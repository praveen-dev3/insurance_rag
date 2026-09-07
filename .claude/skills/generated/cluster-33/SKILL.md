---
name: cluster-33
description: "Skill for the Cluster_33 area of insurance_rag. 8 symbols across 2 files."
---

# Cluster_33

8 symbols | 2 files | Cohesion: 88%

## When to Use

- Working with code in `frontend/`
- Understanding how reindex, streamChat, patchLast work
- Modifying cluster_33-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `frontend/src/api.ts` | readError, reindex, requestBody, streamChat |
| `frontend/src/App.tsx` | nextId, patchLast, send, runReindex |

## Entry Points

Start here when exploring this area:

- **`reindex`** (Function) — `frontend/src/api.ts:59`
- **`streamChat`** (Function) — `frontend/src/api.ts:123`
- **`patchLast`** (Function) — `frontend/src/App.tsx:110`
- **`send`** (Function) — `frontend/src/App.tsx:126`
- **`runReindex`** (Function) — `frontend/src/App.tsx:221`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `reindex` | Function | `frontend/src/api.ts` | 59 |
| `streamChat` | Function | `frontend/src/api.ts` | 123 |
| `patchLast` | Function | `frontend/src/App.tsx` | 110 |
| `send` | Function | `frontend/src/App.tsx` | 126 |
| `runReindex` | Function | `frontend/src/App.tsx` | 221 |
| `readError` | Function | `frontend/src/api.ts` | 24 |
| `requestBody` | Function | `frontend/src/api.ts` | 83 |
| `nextId` | Function | `frontend/src/App.tsx` | 50 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `App → ReadError` | cross_community | 4 |
| `App → RequestBody` | cross_community | 4 |

## How to Explore

1. `context({name: "reindex"})` — see callers and callees
2. `query({search_query: "cluster_33"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings (source→sink data flows), when indexed with `--pdg`
