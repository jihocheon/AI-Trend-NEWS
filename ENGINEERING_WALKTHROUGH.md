# One real MCP item through the system

This walkthrough describes real execution on 2026-10-24 (Asia/Seoul), not a hypothetical platform demo. The canonical topic already existed as a selected Korean reference. Original three news-derived pages also remained untouched.

## 1. Discovery and preparation

The current official MCP repository README points to the schema for version `2026-07-28`. Fetched the actual [schema.ts](https://raw.githubusercontent.com/modelcontextprotocol/modelcontextprotocol/main/schema/2026-07-28/schema.ts): **98,376 characters**. The version string is not fabricated as a publication timestamp; publication date is stored as unknown.

`Source` carries external identity, kind, title, URL, text and publication date. `Store.ingest` retains an original content hash, bounded raw JSON (64,000 characters, with a truncation flag), and normalized text bounded at 20,000 characters. Thus the raw record is explicitly incomplete for this large schema; the full hash still identifies the collected version. No source content is executed.

Code: [preparation.py](radar/preparation.py), [store.py](radar/store.py). Local source ID: **9**. This is an additional persisted source, not a reset of an earlier one.

## 2. Planner and retrieval

The technical title/schema receives interest, credibility and utility signals; selection factors and reason are stored in `source_selection`. Freshness is a small signal and unknown publication dates do not become “today's release.”

The planner invokes [FTS retrieval](radar/retrieval.py), not just a direct row lookup. Text chunks are indexed with source IDs, positions and URLs; topic FTS indexes reference names, aliases and conceptual text. Exact identity resolution precedes BM25 fallback. The real run retrieved **topic ID 6** (에이전트 하네스 · 오케스트레이션 · MCP) and **chunk 43**. The candidate ID and retrieved excerpt were passed to Gemini, making Update actionable against the existing identity.

Inspectable real workflow (SQLite `workflow_events`, run **6**):

```json
[
  {"state":"PLANNING"},
  {"state":"RETRIEVED","topic_ids":[6],"chunk_ids":[43],"latency_ms":4.486},
  {"state":"READY_TO_INFER"},
  {"state":"INFERENCING"},
  {"state":"EVALUATED","decision":"Update"},
  {"state":"COMPLETED","decision":"Update"}
]
```

When a source lacks enough text, the implemented alternative branch does one additional local retrieval, then pauses in WAITING_EVIDENCE if support remains absent. That branch/recovery was exercised by tests, not falsely claimed for this adequate live source. This is deterministic bounded orchestration, not an autonomous model-selected browsing system.

## 3. Free-tier inference gate

The user confirmed Cloud Billing is disabled for the key's project. The verifier fetched Google's official pricing page and checked `gemini-3.5-flash-lite`'s **Standard** table: Free Tier input and output are both “Free of charge.” URL, content hash and verification time are stored with the generation reservation. An earlier parser stopped at a nested h3 heading; the corrected model-section boundary and Standard-table parser were tested before generation.

This live check used stricter **one-request** scope, input upper bound 9,000, output ceiling 3,000 and aggregate ceiling 12,000. The actual classification request set `maxOutputTokens=2048`. Serialized-payload reservation was **5,919 tokens**. Returned metadata: **740 prompt + 162 output = 902 total**. No billing action, service fallback or quota bypass occurred.

Code: [free_tier.py](radar/free_tier.py), [intelligence.py](radar/intelligence.py). Live inference/processing took **2.005 s**. Subsequent prompt enrichment adds previous-concept excerpts/history and has an explicit fake-transport contract test; no second live generation is claimed for that later addition.

## 4. Evaluation and decision

Object schema validates fields and decision enum. Update can only reference a retrieved topic ID. [workflow.py](radar/workflow.py) checks suspicious numeric claims against source excerpts before persistence. There were no quantitative benchmark claims to flag. This is not a semantic proof of every statement.

Actual Korean summary:

> Model Context Protocol(MCP)의 최신 2026-07-28 버전 프로토콜 스키마 코드로, 공통 JSON 타입과 JSON-RPC 메시지 구조 및 메타데이터 필드 정의를 포함하고 있습니다.

Result: **Create=0, Update=1, Skip=0**. Existing topic **6**, its canonical Notion ID and enduring conceptual body were retained. The latest evidence summary is separate from `wiki_json`; the new source relationship/history/change record were committed. The “latest” wording describes the checked repository version; no publication time was invented.

## 5. Publishing the change

`Workspace.sync` patches owned metadata/recent-evidence blocks and the existing dated edition. It does not replace the page's eight conceptual sections or unknown user blocks. The source index links to the original schema and the same topic. The Daily Briefing's **2026-10-24** edition now has four change mentions linking three persistent references; its Date is the edition publication date, separate from source publication dates.

Canonical page: [에이전트 하네스 · 오케스트레이션 · MCP](https://app.notion.com/p/MCP-4028ad41fcfc8163b4f9deb796728f2e). Its database metadata row points to this body instead of copying it. The page contains architecture/algorithm/implementation/use/comparison/limitations/evaluation explanations, original evidence, Python example and Mermaid architecture flow.

## 6. Readback, monitoring and repetition

Authenticated page/block/database reads verified stored technical text, code language/content, navigation mentions, date properties, index schema, canonical URL, and original page preservation. API acceptance of Mermaid is verified; browser pixels/public sharing are not.

Refetched the **same actual schema**, checked its full original hash against the completed source, and reran the real pipeline with the real Gemini adapter. It reached no generation: **0 Create / 0 Update / 0 Skip**, unchanged history. Subsequent sync made **0 Notion writes**. HTTP counters: **4 reads, 0 errors, 0 generation attempts, 0 write attempts**.

Local artifacts: `var/guarded-live-result.json`, `var/current-duplicate-result.json`, `var/wiki-validation.json`, `var/retrieval-evaluation.json`, SQLite workflow/selection/history/usage tables. They contain operational evidence; credentials are never recorded. Reproduce readback using `scripts/verify_notion.py`; do not reset the real database to manufacture a fresh run.

This demonstrates source preparation → indexing → retrieval → selection → guarded inference → validation → Update → integration → readback → duplicate check. Remaining weaknesses, including document ranking, entailment checking and ambiguous remote-write recovery, are recorded rather than represented as completed features.
