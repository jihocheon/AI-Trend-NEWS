# AI Technology Radar Agent

A working local-first Python pipeline: collect RSS / arXiv / GitHub → retrieve related topics → classify, summarize, and decide Create / Update / Skip → persist evidence and history in SQLite → rank and archive → optionally publish to Notion.

Python 3.11+; no runtime packages, OpenAI API, cloud deployment, paid services, or billing setup required. The default sample mode needs no keys or network. Architecture is inspired by AgenticWorks' separation of knowledge pipelines, orchestration, tools, and evaluations; it does not depend on or claim compatibility with that framework.

## Quick start

```bash
cd /path/to/AI-Trend-NEWS
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v
ai-radar run
ai-radar topics
ai-radar run  # unchanged evidence is not processed again
```

The first run produces **2 Create, 1 Update, 1 Skip**. The second produces all zeros. Sample evidence is fictional and fixed; sample reasoning is deterministic rules, not Gemini. Data and rotating execution logs are under ignored `var/`. `python -m radar` also works without installing the command. Global options go **before** the subcommand:

```bash
ai-radar --db var/sample.sqlite3 --log var/sample.log run --mode sample
ai-radar --db var/sample.sqlite3 topics
```

Use separate sample and live databases to keep fixture topics out of the real radar. Sources are versioned by kind, external ID, and content hash: unchanged items are ignored; changed content is retained as new evidence.

## Live collection and Gemini

Create a Gemini API key in Google AI Studio using a project with **no billing enabled** and free-tier access. Never enable billing for this project. Free-tier availability, model access, and quotas vary by region/account and may change; this application cannot inspect your billing status. It stops on quota/access errors instead of switching providers or paid models. It uses no Google Search grounding or other paid tools.

Provide `GEMINI_API_KEY` securely through your shell or environment settings, never in source code, command arguments, logs, or chat. `.env.example` lists names only; `.env` files are **not automatically loaded**. Optional `GEMINI_MODEL` defaults to `gemini-3.5-flash-lite`; choose only a model available on your account's free tier. `GITHUB_TOKEN` is optional for public repository search; it may improve rate limits.

```bash
ai-radar --db var/live.sqlite3 run --mode live --limit 3
ai-radar --db var/live.sqlite3 run --mode live \
  --rss https://huggingface.co/blog/feed.xml \
  --arxiv-query 'cat:cs.AI OR cat:cs.CL' \
  --github-query 'topic:llm' --limit 2
```

RSS defaults to the Hugging Face blog; repeat `--rss` to select multiple feeds. `--limit` applies to **each** collector, not the total. GitHub collects repository metadata sorted by recent updates, not commits/issues or a complete news stream. arXiv collects recent matching papers. RSS 2.0 and basic Atom feeds are supported. No article scraping is performed. Source text is bounded before reasoning, and retrieved candidate summaries are supplied to Gemini. Generated decisions are validated: Update must reference a retrieved existing topic; malformed responses fail visibly. Source content is untrusted and never executed.

HTTPS destinations for live mode:

- `huggingface.co` (or your chosen RSS host)
- `export.arxiv.org`
- `api.github.com`
- `generativelanguage.googleapis.com`
- `api.notion.com` for optional publishing

An environment proxy must allow these destinations. TLS verification remains enabled and credential-bearing redirects are rejected. HTTP GET requests retry transient failures up to three attempts; writes do not automatically retry because remote mutations can be ambiguous. Gemini 429 responses stop the run: wait for quota recovery and rerun; completed source transactions are retained. No silent fallback to fixtures occurs in live mode.

## Notion publishing (explicit opt-in)

Create a Notion integration with read/insert/update content capabilities, then share a parent **page** with it. Supply `NOTION_TOKEN` and `NOTION_PARENT_PAGE_ID` through environment variables. This uses standard child pages, so a Notion database schema is not required. A free Notion workspace is sufficient for this design.

```bash
ai-radar --db var/live.sqlite3 sync
# Or synchronize after a successful collection run:
ai-radar --db var/live.sqlite3 run --mode live --sync-notion --limit 2
```

Publishing is never enabled by default. Using `sync` on a sample database explicitly publishes fictional sample pages. The agent persists each remote page ID and its own summary block ID, then updates that block in place. Other manually added blocks are preserved. Pending updates survive failures and can be retried with `sync`. Local stale topics archive remotely using Notion's reversible `archived` flag; new evidence reactivates them. Archived topics that have never been published remain local.

**Remote write limitation:** Notion has no cross-system transaction with SQLite. A timeout or crash after a successful page/block write but before its ID is persisted can leave an orphan/duplicate page or block on retry. Inspect Notion after ambiguous write failures before retrying. Do not delete the local database if you want to preserve remote identities. External deletion of an agent-owned page/block requires manual reconciliation; the agent does not silently overwrite a replacement.

## Storage, ranking, and archiving

SQLite tables: `sources` (versioned raw evidence), `topics` (current summaries and Notion identities), `relationships` (evidence-to-topic links), `history` (decisions and before/after topic snapshots for Create/Update), and `runs` (execution status and decision counts). Each decision, its relationship, its history, and source completion marker commit atomically. Failed items remain pending for the next successful collection run. Failed live collection leaves previously stored data intact.

Retrieval uses lexical token overlap against existing names/summaries, including archived topics, with a top-five candidate limit. This is a transparent baseline, not semantic embedding search. Ranking is:

```text
(evidence_count + 2 × distinct_source_kinds) / (1 + days_since_last_evidence / 30)
```

Evidence count includes source revisions. It measures observed support, not scientific quality or independent corroboration. Topics inactive for 90 days are marked archived, logged in history, and retained with all evidence. `--archive-days N` changes that threshold. Archive age uses local last processing time, not publication date. `topics` shows archived topics too. No destructive cleanup is implemented.

## Scheduling and logs

```bash
ai-radar --db var/live.sqlite3 run --mode live --limit 1 --interval 3600
```

This optional foreground loop runs immediately and then waits the specified seconds after each successful run (minimum 60). Ctrl-C stops it. A failure exits nonzero; use a local process supervisor or cron for retries. Run only **one writer/scheduler per database**. Avoid overlapping cron jobs. No background daemon is installed.

`var/radar.log` rotates at 1 MB with three backups. Logs record run/source IDs and decisions, never tokens or raw external responses. SQLite `runs` records processing successes and failures; collection and Notion failures appear in the file log/CLI, outside the processing run transaction. Database contents include source text and generated summaries: treat local files as private if your configured sources are private. Shell tracing should remain disabled when handling credentials.

## Validation and limitations

Run `python -m unittest discover -s tests -v`. Tests cover the labelled fixture decisions, ranking, evidence relationships, repeated runs, source revisions, persistent storage, reversible archival, failed-decision recovery, RSS/Atom/arXiv/GitHub parsing, Gemini output rejection, Notion create/update/archive/retry state, CLI behavior, and execution logs. CI runs offline tests and a sample pipeline.

See [VALIDATION.md](VALIDATION.md) for the actual execution report. Mock adapter tests verify request/response handling; they do **not** prove external service access or output quality. The small offline evaluation is a regression fixture, not a production accuracy benchmark. Real-world relevance, duplicate-topic rates, and summary factuality need a larger curated dataset. There is no embedding index, full-text article ingestion, distributed execution, UI, or automatic schema migration. Back up the database before future schema changes.

Repository implementation is modular:

| Module | Responsibility |
| --- | --- |
| `collectors.py` | RSS / Atom, arXiv, GitHub and fixed samples |
| `intelligence.py` | Deterministic baseline and validated Gemini decisions |
| `store.py` | SQLite evidence, lexical retrieval, history, ranking, archival |
| `pipeline.py` | Transactional decision orchestration and run tracking |
| `notion.py` | Pending page/block synchronization |
| `http.py` | Bounded, verified-TLS transport and sanitized failures |
| `cli.py` | Commands, credential selection, rotating logs, local scheduling |
