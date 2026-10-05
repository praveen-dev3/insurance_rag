# Architecture sketch - Claims Triage & Coverage Assistant

```
                         python weeks.py w12 triage --claim CLM-...          (the one entry point)
                                              |
                                              v
 +-------------------------------- TriageSession.run  (tools/w12_agent.py) ---------------------------------+
 |  mints trace_id  ->  RequestTrace (spans: stage, latency, tokens, cost)  ->  RequestSink (redact + verify) |
 |                                                                                                           |
 |  1 intake (harness) --MCP--> claims-records.get_fnol    <- redacted view: no name / address / injury      |
 |                                                                                                           |
 |  2 loop (Week 7 hand-built):                                                                              |
 |       [ MODEL CALL ] gpt-oss-120b  <- tools = whatever tools/list returned + refer_to_adjuster            |
 |             |  tool_calls                                                                                 |
 |             +--MCP--> claims-records.check_coverage_in_force(policy, loss_date)   (dates only)            |
 |             +--MCP--> policy-wording.search_policy_wording(query, product, loss_date)                     |
 |             +--MCP--> policy-wording.get_limits(policy, loss_date, peril)  -> deductible | sub-limit |     |
 |             |                                                                policy limit (3 numbers)     |
 |             +--local-> refer_to_adjuster(reason, summary, citations)      <- the only way a run ends      |
 |                                                                                                           |
 |  3 finalize: system (not model) attaches loss date, edition range, verbatim excerpt, the 3 numbers;       |
 |              ungrounded citation -> grounded:false;  OUTPUT GUARD scans model prose, rewrites on a hit     |
 +-----------------------------------------------------------------------------------------------------------+
         |  _meta.trace_id on every tools/call                        ^  result._meta.server_span
         v                                                            |
 +---------------------------+            +--------------------------------------------------------------+
 | claims-records (stdio)    |            | policy-wording (stdio)  - OUR server, usable by any MCP client |
 |  w12_claims_server.py     |            |  w12_policy_server.py                                          |
 |  wire guard: PII search   |            |   search -> w12_retrieval.search_wording                       |
 |  on every response        |            |     in-force editions from w12_inforce (code, no model)        |
 +---------------------------+            |     filter { form_numbers, edition_dates }  + pair post-check  |
                                          |     -> RagEngine: dense bge-small + BM25 -> RRF -> cross-encoder|
                                          |        over chroma_db_w12/  (6 PDFs, 36 chunks, 2 editions of  |
                                          |        the flood forms)                                        |
                                          +--------------------------------------------------------------+
 server span log: traces/w12_mcp_spans.jsonl (trace_id, tool, arg NAMES, latency - no arguments, no results)
 request log:     traces/w12_requests_<label>.jsonl (redacted on write; notes never stored)
```

## Where the model is called

Exactly two places. **`TriageSession.run`, one call per lap** (`llm.lapN` spans; about 5 laps and 11,000 tokens per
claim on gpt-oss-120b), and **the judge** in `w12_audit.py` (qwen/qwen3.8-27b, eval only). Nothing in either MCP
server, `w12_inforce.py`, `w12_retrieval.py`, `w12_guard.py` or the scoring imports an LLM client. Embedding and
reranking are local.

## Where the money goes (n=25, `eval/w12/cost_and_10x.md`)

Mean **$0.00196 per claim**. Retrieval costs nothing as a call (local search) but its passages are re-sent on every
later lap; attributing tokens to the stage that caused them gives **generation 75%** (the fixed prompt - system
text and six tool schemas - re-sent each lap, plus every output token), **retrieval 15%**, **tools 10%**. The MCP
hop adds a median 1.2 ms. At hailstorm volume the first thing to break is the provider's token rate limit, not the
bill ($35 for 18,000 claims) and not latency.

## What is deterministic, on purpose

Whether the policy was in force, which edition governs, which three numbers apply, which passages are citable, and
whether a sentence contains decision language are all answered by code (`w12_inforce.py`, `w12_retrieval.py`,
`w12_guard.py`), so the model is never the thing standing between a loss date and the wrong wording.
