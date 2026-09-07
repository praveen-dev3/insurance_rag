---
name: cluster-25
description: "Skill for the Cluster_25 area of insurance_rag. 7 symbols across 1 files."
---

# Cluster_25

7 symbols | 1 files | Cohesion: 92%

## When to Use

- Understanding how get_engine, sse, chat work
- Modifying cluster_25-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `server.py` | as_dict, get_engine, sse, chat, event_stream (+2) |

## Entry Points

Start here when exploring this area:

- **`get_engine`** (Function) — `server.py:138`
- **`sse`** (Function) — `server.py:185`
- **`chat`** (Function) — `server.py:194`
- **`event_stream`** (Function) — `server.py:237`
- **`reindex`** (Function) — `server.py:305`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `get_engine` | Function | `server.py` | 138 |
| `sse` | Function | `server.py` | 185 |
| `chat` | Function | `server.py` | 194 |
| `event_stream` | Function | `server.py` | 237 |
| `reindex` | Function | `server.py` | 305 |
| `as_dict` | Method | `server.py` | 58 |
| `_diagnose` | Function | `server.py` | 284 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Chat → Require_api_key` | cross_community | 6 |
| `Chat → Answer_refuses` | cross_community | 5 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Rag | 1 calls |

## How to Explore

1. `context({name: "get_engine"})` — see callers and callees
2. `query({search_query: "cluster_25"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings (source→sink data flows), when indexed with `--pdg`
