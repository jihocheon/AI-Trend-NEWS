# Execution report

**Latest status: curated reference architecture, real guarded MCP Update, and Notion navigation verified; 35 regression tests pass.** See the final sprint section. Earlier network/model blockers and news-only runs remain historical evidence.

Validated on 2026-10-24 (Asia/Seoul), Python 3.12.14, Linux.

## Executed successfully

- Created `.venv` and installed the project with `python -m pip install -e .`.
- `python -m unittest discover -s tests -v`: **16 tests passed**, no skipped tests.
- `python -m pip check`: no broken requirements.
- `python -m pip wheel . --no-deps`: built the distributable wheel, installed it in a separate clean virtual environment, and ran its sample CLI from `/tmp` outside the checkout (Create=2, Update=1, Skip=1).
- Executed the installed CLI on a persistent local database (`var/demo.sqlite3`): first run **Create=2, Update=1, Skip=1**; second run **Create=0, Update=0, Skip=0**.
- Queried ranked topics: Retrieval augmented generation first (score approximately 6), AI agents second (score approximately 3).
- Verified SQLite persistence, source-version tracking, source-to-topic relationships, before/after update history, archival, reactivation, failed-item recovery, and execution logs in automated tests.
- Verified scheduler repetition and interrupt handling with a mocked timer (no long-running scheduler left running).
- Tested RSS/Atom/arXiv/GitHub fixture parsing, Gemini decision validation, and Notion page/block create/update/archive/pending retry handling with fake HTTP responses.

The labelled four-item fixture has the expected action and topic on every item. This is a tiny deterministic regression evaluation, not a measured live Gemini accuracy score.

## External integration status

| Component | Actual result | Still needed |
| --- | --- | --- |
| Live RSS | Attempted default Hugging Face feed; blocked by environment proxy | Permit RSS destination or run on a local network with access |
| Live arXiv | Attempted read; failed through environment network proxy | Access to `export.arxiv.org` |
| Live GitHub | Attempted public search; proxy tunnel explicitly returned 403 | Access to `api.github.com`; token optional for public search |
| Gemini | API key absent; no authenticated request made | Free-tier, unbilled `GEMINI_API_KEY` and access to `generativelanguage.googleapis.com` |
| Notion | Token and parent page ID absent; no remote pages created | `NOTION_TOKEN`, shared `NOTION_PARENT_PAGE_ID`, and access to `api.notion.com` |

No credential values were read, printed, saved, or invented. No billing or deployment was configured. No external publishing was attempted. Network/TLS checks remain enabled. Live provider behavior, account-specific free quotas, Notion permissions, and summary quality remain unverified.

CI configuration was written but has not been executed on GitHub. Local tests and commands above were actually executed. No configuration was published or cloud deployment performed.

## Follow-up live attempt: 2026-10-24 (Asia/Seoul)

The implementation was committed as `447a1ee` and pushed to GitHub `main` with a normal fast-forward push. All 16 tests passed again before that commit.

Credential presence was rechecked without revealing values:

- `NOTION_TOKEN`: present. Authenticated `GET /v1/users/me` succeeded.
- `NOTION_PARENT_PAGE_ID`: present. Authenticated retrieval of that parent page succeeded. This establishes read access, not insert/update permission.
- `GEMINI_API_KEY`: absent from the running process. A Gemini secret requirement already exists in environment configuration; no duplicate requirement was added. Gemini generation could not run.

Real source checks each failed with an explicit proxy destination denial (403): `huggingface.co`, `export.arxiv.org`, and `api.github.com`. A small live CLI run with `--limit 1 --sync-notion` was attempted and exited nonzero at credential preflight. No fixture data was substituted, no Notion pages were created, and page URL verification and live duplicate checks could not execute.

A network configuration draft was saved adding those three source hosts, preserving `api.notion.com` and `generativelanguage.googleapis.com`. Saving the draft did not change the running network policy or publish the configuration. The runtime-status tool was unavailable in this session; policy evidence came from the supported local policy snapshot, saved configuration metadata, and actual HTTP requests.

To unblock the live test: securely supply a free-tier Gemini key as `GEMINI_API_KEY` in environment settings; review/save the drafted domain additions and publish the environment; ensure the updated key and network access reach the running task. Keep billing disabled. Notion credentials do not need to be supplied again based on these successful reads. Insert/update rights and live summary quality still require an actual successful end-to-end test.


## Published-environment retry: live success (2026-10-24, Asia/Seoul)

### Authentication and collection

All three required variables were present; values were never printed. An authenticated Gemini model-list request succeeded. Notion parent-page read access succeeded. The runtime status tool reported current observations but `unknown` readiness states, so readiness was established by the actual successful provider requests rather than inferred from configuration.

Each collector fetched one real item directly from its service. No fixture/sample data or sample reasoner was used in this live run:

| Collector | Actual evidence |
| --- | --- |
| RSS | [LitPivot: Developing research ideas through dynamic contextualization within the literature landscape](https://huggingface.co/blog/allenai/litpivot) |
| arXiv | [Direct Pass@$k$ Optimization for Thought Pruning: Balancing Quality and Diversity in Test-Time Reasoning](https://arxiv.org/abs/2610.31667v1) |
| GitHub | [huggingface/transformers](https://github.com/huggingface/transformers), fetched using a repository-specific public search |

The exact collected source snapshot is retained locally at ignored `var/live-sources.json`; this isolates duplicate checks from changing live feeds. The persistent test database is `var/live-integration.sqlite3`, the execution log is `var/live-integration.log`, and the verification artifact is `var/live-integration-result.json`.

### Integration fixes found during the run

1. Although the model-list endpoint advertised `gemini-2.5-flash-lite`, generation returned HTTP 404 / NOT_FOUND. The provider's error said this model is no longer available to new users and recommended `gemini-3.5-flash-lite`. Updated the default in the Gemini adapter, CLI, `.env.example`, and README. The existing key successfully generated with `gemini-3.5-flash-lite`; no provider switch or billing setup was performed.
2. JSON MIME mode alone returned an array of decision objects. Added an explicit object `responseSchema`, required fields, an enum for Create/Update/Skip, and nullable integer target ID. Kept local validation. Subsequent responses passed validation and the live pipeline succeeded. The schema and default endpoint now have regression assertions.
3. The verification harness initially assumed `www.notion.so`, while the actual API returned `app.notion.com/p/...` URLs. Accepted the API-returned Notion host and verified the URL's page ID, rather than inventing a URL. No remote writes were repeated to correct this verification assumption.

### Created and verified Notion pages

| Topic | API-returned page URL |
| --- | --- |
| LitPivot | https://app.notion.com/p/LitPivot-4028ad41fcfc8106a4d3dd5e71516e6c |
| Direct Pass@k Optimization for Thought Pruning | https://app.notion.com/p/Direct-Pass-k-Optimization-for-Thought-Pruning-4028ad41fcfc81b98d7bfbae4262d930 |
| Hugging Face Transformers | https://app.notion.com/p/Hugging-Face-Transformers-4028ad41fcfc81efb400e5ba63d83311 |

For each page, authenticated Notion GET requests confirmed the stored page ID, configured parent association, active/unarchived state, agent-owned paragraph block, generated summary, and evidence URL. Canonical page URLs came from those successful page responses. This verifies authenticated API access and page contents; it does not establish anonymous/public web sharing or browser login behavior.

### First processing pass and duplicate check

- First successful processing pass: **Create=3, Update=0, Skip=0**; Notion sync created/populated **3 pages**. Model: `gemini-3.5-flash-lite`.
- SQLite persisted **3 sources, 3 topics, 3 decision history records**; all topics had page/block identities and cleared pending-sync flags.
- Second pass used the exact same real-source snapshot, the real Gemini adapter, and the real Notion adapter: **Create=0, Update=0, Skip=0**, Notion synchronized **0** pages. No new Gemini or Notion writes occurred because all evidence was already processed.
- Topic/page mappings and history count remained identical. Paginated parent children were compared by ID: **6 before the second pass, 6 afterward**, with the exact same set of IDs. All three created pages remained present. Existing parent content was preserved.
- The live repeat-run duplicate check passed. This covers unchanged evidence against the same persistent database, not semantic deduplication across a fresh database, changed evidence, or crash-after-write recovery.
- After the model/schema fixes, the offline suite ran again: **16 tests passed**, none skipped. Those fixture tests are separate from the live evidence above.

### Remaining limitations

No network or credential blocker remains for the tested paths. Live Notion archival/reactivation and updates from new evidence were not separately exercised in this small run; they remain covered by mocked tests. No production accuracy benchmark, anonymous URL access test, account billing-status audit, or crash-window duplicate recovery test was performed. No credentials were exposed, no paid services were enabled, and no billing settings were changed.

## Curated knowledge sprint — latest verified state (2026-10-24, Asia/Seoul)

The product now preserves **two equal interfaces**: a curated, revisitable AI engineering reference collection and a Korean date-based AI briefing. It does not aim for encyclopedia coverage or a page-count target. Earlier news-only results above are historical.

### Implementation and tests

- Reused the original collectors, source/version/history store, safe transport and original Notion identities.
- Added source normalization with bounded raw preservation, aliases/canonical identity, independent technical bodies/revisions, source/topic relationships, explainable configurable relevance, FTS5 chunks and history, conditional bounded research traces, token/request reservation and actual usage tracking.
- Added five real Notion areas, a reference **metadata database pointing to canonical bodies**, and a separate Date-property briefing database. Existing page identities and original manual/summary content were retained.
- **35 deterministic tests pass**, none skipped. Built and installed the wheel into a separate virtual environment; real-corpus FTS retrieval and packaged reference data passed outside the checkout. Three trusted Python examples execute successfully. A malformed pricing-section assumption was fixed against Google's actual nested Standard table before generation; exact-model free input/output checks fail closed.
- Measured retrieval: topic Hit@1 **6/6**, MRR@3 **1.0**, source-document Precision@1 **2/3**, irrelevant-query topic results **0**. The remaining document-ranking error is recorded in EVALUATION.md; it is not hidden by a passing label.

### Real source-grounded references and navigation

Three selected Korean reference bodies were published from curated official-source engineering notes, **not sample data and not falsely labelled Gemini-generated**:

| Canonical reference | Verified Notion URL | Technical body |
| --- | --- | --- |
| LLM architecture | https://app.notion.com/p/LLM-4028ad41fcfc81bb81a0d92d00f87495 | 3,072 characters at readback, 10 headings, Mermaid + Python |
| RAG | https://app.notion.com/p/RAG-4028ad41fcfc8192b8cccdae7704b3da | 3,004 characters, 10 headings, Mermaid + Python |
| Agent harness / orchestration / MCP | https://app.notion.com/p/MCP-4028ad41fcfc8163b4f9deb796728f2e | 3,322 characters after real new evidence, 11 headings, Mermaid + Python |

Authenticated reads verified eight meaningful technical sections for these complex topics, stored code/diagram content and language, original source citations, related-page mentions, Home/Wiki/Daily navigation, and stable canonical identities. Mermaid was accepted and returned by Notion; no browser screenshot/visual-rendering claim is made. Concise future references need not duplicate this section count.

- Home: https://app.notion.com/p/Home-Dashboard-AI-4028ad41fcfc81069884d64b437ee91b
- Wiki navigation: https://app.notion.com/p/Technology-Wiki-4028ad41fcfc8194b6fcc07f16734f8a
- Reference database: https://app.notion.com/p/4028ad41fcfc81b3bf98d648823c15e7 — three metadata rows with categories, relevance, date, status, related technologies, evidence count and canonical page URLs. These rows intentionally do not duplicate technical bodies.
- Daily area: https://app.notion.com/p/Daily-Briefing-4028ad41fcfc81b29c2ada1cbea74717
- Dated Korean edition: https://app.notion.com/p/2026-10-24-AI-4028ad41fcfc81b8ae72c66d70b4080e
- Research sources: https://app.notion.com/p/Research-Sources-4028ad41fcfc8197ba4bfa62e31055c5
- Radar: https://app.notion.com/p/Technology-Radar-4028ad41fcfc810f9cc4cf7dacb03fbd

The dated edition has a real Date property, three knowledge-update records plus one real MCP source-review change, and four mentions linking three persistent Wiki references. Its latest source-review explanation separates what was reviewed, why it matters, background mechanism, practical implications and unknown source publication date. No claim is made that an undated schema was released today. The API cannot create the Calendar view: Daily Briefing → 한국어 일일 AI 브리핑 → **+ Add view → Calendar → Date** is the one manual setup action.

### Actual guarded Gemini inference and safe rerun

Initial pricing access was denied; it later became reachable. Google's official pricing page explicitly listed **gemini-3.5-flash-lite Standard Free Tier input/output = Free of charge**. Verified the exact section/table before inference and retained URL/hash/time in `generation_usage.pricing_proof`. The user confirmed billing is disabled for the key's project. No billing configuration was changed.

Fetched real official MCP schema source, persisted as source **9**, and retrieved topic **6** plus source chunk **43**. The real run (**6**) traversed PLANNING → RETRIEVED → READY_TO_INFER → INFERENCING → EVALUATED → COMPLETED and returned **Create=0, Update=1, Skip=0**. It updated the existing harness/MCP identity, added a source relationship/history record, preserved the enduring body, and published recent evidence plus briefing content.

One-request policy: input upper bound 9,000, output ceiling 3,000, total reservation ceiling 12,000. Actual request output cap was 2,048. Reserved **5,919** conservative tokens; provider usage **740 input + 162 output = 902 total**. Processing took **2.005 seconds**. No paid fallback, provider switch or quota bypass occurred. Model/pricing presence without these checks would not be accepted as proof of free operation.

Refetched the same real source and checked the full original content hash before rerunning. The repeated source pipeline produced **0/0/0**, unchanged history and zero new generation attempts. Following Notion sync made zero writes: transport counters **4 reads, 0 errors, 0 write attempts**. A separate remote readback + repeat sync check made **22 reads, 0 errors, 0 writes** in **8.60 seconds**. All three original pages and original summary blocks were checked against the pre-Wiki backup and preserved. These are small observations, not production reliability statistics.

### Reproduce and remaining boundaries

```bash
python -m unittest discover -s tests -v
python -m radar.evaluate --db var/live-integration.sqlite3
python scripts/verify_notion.py --db var/live-integration.sqlite3 \
  --legacy-backup var/pre-wiki-backup.sqlite3
```

Local actual artifacts: `var/guarded-live-result.json`, `var/current-duplicate-result.json`, `var/wiki-validation.json`, `var/retrieval-evaluation.json`, pricing snapshot/proof and the SQLite state/selection/usage/history tables. These files contain no API credential values.

Live verified: official collection, source-backed Korean starter publishing, an existing-topic Gemini Update, evidence/briefing integration, navigation/database/date readback, legacy preservation and unchanged-repeat safety. Tested deterministically rather than newly live: sparse-evidence retry/wait/recovery, malformed output/unsupported quantity rejection, quota exhaustion, and adaptive full-reference Gemini enrichment. Numeric/citation checks do not establish semantic factuality. No load test, distributed locking, automatic cross-system crash reconciliation, or anonymous-sharing validation was performed. Single-process operation remains required.

The environment draft saves pricing-host access and the nonsecret `GEMINI_BILLING_DISABLED=true` acknowledgement for review/publishing; a saved draft is not proof of a new published snapshot. Actual pricing/generation worked in this running instance. Model eligibility is rechecked for future invocations, and unverified/changed pricing stops generation.
