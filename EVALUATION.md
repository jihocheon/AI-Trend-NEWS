# Reproducible evaluation

Measured 2026-10-24 (Asia/Seoul), Python 3.12.14, local SQLite FTS5. No LLM-as-a-judge, synthetic live success, paid tools, or invented metrics.

## Reproduce

```bash
python -m unittest discover -s tests -v
ai-radar --db var/evaluation.sqlite3 bootstrap  # fetch actual originals; zero Gemini
python -m radar.evaluate --db var/evaluation.sqlite3
# Existing real workspace corpus, including legacy sources:
python -m radar.evaluate --db var/live-integration.sqlite3
python scripts/verify_notion.py --db var/live-integration.sqlite3
```

The exact local JSON artifacts are under ignored `var/`; changing the corpus can change results. Do not reset the real knowledge database for evaluation. `evaluate.py` contains the manually labelled queries and expected topic keys/source URLs.

## Retrieval methodology and results

Six topic queries: RAG, 트랜스포머, MCP, KV cache, reranking, 도구 호출. Gold targets are respectively RAG, LLM architecture, harness/MCP, LLM architecture, RAG, harness/MCP. Hit@1 measures whether the first result is correct; MRR@3 averages reciprocal gold-topic rank in the first three. Source Precision@1 uses three separately labelled queries: similarity-search/vector clustering → FAISS README, Model Context Protocol → official MCP README, causal language model → Transformers LLM tutorial. One unrelated query (volcano/weather/baseball) should return no topic.

| Metric | Actual result |
| --- | --- |
| Topic Hit@1 | 6/6 = 1.000 |
| Topic MRR@3 | 1.000 |
| Source-document Precision@1 | 2/3 = 0.667 |
| Irrelevant query topic results | 0 |
| Mean topic retrieval latency, latest local run | 2.02 ms (six queries, includes local indexing work) |

The failed source query retrieved the RAG paper before the expected Transformers tutorial. Both discuss language models, but it fails the deliberately specific gold label. This is an unresolved source-ranking error, not a reason to silently relabel the test as passing. An earlier irrelevant hit came from the word “weather” in a toy code example; excluding code from conceptual indexing fixed it. The source conjunction-first fallback did not resolve the remaining document error.

These are small, in-repository regression labels close to the starter notes, not an independent relevance benchmark. MRR success does not imply general semantic understanding. No embedding improvement has been measured. The corpus includes legacy topics and actual official references, not just isolated SQL identity lookups; BM25 excerpt selection is measured separately from identity matching.

## Deterministic regression suite

**35 tests passed**, zero skipped, in the final run. Coverage includes:

- Original 16 source parsing, decision validation, persistence, source versions, Create/Update/Skip fixture actions, ranking/archive/reactivation, CLI, scheduling, Notion retry checkpoint and unchanged rerun tests.
- Additive migration with backup and remote identity preservation; canonical aliases convert Create to Update without replacing evergreen text.
- Idempotent curated installation, relationships and dated changes, cross-language aliases/category search.
- FTS chunks with URLs/history, quoted query terms, bounded NEED_EVIDENCE → RESEARCH_RETRY → WAITING_EVIDENCE, and recovery when support appears.
- Independent rejection of invented citation URLs and unsupported quantitative claims. These are structural/numeric checks, not full factual entailment verification.
- Pricing-table shape, nested Standard heading, exact model, both free input/output, billing acknowledgement, unverified-generation denial, token/request exhaustion, actual usage tracking, and stop-after-failure.
- HTML script exclusion, retained raw original, unknown-date preservation, invalid ranking weights and evergreen references surviving a news-free interval.
- Retrieved concepts/evidence/history reaching the LLM prompt; three trusted curated Python snippets executed with their assertions.

## Live engineering evidence

One new official MCP schema was collected and selected; FTS retrieved existing topic 6 and evidence chunk 43. The real guarded Gemini classifier returned Update, preserving the technical page and adding new evidence/briefing content. Trace states were PLANNING → RETRIEVED → READY_TO_INFER → INFERENCING → EVALUATED → COMPLETED. The missing-evidence feedback branch was tested deterministically, not forced against live APIs.

| Observation | Actual result |
| --- | --- |
| Live classify run decisions | Create=0, Update=1, Skip=0 |
| Generation calls for that run | 1 |
| Reserved conservative token bound | 5,919 |
| Actual Gemini prompt / output / total tokens | 740 / 162 / 902 |
| Source processing wall time | 2.005 s, one item |
| Repeated identical live-source run | all zero decisions; history unchanged |
| Repeated live-source + Notion sync | 4 HTTP reads, 0 errors, 0 Gemini generation, 0 Notion writes |
| Separate Notion readback + unchanged sync | 22 HTTP reads, 0 errors, 0 writes, 8.60 s |
| Original Notion pages preserved | 3/3, ID and original summary-block readback |
| Selected Korean reference pages | 3, each with stored Mermaid and Python code |
| Technical structure | Eight technical sections per complex starter; concise future entries allowed |
| Explicit original citations in starter references | 5/5 URLs resolve to persisted source relationships |
| Dated edition links after live update | Four change mentions referencing three persistent Wiki topics |

The 22-request check was measured before later transport/log refinements; the repeat pipeline check used the transport counters. Its error rate was 0/4; the former was 0/22. These tiny checks are not reliability estimates. Initial creation write counts were not instrumented retroactively; no number is invented for them.

## Limits

No visual browser screenshot audit, semantic claim entailment benchmark, ranking precision benchmark, multi-user/load test, LLM judge, distributed restart test, or real induced Notion 429 was performed. Unknown source dates remain unknown. Manuscript provenance and numeric checks do not prove every explanatory statement. Live free-tier generation succeeded for one classification; adaptive full-reference generation is implemented but not newly exercised live. Quota/error handling uses deterministic failures instead of intentionally burning free quota.

## Conversational RAG evaluation (2026-10-24, Asia/Seoul)

The original knowledge/source evaluation and its 2/3 real-document result are unchanged. The chatbot adds a separate transparent test set in `tests/fixtures/chat_questions.json`: eight answerable Korean/English queries and four ambiguity/gap/safety queries. Queries cover factual explanation, multi-topic comparison, paraphrases, acronyms with Korean particles, and two context-dependent follow-ups. Production-source accuracy is not inferred from fixture scores.

Reproduce offline:

```bash
python -m pip install -e '.[chat,test]'
python -m unittest discover -s tests -v
PYTHONPATH="$PWD/scripts/ci_offline" python scripts/ci_chat_evaluate.py
```

| Metric | Measured result | Interpretation |
| --- | --- | --- |
| Baseline mean topic Recall@3, eight positive questions | 0.6875 | Original FTS receives only the literal current question |
| Chat mean topic Recall@3 | 1.0000 | Same FTS with aliases, deterministic expansion and bounded focus memory |
| Four gap/safety queries without unrelated evidence | 4/4 | Includes a pre-inference refusal; this is pipeline behavior, not pure FTS quality |
| Mean comparison latency on real SQLite corpus | 9.92 ms | Includes both retrieval paths; tiny corpus, no LLM call |
| Automated regression tests | 58 passed, 0 skipped | Original 35 retained plus 23 chat tests |

The identical labelled questions against the real persistent knowledge store gave the same recall values. Rules and labels are in-repository and close to the curated subjects; these are regression results, not held-out proof of semantic generalization. No vector database or embedding improvement is claimed.

Answer verification tests reject unknown IDs, fabricated supporting quotes/URLs, unsupported numeric claims, near-verbatim dumps, unlabelled responses and secret-like output. Explicit conflicting-source cases need an uncertainty segment with two exact supporting quotes. Source-instruction placement, project-scope abstention, session continuity/expiry, privacy, shared-budget accounting across connection/thread changes, provider 429/no fallback and API host/origin boundaries are tested. These are deterministic contracts, not generated-answer quality scores.

### Three actual Gemini answers in a real browser

| Check | Actual result |
| --- | --- |
| Desktop comparison: RAG vs MCP, practical document QA | HTTP 200; grounded roles + labelled practical inference |
| Follow-up: permissions and latency | HTTP 200; same focus/session retained; latency coverage incomplete |
| Mobile original-source comparison | HTTP 200; RAG paper and official MCP source actually cited, original/Notion links displayed |
| Source identifiers | All 11 citation-ID references across seven evidence-bearing segments resolve to returned selected evidence |
| Source evidence labels | Six grounded, one inference, one additional general-knowledge segment explicitly labelled |
| Browser behavior | Desktop/mobile inspected; no page errors or horizontal mobile overflow; new conversation/gap/quota states verified |
| Requests and tokens | Exactly 3 generation requests; 1,598 + 1,595 + 1,582 = 4,775 total tokens |
| Server response times | 10.35 s / 8.07 s / 6.07 s; pricing GET included on each server's first request |
| Notion curation regression | Existing publisher unchanged sync: 3 GETs, 0 writes, 0 errors |

The three generations occurred in explicitly bounded validation invocations allowing two and then one request. Both verified current official Standard free-tier eligibility before generation using the user's billing-disabled acknowledgement. No model fallback or billing change occurred. UI reset/error/knowledge-gap checks made zero extra model generations.

Manual completeness rubric: comparison roles/application **3/3**; follow-up retrieval permission/tool permission-timeout/latency decomposition **2/3**; source comparison memory distinction/spec coverage/original attribution **3/3**. Total **8/9** checks, one reviewer and three examples, not an independent benchmark. Later sentence targeting for latency is unit-tested but no improved live follow-up score is invented. Supporting quote checks passed; full semantic groundedness and unsupported-claim rates remain **unmeasured**. A zero numeric-red-flag count does not prove zero hallucinations. General knowledge was labelled rather than presented as verified store content.

Local opt-in artifacts: `var/chat-live-results.json`, `var/chat-live-originals.json`, `var/chat-ui-states.json`, `var/chat-retrieval-evaluation.json`, and desktop/mobile screenshots. Default operational logs omit conversation text and raw model output. CI stays fully offline and executes the new chat evaluation and packaged web-asset smoke checks.
