---
name: rag
description: "Skill for the Rag area of insurance_rag. 147 symbols across 19 files."
---

# Rag

147 symbols | 19 files | Cohesion: 78%

## When to Use

- Working with code in `rag/`
- Understanding how require_api_key, classify_by_chunk_id, answer_refuses work
- Modifying rag-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `rag/retrieval.py` | tokenize, provenance_of, build_where, matches_filters, __init__ (+16) |
| `rag/chunking.py` | get_encoding, count_tokens, _token_pieces, _recursive_split, _sentence_split (+14) |
| `rag/indexing.py` | log, load_documents, indexed_fingerprints, sync_collection, load_or_build_collection (+11) |
| `rag/evaluation.py` | sweep_retrieval, sweep_chunking, format_table, render, evaluate_answers (+10) |
| `evaluate.py` | rewrite_transform, hyde_transform, command_retrieval, command_sweep_retrieval, command_sweep_chunking (+5) |
| `rag/diagnostics.py` | _describe, classify_by_chunk_id, answer_refuses, classify_with_judge, normalize_for_match (+4) |
| `rag/rerankers.py` | BaseReranker, NullReranker, LocalCrossEncoder, CohereReranker, describe (+4) |
| `rag/generation.py` | extract_citations, verify_citations, is_generation_error, is_refusal, generate_answer (+3) |
| `rag/engine.py` | ask, retrieve, prepare, __init__, stream (+2) |
| `main.py` | describe_scores, print_trace, ask_question, build_filters, tolerate_console_encoding (+2) |

## Entry Points

Start here when exploring this area:

- **`require_api_key`** (Function) — `rag/config.py:207`
- **`classify_by_chunk_id`** (Function) — `rag/diagnostics.py:131`
- **`answer_refuses`** (Function) — `rag/diagnostics.py:340`
- **`classify_with_judge`** (Function) — `rag/diagnostics.py:493`
- **`extract_citations`** (Function) — `rag/generation.py:147`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `BaseReranker` | Class | `rag/rerankers.py` | 35 |
| `NullReranker` | Class | `rag/rerankers.py` | 69 |
| `LocalCrossEncoder` | Class | `rag/rerankers.py` | 83 |
| `CohereReranker` | Class | `rag/rerankers.py` | 122 |
| `require_api_key` | Function | `rag/config.py` | 207 |
| `classify_by_chunk_id` | Function | `rag/diagnostics.py` | 131 |
| `answer_refuses` | Function | `rag/diagnostics.py` | 340 |
| `classify_with_judge` | Function | `rag/diagnostics.py` | 493 |
| `extract_citations` | Function | `rag/generation.py` | 147 |
| `verify_citations` | Function | `rag/generation.py` | 156 |
| `is_generation_error` | Function | `rag/generation.py` | 190 |
| `is_refusal` | Function | `rag/generation.py` | 202 |
| `generate_answer` | Function | `rag/generation.py` | 249 |
| `get_client` | Function | `rag/llm.py` | 14 |
| `run` | Function | `tools/run_bonus.py` | 81 |
| `main` | Function | `tools/run_bonus.py` | 132 |
| `run_generation` | Function | `tools/run_task_d.py` | 273 |
| `run_arm` | Function | `tools/run_week4.py` | 92 |
| `get_encoding` | Function | `rag/chunking.py` | 73 |
| `count_tokens` | Function | `rag/chunking.py` | 83 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Run_generation → Require_api_key` | cross_community | 8 |
| `Stream → Require_api_key` | cross_community | 7 |
| `Chat → Require_api_key` | cross_community | 6 |
| `Main → _line_stream` | cross_community | 6 |
| `Main → Close` | cross_community | 6 |
| `Run_generation → _build` | cross_community | 6 |
| `Run_generation → Format_pages` | cross_community | 6 |
| `Command_sweep_chunking → Index_signature` | cross_community | 6 |
| `Main → Index_signature` | cross_community | 6 |
| `Main → Is_page_furniture` | cross_community | 6 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tools | 8 calls |

## How to Explore

1. `context({name: "require_api_key"})` — see callers and callees
2. `query({search_query: "rag"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings (source→sink data flows), when indexed with `--pdg`
