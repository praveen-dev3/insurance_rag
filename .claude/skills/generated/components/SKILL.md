---
name: components
description: "Skill for the Components area of insurance_rag. 25 symbols across 8 files."
---

# Components

25 symbols | 8 files | Cohesion: 83%

## When to Use

- Working with code in `frontend/`
- Understanding how fetchHealth, fetchGoldenSet, App work
- Modifying components-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `frontend/src/components/InspectionPanel.tsx` | number, Funnel, StageTable, TraceView, useEvalRuns (+2) |
| `frontend/src/api.ts` | getJson, fetchHealth, fetchGoldenSet, fetchEvalResults |
| `frontend/src/components/SourceList.tsx` | format, MatchBadges, SourceCard, SourceList |
| `frontend/src/components/RichText.tsx` | renderInline, RichText, flushParagraph, flushList |
| `frontend/src/components/Sidebar.tsx` | Toggle, Sidebar, toggleSource |
| `frontend/src/App.tsx` | App |
| `frontend/src/components/Composer.tsx` | Composer |
| `frontend/src/components/MessageBubble.tsx` | MessageBubble |

## Entry Points

Start here when exploring this area:

- **`fetchHealth`** (Function) — `frontend/src/api.ts:43`
- **`fetchGoldenSet`** (Function) — `frontend/src/api.ts:45`
- **`App`** (Function) — `frontend/src/App.tsx:52`
- **`Composer`** (Function) — `frontend/src/components/Composer.tsx:22`
- **`Sidebar`** (Function) — `frontend/src/components/Sidebar.tsx:87`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `fetchHealth` | Function | `frontend/src/api.ts` | 43 |
| `fetchGoldenSet` | Function | `frontend/src/api.ts` | 45 |
| `App` | Function | `frontend/src/App.tsx` | 52 |
| `Composer` | Function | `frontend/src/components/Composer.tsx` | 22 |
| `Sidebar` | Function | `frontend/src/components/Sidebar.tsx` | 87 |
| `toggleSource` | Function | `frontend/src/components/Sidebar.tsx` | 104 |
| `fetchEvalResults` | Function | `frontend/src/api.ts` | 53 |
| `InspectionPanel` | Function | `frontend/src/components/InspectionPanel.tsx` | 361 |
| `MessageBubble` | Function | `frontend/src/components/MessageBubble.tsx` | 28 |
| `SourceList` | Function | `frontend/src/components/SourceList.tsx` | 106 |
| `RichText` | Function | `frontend/src/components/RichText.tsx` | 43 |
| `flushParagraph` | Function | `frontend/src/components/RichText.tsx` | 51 |
| `flushList` | Function | `frontend/src/components/RichText.tsx` | 59 |
| `getJson` | Function | `frontend/src/api.ts` | 33 |
| `Toggle` | Function | `frontend/src/components/Sidebar.tsx` | 55 |
| `number` | Function | `frontend/src/components/InspectionPanel.tsx` | 37 |
| `Funnel` | Function | `frontend/src/components/InspectionPanel.tsx` | 50 |
| `StageTable` | Function | `frontend/src/components/InspectionPanel.tsx` | 92 |
| `TraceView` | Function | `frontend/src/components/InspectionPanel.tsx` | 136 |
| `useEvalRuns` | Function | `frontend/src/components/InspectionPanel.tsx` | 265 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `App → ReadError` | cross_community | 4 |
| `App → RequestBody` | cross_community | 4 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Cluster_33 | 2 calls |

## How to Explore

1. `context({name: "fetchHealth"})` — see callers and callees
2. `query({search_query: "components"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings (source→sink data flows), when indexed with `--pdg`
