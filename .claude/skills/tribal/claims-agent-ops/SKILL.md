---
name: claims-agent-ops
description: Tribal knowledge for the claims-triage agent and its tooling (tools/w7d_* through w12_*). Use when running or editing the agent evals, the MCP servers, the request logs, or anything that spends Groq tokens.
---

# claims-agent-ops

## The Groq free tier is the scheduler

- Each model has its own **200,000 tokens/day** bucket (refills continuously, ~2.3 tokens/s) and **8,000 tokens/minute**. A triage costs 7-11k tokens, so a day is ~18-28 claims. A 12-case x 2-trial suite on `gpt-oss-20b` spends the whole day; the 429 body says `Limit 200000, Used N`.
- Models are separate buckets: when `openai/gpt-oss-20b` is spent, `openai/gpt-oss-120b` and `qwen/qwen3.8-27b` still answer (tool calling works on both). `LLM_MODEL` is read **once at import** in `tools/w7d_common.py`; set it before importing anything.
- The failure the Week 11 drill is built on **only reproduces on gpt-oss-20b** (c11 passes on 120b and on qwen under the unfixed prompt). A suite run for a 20b failure must run on 20b.
- `call_llm` sleeps whatever the 429 says. Do not let a wall-clock budget score that wait as a failed case (the suites now lift the cap and refuse to record a run that still hit it).
- Every suite/eval runner here is **resumable** - it writes each finished case before starting the next. Keep it that way; a crash on case 26 must not cost cases 1-25.

## MCP over stdio (tools/w9d_mcp.py, w12_mcp.py)

- stdout is the protocol. Anything printed during a handler (the `RagEngine` prints index progress, "Loading ...") corrupts the stream and shows up as `JSONDecodeError` in the *client* at `initialize`. Divert stdout to stderr, including during warm-up.
- An unread `stderr=PIPE` deadlocks a chatty server. Send it to a file.
- Warm the engine at server boot; a cold first search is ~75 s and will look like a hung tool call.
- `rag.config` reads `DOCUMENTS_FOLDER` / `CHROMA_PATH` / `COLLECTION_NAME` at import. The capstone corpus (`insurance_docs_w12/`, `chroma_db_w12/`) is selected by `tools/w12_retrieval.py` setting them first - it must be the first importer of `rag` in the process.

## Logs and PII

- Redaction happens in `RequestSink.write` (reusing `rag/tracing.py`'s `Redactor`, loaded by file path so `import rag` - chromadb, torch - is not triggered). The adjuster note is never stored, only its sha256 and length.
- `Redactor` only recognises `CLM-YYYY-NNNNN`. `CLM-7001` (Week 7) is not redacted unless registered; `RequestSink.register_claim` does that per request.
- The PII audit (`w12 pii`) searches for *known* literals. It cannot find a name nobody registered. Say so when quoting "0 leaks".

## Versions

- A fix is a pair: `prompt_version` + `retrieval_version`, both logged on every request with the prompt's sha256. Bump both when either changes; a replay (`w12 replay`) uses the logged retrieval version, because replaying with today's code reports drift as if it were a bug.
- Keep **retrieval** and **generation** failures separate. Week 11's c11 had both: v1 never showed E-34/E-36 (retrieval; fixed by `kw-r2`), then v2 showed them and gpt-oss-20b still read "pitted" as a breach (generation; prompt v3). A retrieval fix that leaves the case red has not failed - it has exposed the second cause.
