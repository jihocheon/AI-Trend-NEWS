# AI Technology Radar

[![Tests](https://github.com/jihocheon/AI-Trend-NEWS/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/jihocheon/AI-Trend-NEWS/actions/workflows/tests.yml)

A local-first, curated AI engineering reference collection **and** a Korean AI trends briefing, powered by the same sources, topic identities, retrieval, and relevance ranking. This is neither a page-count generator nor an exhaustive AI encyclopedia.

It selects worthwhile technologies, retrieves existing knowledge before decisions, preserves evergreen explanations, and records what changed separately. Strong interests include LLMs, agent harnesses, orchestration, MCP, RAG, inference and evaluation; adjacent discoveries remain eligible.

## Run locally

Python 3.11+ with SQLite FTS5; no runtime packages or cloud deployment required.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v
# Install three carefully selected Korean references from official originals; no Gemini:
ai-radar --db var/radar.sqlite3 bootstrap
ai-radar --db var/radar.sqlite3 search 'RAG'
ai-radar --db var/radar.sqlite3 search 'MCP' --category Agents
python -m radar.evaluate --db var/radar.sqlite3
```

The starter references cover LLM architecture, RAG, and agent harnesses/orchestration/MCP because they are useful, interconnected engineering references. They are curated editorial starting points, not evidence of automated Gemini writing or a requirement to create every category. They contain source links, technical explanations, trade-offs, Mermaid diagrams, and small Python examples executed in regression tests. Simpler future entries may be shorter.

For the already populated workspace use `--db var/live-integration.sqlite3`. Preserve this database: it holds the existing Notion identities. Do not create a fresh database to resync the same workspace.

## Notion workspace

Securely provide `NOTION_TOKEN` and `NOTION_PARENT_PAGE_ID`. Share the parent page with the integration with read/insert/update capabilities. No values belong in source code, shell arguments, logs, or chat. `.env.example` lists names; `.env` is **not** auto-loaded.

```bash
ai-radar --db var/radar.sqlite3 workspace-sync
python scripts/verify_notion.py --db var/radar.sqlite3
```

Five linked areas: Home Dashboard, Technology Wiki, Daily Briefing, Research & Sources, and Technology Radar. The Wiki contains a searchable database with Category, Relevance, Last updated, Status, Related technologies, Sources, and Reference. Rows intentionally link to canonical technical pages instead of duplicating their bodies or changing existing page identities. The original three news-derived pages are preserved, but excluded from the curated dashboard until they have worthwhile reference content.

Briefings use a separate database with `Date` and one edition per publication day in **Asia/Seoul**. Entries link to the same persistent reference pages and sources; original source publication dates remain separate. A wiki-update edition is labelled a knowledge-update record, not falsely described as breaking news. Live selected news is summarized in Korean with source dates and links.

**Calendar setup:** open Daily Briefing → 한국어 일일 AI 브리핑 → **+ Add view → Calendar → Date**. The API can create the database/date property but cannot configure that view. Notion API readback validates stored Mermaid blocks; browser diagram rendering and public sharing are not independently verified.

Sync only changes agent-owned blocks. Manual/unknown blocks are retained. A repeated unchanged sync makes no writes. Cross-system exactly-once writes are not guaranteed: after an ambiguous remote timeout, inspect Notion before retrying. A crash between a successful write and local ID persistence can leave an orphan. Keep database backups. Archive status is reversible; generated index rows show Archived and the dashboard stops featuring them. Foundational references do not expire merely because there was no recent news.

## Strict zero-cost Gemini

Use only an API key whose project has **Cloud Billing disabled**. The user confirmed that fact for the current key; the API key cannot itself prove billing status. The application never enables billing, upgrades a tier, uses a paid fallback, or changes providers.

Live generation has a fail-closed gate:

1. `GEMINI_BILLING_DISABLED=true` explicitly acknowledges the key project's billing state.
2. Fetch Google's [official pricing](https://ai.google.dev/gemini-api/docs/pricing) and verify the **exact model's Standard table** explicitly lists Free Tier input and output as **Free of charge**.
3. Persist pricing URL/hash/time and reserve conservative request/token budgets before POST.
4. Record actual `usageMetadata`; any request failure/quota error stops this invocation without automatic POST retries or model switching.

Default model: `gemini-3.5-flash-lite`, whose Standard free-tier eligibility was actually verified during the sprint. Eligibility is rechecked per process, never inferred from API-key presence or model listing. Default per-invocation limits are **2 requests, 6,000 estimated input tokens/request, 3,000 output tokens/request, 12,000 reserved total tokens**. Serialized UTF-8 bytes plus overhead deliberately overestimate input tokens. Hard configurable ceilings in the budget constructor are 3 requests, 12,000 input, 4,000 output, 20,000 total. No grounding/search tools, caching service, Batch API, or paid-only features are invoked. Free-tier quotas/privacy terms are account- and region-dependent; public official sources are used in the demo.

```bash
# Set credentials securely in your environment first, then:
export GEMINI_BILLING_DISABLED=true
ai-radar --db var/radar.sqlite3 run --mode live --limit 1 --sync-notion
# Enrich one existing selected reference with retrieved source evidence:
ai-radar --db var/radar.sqlite3 enrich 5
ai-radar --db var/radar.sqlite3 workspace-sync
```

Use the correct local topic ID from `topics`/`search` for enrichment. `enrich` drafts require structural and citation validation; they are marked as model drafts, and code is not automatically executed. Budgets may stop a long prompt; do not increase limits blindly. At the local request cap, a batch pauses with `pending_sources` and can publish completed changes; remaining sources wait for a later explicit run. An API quota error or unsafe token estimate stops with no fallback. Failures retain committed decisions. All paused/pending states are inspectable in SQLite.

Required destinations: `ai.google.dev`, `generativelanguage.googleapis.com`, `api.notion.com`, `huggingface.co` (default RSS), `export.arxiv.org`, `api.github.com`, and `raw.githubusercontent.com` for official reference seeds. Keep the managed proxy and TLS verification enabled. The environment draft adds pricing access and the billing-disabled acknowledgement; saving a draft is separate from applying/publishing it.

## Discovery, ranking, and retrieval

Collection is separate from editorial selection. Source adapters fetch RSS/Atom, arXiv metadata and public GitHub repository metadata; bootstrap fetches official docs and original paper metadata. Raw records are bounded/preserved, HTML scripts are excluded from normalized text, known timestamps normalize to UTC, and unknown dates remain unknown. Sources deduplicate by kind/external identity/original content hash, preserving changed versions. GitHub search is not a full release/commit/news crawler; no full-article scraping is claimed.

Ranking uses technical relevance **30%**, foundational importance **25%**, practical utility **20%**, novelty **8%**, credibility **12%**, freshness **5%**. These are transparent heuristic proxies, not calibrated judgments of research quality. Source credibility is a provenance signal, not proof that claims are true. Maturity is an explicit editorial label, not an automatically validated readiness measure; no calibrated momentum predictor is claimed. Novelty distinguishes previously seen source identities; it is not a semantic discovery score. Redundancy uses source hashes, aliases and existing topic retrieval. Source selection and topic selection store scores, factors, and explanations independently.

```bash
# Optional JSON array of interests; optional JSON object of the six weights, summing to 1:
ai-radar --db var/radar.sqlite3 --interests examples/interests.json \
  --ranking-weights examples/weights.json run --mode live --limit 1
```

SQLite FTS5 indexes overlapping source chunks and conceptual topic text. Exact identity/aliases are tried first; BM25 ranks lexical matches. Strict document term conjunction is preferred, with a broader fallback. Code examples are excluded from the topic index to avoid irrelevant matches. Source IDs, URLs, excerpt positions and historical decisions accompany retrieval. Retrieved excerpts are supplied to the Gemini classifier; enrichment uses persisted related source evidence and existing text. No embedding model/vector database is claimed. Korean morphology and ambiguous terms remain limitations.

The deterministic planner selects/rejects, retrieves, checks evidence sufficiency, makes at most one additional local retrieval when needed, and pauses for evidence/review instead of inventing missing facts. A numeric red-flag check detects unsupported quantities; it does **not** prove semantic entailment. Unknown concepts are not promoted to full reference pages solely because a model produced one news paragraph.

## Operation and evidence

Optional local scheduling: append `--interval 3600` to `run`. One foreground process only per database; no distributed locking or automatic daemon installation. The request budget spans the entire invocation, including loop iterations, so quota limits are not bypassed by a scheduler. GETs have bounded backoff; writes are not automatically retried. Notion publishing is paced. HTTP logs contain only service/method/status/timing; no tokens or remote error bodies.

Local `var/` contains SQLite data, rotating logs, usage reservations/actual usage, selection explanations and workflow events. Before additive Wiki migration, a `.pre-wiki-v1.bak` SQLite backup is created without overwriting an existing one. This is a version-2 additive migration, not a generic migration framework.

An explicit `run --mode sample` remains an offline fixture demonstration; it is never used as live proof. See [VALIDATION.md](VALIDATION.md), [EVALUATION.md](EVALUATION.md), [ARCHITECTURE.md](ARCHITECTURE.md), [DECISIONS.md](DECISIONS.md), and [ENGINEERING_WALKTHROUGH.md](ENGINEERING_WALKTHROUGH.md) for measured results and limitations. This is a tested local integration, not a production-readiness claim.


## Continuous integration

The existing [Tests workflow](.github/workflows/tests.yml) runs on pushes to `main`, pull requests targeting `main`, and manual dispatch. GitHub-hosted Ubuntu with Python 3.12 creates a clean virtual environment, installs the project, runs `python -m pip check`, executes **all regression tests** (zero tests or skipped outcomes fail the gate), evaluates retrieval against an isolated fixture-backed SQLite database, and smoke-tests the installed CLI outside the checkout including an unchanged rerun.

Checks run with Python network operations blocked and live API credentials empty. Dependency/action installation may use package registries; tests, evaluation, and smoke never call Gemini, Notion, or other live services and never open the production database. The evaluation uses explicitly synthetic source fixtures and enforced thresholds; it is not a new measurement of live retrieval quality. Actions are pinned to verified commit SHAs, permissions are `contents: read`, and the job has a 10-minute timeout. No Notion publishing, model generation, or deployment is part of CI.
