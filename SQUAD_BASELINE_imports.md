# SQUAD_BASELINE_imports.md — `rag/` import surface map

Frozen at commit `933d926` (branch `master`). Read-only measurement; no source file was modified.

**Method.** Every `.py` in `rag/`, `tools/`, plus `main.py`, `server.py`, `evaluate.py` was parsed
with Python's `ast` module (not regex) and every `ImportFrom` whose module is `rag` or `rag.*` was
recorded, including multi-line parenthesised imports. A module's own internal imports are excluded,
so every row below is a genuine **cross-module** dependency.

Additional checks, all negative:

- `from rag import ...` — **zero occurrences** anywhere. `rag/__init__.py` re-exports
  `RagEngine`, `RetrievedChunk`, `format_pages`, but nothing in the repo consumes the package root.
- `import rag` / `import rag.X` — **zero occurrences** (the `python -c "import rag, ..."` health check aside).
- `rag.X.Y` attribute access — only 3 hits, all inside comments/docstrings
  (`rag/claims.py:92`, `rag/config.py:124`, `rag/config.py:183`). No runtime attribute-path coupling.
- No `.py` files exist outside `rag/`, `tools/` and the three root front ends.

---

## 1. Per-module import surface

Each row: a symbol exported by that module, and every file outside the module that imports it.

### `rag/__init__.py`

_No symbol is imported from this module by any other file._

(It is the package root: it *re-exports* `RagEngine`, `RetrievedChunk`, `format_pages` from `rag.engine`, but no file imports from it.)

### `rag/assertions.py`

| symbol | # importers | imported by |
|---|---|---|
| `ASSERTIONS` | 1 | `tools/run_w6.py` |
| `run_assertions` | 1 | `tools/run_w6.py` |

### `rag/chunking.py`

| symbol | # importers | imported by |
|---|---|---|
| `CHUNK_STRATEGIES` | 3 | `main.py`, `rag/engine.py`, `rag/evaluation.py` |
| `create_chunks` | 2 | `rag/indexing.py`, `tools/chunk_report.py` |
| `_parse_units` | 1 | `tools/chunk_report.py` |

### `rag/claims.py`

| symbol | # importers | imported by |
|---|---|---|
| `ClaimFile` | 2 | `tools/run_w6.py`, `tools/w5_traffic.py` |
| `SUMMARY_PROMPT` | 2 | `tools/w5_replay.py`, `tools/w5_traffic.py` |
| `SUMMARY_PROMPT_VERSION` | 2 | `tools/run_w6.py`, `tools/w5_traffic.py` |
| `build_summary_prompt` | 2 | `tools/w5_replay.py`, `tools/w5_traffic.py` |
| `coverage_position` | 2 | `rag/assertions.py`, `tools/run_w6.py` |
| `generate_summary` | 2 | `tools/run_w6.py`, `tools/w5_traffic.py` |
| `build_context` | 1 | `tools/run_w6.py` |
| `parse_summary` | 1 | `rag/assertions.py` |

### `rag/config.py`

| symbol | # importers | imported by |
|---|---|---|
| `CHROMA_PATH` | 8 | `rag/engine.py`, `rag/indexing.py`, `tools/build_w4_golden.py`, `tools/resolve_chunk.py`, `tools/run_bonus.py`, `tools/run_task_d.py`, `tools/run_week4.py`, `tools/w5_replay.py` |
| `TOP_K` | 8 | `evaluate.py`, `main.py`, `rag/engine.py`, `rag/evaluation.py`, `rag/retrieval.py`, `server.py`, `tools/run_w6.py`, `tools/w5_traffic.py` |
| `LLM_MODEL` | 4 | `rag/claims.py`, `rag/engine.py`, `rag/generation.py`, `tools/w5_traffic.py` |
| `MMR_LAMBDA` | 4 | `main.py`, `rag/engine.py`, `rag/retrieval.py`, `server.py` |
| `MMR_POOL` | 4 | `main.py`, `rag/engine.py`, `rag/retrieval.py`, `server.py` |
| `CHUNK_SIZE` | 3 | `main.py`, `rag/chunking.py`, `rag/engine.py` |
| `CHUNK_STRATEGY` | 3 | `main.py`, `rag/chunking.py`, `rag/engine.py` |
| `COLLECTION_NAME` | 3 | `rag/indexing.py`, `tools/resolve_chunk.py`, `tools/w5_replay.py` |
| `DEFAULT_MODE` | 3 | `rag/engine.py`, `tools/run_w6.py`, `tools/w5_traffic.py` |
| `CHUNK_OVERLAP` | 2 | `rag/chunking.py`, `rag/engine.py` |
| `EMBEDDING_MODEL` | 2 | `rag/embeddings.py`, `rag/engine.py` |
| `GOLDEN_SET_PATH` | 2 | `evaluate.py`, `rag/evaluation.py` |
| `MIN_RERANK_SCORE` | 2 | `rag/engine.py`, `rag/rerankers.py` |
| `REASONING_EFFORT` | 2 | `rag/claims.py`, `rag/generation.py` |
| `RERANKER` | 2 | `rag/engine.py`, `rag/rerankers.py` |
| `USE_MMR` | 2 | `rag/engine.py`, `rag/retrieval.py` |
| `UTILITY_MODEL` | 2 | `rag/diagnostics.py`, `rag/query.py` |
| `COHERE_API_KEY` | 1 | `rag/rerankers.py` |
| `COHERE_RERANK_MODEL` | 1 | `rag/rerankers.py` |
| `CROSS_ENCODER_MODEL` | 1 | `rag/rerankers.py` |
| `DENSE_TOP_K` | 1 | `rag/retrieval.py` |
| `DOCUMENTS_FOLDER` | 1 | `rag/indexing.py` |
| `EVAL_RESULTS_PATH` | 1 | `evaluate.py` |
| `GROQ_BASE_URL` | 1 | `rag/llm.py` |
| `HNSW_EF_CONSTRUCTION` | 1 | `rag/indexing.py` |
| `HNSW_EF_SEARCH` | 1 | `rag/indexing.py` |
| `HNSW_MAX_NEIGHBORS` | 1 | `rag/indexing.py` |
| `HNSW_SPACE` | 1 | `rag/indexing.py` |
| `JUDGE_MODEL` | 1 | `rag/judge.py` |
| `MAX_RATE_LIMIT_WAIT` | 1 | `rag/llm.py` |
| `RATE_LIMIT_RETRIES` | 1 | `rag/llm.py` |
| `RERANK_CANDIDATES` | 1 | `rag/retrieval.py` |
| `RRF_K` | 1 | `rag/retrieval.py` |
| `SENTENCE_OVERLAP` | 1 | `rag/chunking.py` |
| `SPARSE_TOP_K` | 1 | `rag/retrieval.py` |
| `USE_HYDE` | 1 | `rag/engine.py` |
| `USE_QUERY_REWRITE` | 1 | `rag/engine.py` |
| `index_signature` | 1 | `rag/indexing.py` |
| `require_api_key` | 1 | `rag/llm.py` |

### `rag/diagnostics.py`

| symbol | # importers | imported by |
|---|---|---|
| `classify_with_judge` | 3 | `main.py`, `rag/engine.py`, `server.py` |
| `EXPLANATIONS` | 1 | `server.py` |
| `LABELS` | 1 | `rag/evaluation.py` |
| `TASK_LABELS` | 1 | `tools/run_week4.py` |
| `classify_by_chunk_id` | 1 | `tools/run_week4.py` |
| `classify_with_ground_truth` | 1 | `rag/evaluation.py` |

### `rag/embeddings.py`

| symbol | # importers | imported by |
|---|---|---|
| `get_embedder` | 4 | `rag/engine.py`, `rag/indexing.py`, `rag/retrieval.py`, `server.py` |
| `EMBEDDING_MODELS` | 1 | `rag/engine.py` |

### `rag/engine.py`

| symbol | # importers | imported by |
|---|---|---|
| `RagEngine` | 8 | `evaluate.py`, `main.py`, `rag/__init__.py`, `server.py`, `tools/run_task_d.py`, `tools/run_w6.py`, `tools/w5_replay.py`, `tools/w5_traffic.py` |
| `RetrievedChunk` | 1 | `rag/__init__.py` |
| `format_pages` | 1 | `rag/__init__.py` |

### `rag/evaluation.py`

| symbol | # importers | imported by |
|---|---|---|
| `load_golden_set` | 2 | `evaluate.py`, `server.py` |
| `compare` | 1 | `evaluate.py` |
| `evaluate_answers` | 1 | `evaluate.py` |
| `evaluate_retrieval` | 1 | `evaluate.py` |
| `format_table` | 1 | `evaluate.py` |
| `latency_summary` | 1 | `tools/run_week4.py` |
| `save_results` | 1 | `evaluate.py` |
| `sweep_chunking` | 1 | `evaluate.py` |
| `sweep_retrieval` | 1 | `evaluate.py` |

### `rag/generation.py`

| symbol | # importers | imported by |
|---|---|---|
| `generate_answer` | 5 | `rag/engine.py`, `tools/run_bonus.py`, `tools/run_week4.py`, `tools/w5_replay.py`, `tools/w5_traffic.py` |
| `is_generation_error` | 4 | `tools/run_bonus.py`, `tools/run_task_d.py`, `tools/run_w6.py`, `tools/run_week4.py` |
| `NO_ANSWER` | 3 | `rag/diagnostics.py`, `rag/engine.py`, `tools/run_task_d.py` |
| `build_prompt` | 2 | `tools/w5_replay.py`, `tools/w5_traffic.py` |
| `stream_answer` | 2 | `main.py`, `rag/engine.py` |
| `verify_citations` | 2 | `tools/run_task_d.py`, `tools/w5_traffic.py` |
| `ANSWER_PROMPT_VERSION` | 1 | `tools/w5_traffic.py` |
| `GENERATION_ERROR` | 1 | `rag/claims.py` |
| `is_refusal` | 1 | `tools/run_task_d.py` |

### `rag/indexing.py`

| symbol | # importers | imported by |
|---|---|---|
| `build_collection` | 4 | `rag/evaluation.py`, `tools/build_w4_golden.py`, `tools/run_bonus.py`, `tools/run_task_d.py` |
| `open_collection` | 3 | `tools/resolve_chunk.py`, `tools/run_week4.py`, `tools/w5_replay.py` |
| `load_documents` | 1 | `tools/chunk_report.py` |
| `load_or_build_collection` | 1 | `rag/engine.py` |

### `rag/judge.py`

| symbol | # importers | imported by |
|---|---|---|
| `CRITERION` | 1 | `tools/run_w6.py` |
| `Verdict` | 1 | `tools/run_w6.py` |
| `agreement` | 1 | `tools/run_w6.py` |
| `judge_summary` | 1 | `tools/run_w6.py` |
| `load_judge_prompt` | 1 | `tools/run_w6.py` |

### `rag/llm.py`

| symbol | # importers | imported by |
|---|---|---|
| `complete` | 6 | `rag/claims.py`, `rag/generation.py`, `rag/judge.py`, `rag/query.py`, `tools/w5_replay.py`, `tools/w6_ragas.py` |
| `get_client` | 2 | `rag/diagnostics.py`, `rag/generation.py` |

### `rag/metadata.py`

| symbol | # importers | imported by |
|---|---|---|
| `UNSPECIFIED` | 3 | `rag/chunking.py`, `rag/indexing.py`, `rag/retrieval.py` |
| `CLAUSE_HEADING` | 1 | `rag/chunking.py` |
| `TABLE_COLUMNS` | 1 | `rag/chunking.py` |
| `TABLE_HEADING` | 1 | `rag/chunking.py` |
| `TABLE_NOTE` | 1 | `rag/chunking.py` |
| `clause_label` | 1 | `rag/chunking.py` |
| `clause_of` | 1 | `rag/chunking.py` |
| `exclusion_code` | 1 | `rag/chunking.py` |
| `extract_document_metadata` | 1 | `rag/indexing.py` |
| `strip_page_furniture` | 1 | `rag/indexing.py` |

### `rag/query.py`

| symbol | # importers | imported by |
|---|---|---|
| `HISTORY_TURNS` | 1 | `rag/generation.py` |
| `hyde_document` | 1 | `evaluate.py` |
| `rewrite_query` | 1 | `evaluate.py` |
| `transform` | 1 | `rag/engine.py` |

### `rag/rerankers.py`

| symbol | # importers | imported by |
|---|---|---|
| `get_reranker` | 5 | `evaluate.py`, `rag/engine.py`, `rag/retrieval.py`, `server.py`, `tools/run_week4.py` |
| `RERANKERS` | 3 | `main.py`, `rag/engine.py`, `server.py` |

### `rag/retrieval.py`

| symbol | # importers | imported by |
|---|---|---|
| `HybridRetriever` | 5 | `rag/engine.py`, `rag/evaluation.py`, `tools/run_bonus.py`, `tools/run_task_d.py`, `tools/run_week4.py` |
| `format_pages` | 4 | `main.py`, `rag/claims.py`, `rag/engine.py`, `rag/generation.py` |
| `RETRIEVAL_MODES` | 3 | `main.py`, `rag/engine.py`, `server.py` |
| `RetrievedChunk` | 2 | `rag/engine.py`, `tools/w5_replay.py` |
| `RetrievalTrace` | 1 | `rag/engine.py` |
| `UNSPECIFIED` | 1 | `tools/w5_replay.py` |

### `rag/tracing.py`

| symbol | # importers | imported by |
|---|---|---|
| `DEFAULT_TRACE_PATH` | 4 | `tools/w5_read.py`, `tools/w5_replay.py`, `tools/w5_sample.py`, `tools/w5_traffic.py` |
| `read_traces` | 3 | `tools/w5_read.py`, `tools/w5_replay.py`, `tools/w5_sample.py` |
| `Redactor` | 2 | `tools/run_w6.py`, `tools/w5_traffic.py` |
| `index_traces` | 2 | `tools/w5_read.py`, `tools/w5_replay.py` |
| `sha256_short` | 2 | `tools/w5_replay.py`, `tools/w5_traffic.py` |
| `TraceWriter` | 1 | `tools/w5_traffic.py` |
| `prompt_fingerprint` | 1 | `tools/w5_traffic.py` |

---

## 2. Symbols with 2+ external importers — the mandatory re-export set

**These are the refactor's hard contract.** If a symbol below stops being importable from the
module path shown, at least two call sites break.

Count: **51** symbols.

| # importers | symbol | defining module | imported by |
|---|---|---|---|
| 8 | `CHROMA_PATH` | `rag.config` | `rag/engine.py`, `rag/indexing.py`, `tools/build_w4_golden.py`, `tools/resolve_chunk.py`, `tools/run_bonus.py`, `tools/run_task_d.py`, `tools/run_week4.py`, `tools/w5_replay.py` |
| 8 | `TOP_K` | `rag.config` | `evaluate.py`, `main.py`, `rag/engine.py`, `rag/evaluation.py`, `rag/retrieval.py`, `server.py`, `tools/run_w6.py`, `tools/w5_traffic.py` |
| 8 | `RagEngine` | `rag.engine` | `evaluate.py`, `main.py`, `rag/__init__.py`, `server.py`, `tools/run_task_d.py`, `tools/run_w6.py`, `tools/w5_replay.py`, `tools/w5_traffic.py` |
| 6 | `complete` | `rag.llm` | `rag/claims.py`, `rag/generation.py`, `rag/judge.py`, `rag/query.py`, `tools/w5_replay.py`, `tools/w6_ragas.py` |
| 5 | `generate_answer` | `rag.generation` | `rag/engine.py`, `tools/run_bonus.py`, `tools/run_week4.py`, `tools/w5_replay.py`, `tools/w5_traffic.py` |
| 5 | `get_reranker` | `rag.rerankers` | `evaluate.py`, `rag/engine.py`, `rag/retrieval.py`, `server.py`, `tools/run_week4.py` |
| 5 | `HybridRetriever` | `rag.retrieval` | `rag/engine.py`, `rag/evaluation.py`, `tools/run_bonus.py`, `tools/run_task_d.py`, `tools/run_week4.py` |
| 4 | `LLM_MODEL` | `rag.config` | `rag/claims.py`, `rag/engine.py`, `rag/generation.py`, `tools/w5_traffic.py` |
| 4 | `MMR_LAMBDA` | `rag.config` | `main.py`, `rag/engine.py`, `rag/retrieval.py`, `server.py` |
| 4 | `MMR_POOL` | `rag.config` | `main.py`, `rag/engine.py`, `rag/retrieval.py`, `server.py` |
| 4 | `get_embedder` | `rag.embeddings` | `rag/engine.py`, `rag/indexing.py`, `rag/retrieval.py`, `server.py` |
| 4 | `is_generation_error` | `rag.generation` | `tools/run_bonus.py`, `tools/run_task_d.py`, `tools/run_w6.py`, `tools/run_week4.py` |
| 4 | `build_collection` | `rag.indexing` | `rag/evaluation.py`, `tools/build_w4_golden.py`, `tools/run_bonus.py`, `tools/run_task_d.py` |
| 4 | `format_pages` | `rag.retrieval` | `main.py`, `rag/claims.py`, `rag/engine.py`, `rag/generation.py` |
| 4 | `DEFAULT_TRACE_PATH` | `rag.tracing` | `tools/w5_read.py`, `tools/w5_replay.py`, `tools/w5_sample.py`, `tools/w5_traffic.py` |
| 3 | `CHUNK_STRATEGIES` | `rag.chunking` | `main.py`, `rag/engine.py`, `rag/evaluation.py` |
| 3 | `CHUNK_SIZE` | `rag.config` | `main.py`, `rag/chunking.py`, `rag/engine.py` |
| 3 | `CHUNK_STRATEGY` | `rag.config` | `main.py`, `rag/chunking.py`, `rag/engine.py` |
| 3 | `COLLECTION_NAME` | `rag.config` | `rag/indexing.py`, `tools/resolve_chunk.py`, `tools/w5_replay.py` |
| 3 | `DEFAULT_MODE` | `rag.config` | `rag/engine.py`, `tools/run_w6.py`, `tools/w5_traffic.py` |
| 3 | `classify_with_judge` | `rag.diagnostics` | `main.py`, `rag/engine.py`, `server.py` |
| 3 | `NO_ANSWER` | `rag.generation` | `rag/diagnostics.py`, `rag/engine.py`, `tools/run_task_d.py` |
| 3 | `open_collection` | `rag.indexing` | `tools/resolve_chunk.py`, `tools/run_week4.py`, `tools/w5_replay.py` |
| 3 | `UNSPECIFIED` | `rag.metadata` | `rag/chunking.py`, `rag/indexing.py`, `rag/retrieval.py` |
| 3 | `RERANKERS` | `rag.rerankers` | `main.py`, `rag/engine.py`, `server.py` |
| 3 | `RETRIEVAL_MODES` | `rag.retrieval` | `main.py`, `rag/engine.py`, `server.py` |
| 3 | `read_traces` | `rag.tracing` | `tools/w5_read.py`, `tools/w5_replay.py`, `tools/w5_sample.py` |
| 2 | `create_chunks` | `rag.chunking` | `rag/indexing.py`, `tools/chunk_report.py` |
| 2 | `ClaimFile` | `rag.claims` | `tools/run_w6.py`, `tools/w5_traffic.py` |
| 2 | `SUMMARY_PROMPT` | `rag.claims` | `tools/w5_replay.py`, `tools/w5_traffic.py` |
| 2 | `SUMMARY_PROMPT_VERSION` | `rag.claims` | `tools/run_w6.py`, `tools/w5_traffic.py` |
| 2 | `build_summary_prompt` | `rag.claims` | `tools/w5_replay.py`, `tools/w5_traffic.py` |
| 2 | `coverage_position` | `rag.claims` | `rag/assertions.py`, `tools/run_w6.py` |
| 2 | `generate_summary` | `rag.claims` | `tools/run_w6.py`, `tools/w5_traffic.py` |
| 2 | `CHUNK_OVERLAP` | `rag.config` | `rag/chunking.py`, `rag/engine.py` |
| 2 | `EMBEDDING_MODEL` | `rag.config` | `rag/embeddings.py`, `rag/engine.py` |
| 2 | `GOLDEN_SET_PATH` | `rag.config` | `evaluate.py`, `rag/evaluation.py` |
| 2 | `MIN_RERANK_SCORE` | `rag.config` | `rag/engine.py`, `rag/rerankers.py` |
| 2 | `REASONING_EFFORT` | `rag.config` | `rag/claims.py`, `rag/generation.py` |
| 2 | `RERANKER` | `rag.config` | `rag/engine.py`, `rag/rerankers.py` |
| 2 | `USE_MMR` | `rag.config` | `rag/engine.py`, `rag/retrieval.py` |
| 2 | `UTILITY_MODEL` | `rag.config` | `rag/diagnostics.py`, `rag/query.py` |
| 2 | `load_golden_set` | `rag.evaluation` | `evaluate.py`, `server.py` |
| 2 | `build_prompt` | `rag.generation` | `tools/w5_replay.py`, `tools/w5_traffic.py` |
| 2 | `stream_answer` | `rag.generation` | `main.py`, `rag/engine.py` |
| 2 | `verify_citations` | `rag.generation` | `tools/run_task_d.py`, `tools/w5_traffic.py` |
| 2 | `get_client` | `rag.llm` | `rag/diagnostics.py`, `rag/generation.py` |
| 2 | `RetrievedChunk` | `rag.retrieval` | `rag/engine.py`, `tools/w5_replay.py` |
| 2 | `Redactor` | `rag.tracing` | `tools/run_w6.py`, `tools/w5_traffic.py` |
| 2 | `index_traces` | `rag.tracing` | `tools/w5_read.py`, `tools/w5_replay.py` |
| 2 | `sha256_short` | `rag.tracing` | `tools/w5_replay.py`, `tools/w5_traffic.py` |

### Same set, compact (for a checklist)

```
CHROMA_PATH (rag.config) <- 8 importers
TOP_K (rag.config) <- 8 importers
RagEngine (rag.engine) <- 8 importers
complete (rag.llm) <- 6 importers
generate_answer (rag.generation) <- 5 importers
get_reranker (rag.rerankers) <- 5 importers
HybridRetriever (rag.retrieval) <- 5 importers
LLM_MODEL (rag.config) <- 4 importers
MMR_LAMBDA (rag.config) <- 4 importers
MMR_POOL (rag.config) <- 4 importers
get_embedder (rag.embeddings) <- 4 importers
is_generation_error (rag.generation) <- 4 importers
build_collection (rag.indexing) <- 4 importers
format_pages (rag.retrieval) <- 4 importers
DEFAULT_TRACE_PATH (rag.tracing) <- 4 importers
CHUNK_STRATEGIES (rag.chunking) <- 3 importers
CHUNK_SIZE (rag.config) <- 3 importers
CHUNK_STRATEGY (rag.config) <- 3 importers
COLLECTION_NAME (rag.config) <- 3 importers
DEFAULT_MODE (rag.config) <- 3 importers
classify_with_judge (rag.diagnostics) <- 3 importers
NO_ANSWER (rag.generation) <- 3 importers
open_collection (rag.indexing) <- 3 importers
UNSPECIFIED (rag.metadata) <- 3 importers
RERANKERS (rag.rerankers) <- 3 importers
RETRIEVAL_MODES (rag.retrieval) <- 3 importers
read_traces (rag.tracing) <- 3 importers
create_chunks (rag.chunking) <- 2 importers
ClaimFile (rag.claims) <- 2 importers
SUMMARY_PROMPT (rag.claims) <- 2 importers
SUMMARY_PROMPT_VERSION (rag.claims) <- 2 importers
build_summary_prompt (rag.claims) <- 2 importers
coverage_position (rag.claims) <- 2 importers
generate_summary (rag.claims) <- 2 importers
CHUNK_OVERLAP (rag.config) <- 2 importers
EMBEDDING_MODEL (rag.config) <- 2 importers
GOLDEN_SET_PATH (rag.config) <- 2 importers
MIN_RERANK_SCORE (rag.config) <- 2 importers
REASONING_EFFORT (rag.config) <- 2 importers
RERANKER (rag.config) <- 2 importers
USE_MMR (rag.config) <- 2 importers
UTILITY_MODEL (rag.config) <- 2 importers
load_golden_set (rag.evaluation) <- 2 importers
build_prompt (rag.generation) <- 2 importers
stream_answer (rag.generation) <- 2 importers
verify_citations (rag.generation) <- 2 importers
get_client (rag.llm) <- 2 importers
RetrievedChunk (rag.retrieval) <- 2 importers
Redactor (rag.tracing) <- 2 importers
index_traces (rag.tracing) <- 2 importers
sha256_short (rag.tracing) <- 2 importers
```

### Single-importer symbols (still public API — 1 break each)

Count: **70** symbols. Lower risk, but each one still has a live caller.

| symbol | defining module | sole importer |
|---|---|---|
| `ASSERTIONS` | `rag.assertions` | `tools/run_w6.py` |
| `run_assertions` | `rag.assertions` | `tools/run_w6.py` |
| `_parse_units` | `rag.chunking` | `tools/chunk_report.py` |
| `build_context` | `rag.claims` | `tools/run_w6.py` |
| `parse_summary` | `rag.claims` | `rag/assertions.py` |
| `COHERE_API_KEY` | `rag.config` | `rag/rerankers.py` |
| `COHERE_RERANK_MODEL` | `rag.config` | `rag/rerankers.py` |
| `CROSS_ENCODER_MODEL` | `rag.config` | `rag/rerankers.py` |
| `DENSE_TOP_K` | `rag.config` | `rag/retrieval.py` |
| `DOCUMENTS_FOLDER` | `rag.config` | `rag/indexing.py` |
| `EVAL_RESULTS_PATH` | `rag.config` | `evaluate.py` |
| `GROQ_BASE_URL` | `rag.config` | `rag/llm.py` |
| `HNSW_EF_CONSTRUCTION` | `rag.config` | `rag/indexing.py` |
| `HNSW_EF_SEARCH` | `rag.config` | `rag/indexing.py` |
| `HNSW_MAX_NEIGHBORS` | `rag.config` | `rag/indexing.py` |
| `HNSW_SPACE` | `rag.config` | `rag/indexing.py` |
| `JUDGE_MODEL` | `rag.config` | `rag/judge.py` |
| `MAX_RATE_LIMIT_WAIT` | `rag.config` | `rag/llm.py` |
| `RATE_LIMIT_RETRIES` | `rag.config` | `rag/llm.py` |
| `RERANK_CANDIDATES` | `rag.config` | `rag/retrieval.py` |
| `RRF_K` | `rag.config` | `rag/retrieval.py` |
| `SENTENCE_OVERLAP` | `rag.config` | `rag/chunking.py` |
| `SPARSE_TOP_K` | `rag.config` | `rag/retrieval.py` |
| `USE_HYDE` | `rag.config` | `rag/engine.py` |
| `USE_QUERY_REWRITE` | `rag.config` | `rag/engine.py` |
| `index_signature` | `rag.config` | `rag/indexing.py` |
| `require_api_key` | `rag.config` | `rag/llm.py` |
| `EXPLANATIONS` | `rag.diagnostics` | `server.py` |
| `LABELS` | `rag.diagnostics` | `rag/evaluation.py` |
| `TASK_LABELS` | `rag.diagnostics` | `tools/run_week4.py` |
| `classify_by_chunk_id` | `rag.diagnostics` | `tools/run_week4.py` |
| `classify_with_ground_truth` | `rag.diagnostics` | `rag/evaluation.py` |
| `EMBEDDING_MODELS` | `rag.embeddings` | `rag/engine.py` |
| `RetrievedChunk` | `rag.engine` | `rag/__init__.py` |
| `format_pages` | `rag.engine` | `rag/__init__.py` |
| `compare` | `rag.evaluation` | `evaluate.py` |
| `evaluate_answers` | `rag.evaluation` | `evaluate.py` |
| `evaluate_retrieval` | `rag.evaluation` | `evaluate.py` |
| `format_table` | `rag.evaluation` | `evaluate.py` |
| `latency_summary` | `rag.evaluation` | `tools/run_week4.py` |
| `save_results` | `rag.evaluation` | `evaluate.py` |
| `sweep_chunking` | `rag.evaluation` | `evaluate.py` |
| `sweep_retrieval` | `rag.evaluation` | `evaluate.py` |
| `ANSWER_PROMPT_VERSION` | `rag.generation` | `tools/w5_traffic.py` |
| `GENERATION_ERROR` | `rag.generation` | `rag/claims.py` |
| `is_refusal` | `rag.generation` | `tools/run_task_d.py` |
| `load_documents` | `rag.indexing` | `tools/chunk_report.py` |
| `load_or_build_collection` | `rag.indexing` | `rag/engine.py` |
| `CRITERION` | `rag.judge` | `tools/run_w6.py` |
| `Verdict` | `rag.judge` | `tools/run_w6.py` |
| `agreement` | `rag.judge` | `tools/run_w6.py` |
| `judge_summary` | `rag.judge` | `tools/run_w6.py` |
| `load_judge_prompt` | `rag.judge` | `tools/run_w6.py` |
| `CLAUSE_HEADING` | `rag.metadata` | `rag/chunking.py` |
| `TABLE_COLUMNS` | `rag.metadata` | `rag/chunking.py` |
| `TABLE_HEADING` | `rag.metadata` | `rag/chunking.py` |
| `TABLE_NOTE` | `rag.metadata` | `rag/chunking.py` |
| `clause_label` | `rag.metadata` | `rag/chunking.py` |
| `clause_of` | `rag.metadata` | `rag/chunking.py` |
| `exclusion_code` | `rag.metadata` | `rag/chunking.py` |
| `extract_document_metadata` | `rag.metadata` | `rag/indexing.py` |
| `strip_page_furniture` | `rag.metadata` | `rag/indexing.py` |
| `HISTORY_TURNS` | `rag.query` | `rag/generation.py` |
| `hyde_document` | `rag.query` | `evaluate.py` |
| `rewrite_query` | `rag.query` | `evaluate.py` |
| `transform` | `rag.query` | `rag/engine.py` |
| `RetrievalTrace` | `rag.retrieval` | `rag/engine.py` |
| `UNSPECIFIED` | `rag.retrieval` | `tools/w5_replay.py` |
| `TraceWriter` | `rag.tracing` | `tools/w5_traffic.py` |
| `prompt_fingerprint` | `rag.tracing` | `tools/w5_traffic.py` |

**Total cross-module symbols in the contract: 121** (51 with 2+ importers, 70 with exactly 1).

---

## 3. Module fan-in summary

| module | distinct symbols exported (imported elsewhere) | distinct importing files |
|---|---|---|
| `rag/config.py` | 39 | 24 |
| `rag/generation.py` | 9 | 10 |
| `rag/retrieval.py` | 6 | 10 |
| `rag/indexing.py` | 4 | 9 |
| `rag/engine.py` | 3 | 8 |
| `rag/llm.py` | 2 | 7 |
| `rag/rerankers.py` | 2 | 6 |
| `rag/tracing.py` | 7 | 5 |
| `rag/diagnostics.py` | 6 | 5 |
| `rag/chunking.py` | 3 | 5 |
| `rag/claims.py` | 8 | 4 |
| `rag/embeddings.py` | 2 | 4 |
| `rag/metadata.py` | 10 | 3 |
| `rag/evaluation.py` | 9 | 3 |
| `rag/query.py` | 4 | 3 |
| `rag/judge.py` | 5 | 1 |
| `rag/assertions.py` | 2 | 1 |
| `rag/__init__.py` | 0 | 0 |

---

## 4. Line counts

### All files, largest first

| file | lines |
|---|---|
| `rag/retrieval.py` | 1005 |
| `rag/chunking.py` | 708 |
| `rag/indexing.py` | 694 |
| `rag/evaluation.py` | 607 |
| `rag/tracing.py` | 576 |
| `rag/diagnostics.py` | 568 |
| `tools/endorsement_content.py` | 563 |
| `tools/run_week4.py` | 514 |
| `tools/run_w6.py` | 486 |
| `tools/claims_population.py` | 434 |
| `tools/run_task_d.py` | 421 |
| `main.py` | 407 |
| `rag/assertions.py` | 405 |
| `server.py` | 398 |
| `rag/claims.py` | 388 |
| `tools/w6_population.py` | 383 |
| `evaluate.py` | 343 |
| `tools/w5_replay.py` | 341 |
| `tools/make_endorsements.py` | 327 |
| `rag/generation.py` | 326 |
| `tools/w6_ragas.py` | 324 |
| `tools/w5_traffic.py` | 312 |
| `rag/engine.py` | 287 |
| `rag/metadata.py` | 285 |
| `tools/build_w4_golden.py` | 268 |
| `rag/config.py` | 263 |
| `rag/rerankers.py` | 226 |
| `rag/query.py` | 193 |
| `rag/judge.py` | 189 |
| `tools/run_bonus.py` | 176 |
| `tools/w5_taxonomy.py` | 175 |
| `rag/embeddings.py` | 168 |
| `tools/chunk_report.py` | 159 |
| `tools/w5_read.py` | 142 |
| `rag/llm.py` | 129 |
| `tools/prepare_corpus.py` | 128 |
| `tools/w5_sample.py` | 119 |
| `tools/resolve_chunk.py` | 105 |
| `tools/w6_label.py` | 71 |
| `rag/__init__.py` | 9 |
| **total** | **13622** |

### `rag/` (the library) — 18 files, 7026 lines

| file | lines |
|---|---|
| `rag/retrieval.py` | 1005 |
| `rag/chunking.py` | 708 |
| `rag/indexing.py` | 694 |
| `rag/evaluation.py` | 607 |
| `rag/tracing.py` | 576 |
| `rag/diagnostics.py` | 568 |
| `rag/assertions.py` | 405 |
| `rag/claims.py` | 388 |
| `rag/generation.py` | 326 |
| `rag/engine.py` | 287 |
| `rag/metadata.py` | 285 |
| `rag/config.py` | 263 |
| `rag/rerankers.py` | 226 |
| `rag/query.py` | 193 |
| `rag/judge.py` | 189 |
| `rag/embeddings.py` | 168 |
| `rag/llm.py` | 129 |
| `rag/__init__.py` | 9 |

### `tools/` (one-off week scripts) — 19 files, 5448 lines

| file | lines |
|---|---|
| `tools/endorsement_content.py` | 563 |
| `tools/run_week4.py` | 514 |
| `tools/run_w6.py` | 486 |
| `tools/claims_population.py` | 434 |
| `tools/run_task_d.py` | 421 |
| `tools/w6_population.py` | 383 |
| `tools/w5_replay.py` | 341 |
| `tools/make_endorsements.py` | 327 |
| `tools/w6_ragas.py` | 324 |
| `tools/w5_traffic.py` | 312 |
| `tools/build_w4_golden.py` | 268 |
| `tools/run_bonus.py` | 176 |
| `tools/w5_taxonomy.py` | 175 |
| `tools/chunk_report.py` | 159 |
| `tools/w5_read.py` | 142 |
| `tools/prepare_corpus.py` | 128 |
| `tools/w5_sample.py` | 119 |
| `tools/resolve_chunk.py` | 105 |
| `tools/w6_label.py` | 71 |

### Root front ends — 3 files, 1148 lines

| file | lines |
|---|---|
| `main.py` | 407 |
| `server.py` | 398 |
| `evaluate.py` | 343 |

