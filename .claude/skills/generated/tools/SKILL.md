---
name: tools
description: "Skill for the Tools area of insurance_rag. 37 symbols across 9 files."
---

# Tools

37 symbols | 9 files | Cohesion: 71%

## When to Use

- Working with code in `tools/`
- Understanding how open_collection, resolve, main work
- Modifying tools-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `tools/run_week4.py` | load_cases, top3_diversity, run_mmr_sweep, compare_arms, save (+4) |
| `tools/run_task_d.py` | load_cases, is_hit, dump_row, run_chunking_comparison, run_filter_demo (+2) |
| `tools/make_endorsements.py` | render_row, render_table, running_header, build_story, write_pdf (+1) |
| `tools/chunk_report.py` | endorsement_files, canonical_rows, audit, main |
| `tools/build_w4_golden.py` | build_index, resolve_anchor, main |
| `tools/prepare_corpus.py` | restore_base_wording, corpus_files, prepare |
| `tools/resolve_chunk.py` | resolve, main |
| `rag/rerankers.py` | _build, get_reranker |
| `rag/indexing.py` | open_collection |

## Entry Points

Start here when exploring this area:

- **`open_collection`** (Function) — `rag/indexing.py:347`
- **`resolve`** (Function) — `tools/resolve_chunk.py:41`
- **`main`** (Function) — `tools/resolve_chunk.py:59`
- **`load_cases`** (Function) — `tools/run_week4.py:79`
- **`top3_diversity`** (Function) — `tools/run_week4.py:188`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `open_collection` | Function | `rag/indexing.py` | 347 |
| `resolve` | Function | `tools/resolve_chunk.py` | 41 |
| `main` | Function | `tools/resolve_chunk.py` | 59 |
| `load_cases` | Function | `tools/run_week4.py` | 79 |
| `top3_diversity` | Function | `tools/run_week4.py` | 188 |
| `run_mmr_sweep` | Function | `tools/run_week4.py` | 210 |
| `compare_arms` | Function | `tools/run_week4.py` | 364 |
| `save` | Function | `tools/run_week4.py` | 397 |
| `main` | Function | `tools/run_week4.py` | 405 |
| `load_cases` | Function | `tools/run_task_d.py` | 53 |
| `is_hit` | Function | `tools/run_task_d.py` | 69 |
| `dump_row` | Function | `tools/run_task_d.py` | 90 |
| `run_chunking_comparison` | Function | `tools/run_task_d.py` | 117 |
| `run_filter_demo` | Function | `tools/run_task_d.py` | 218 |
| `save` | Function | `tools/run_task_d.py` | 368 |
| `main` | Function | `tools/run_task_d.py` | 383 |
| `build_index` | Function | `tools/build_w4_golden.py` | 162 |
| `resolve_anchor` | Function | `tools/build_w4_golden.py` | 177 |
| `main` | Function | `tools/build_w4_golden.py` | 213 |
| `restore_base_wording` | Function | `tools/prepare_corpus.py` | 43 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Main → Render_row` | cross_community | 7 |
| `Main → _line_stream` | cross_community | 6 |
| `Main → Close` | cross_community | 6 |
| `Run_generation → _build` | cross_community | 6 |
| `Main → Index_signature` | cross_community | 6 |
| `Main → Is_page_furniture` | cross_community | 6 |
| `Main → Running_header` | cross_community | 5 |
| `Main → Index_signature` | cross_community | 5 |
| `Main → Log` | cross_community | 5 |
| `Main → Extract_document_metadata` | cross_community | 5 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Rag | 13 calls |

## How to Explore

1. `context({name: "open_collection"})` — see callers and callees
2. `query({search_query: "tools"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings (source→sink data flows), when indexed with `--pdg`
