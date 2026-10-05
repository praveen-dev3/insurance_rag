# Cost per query, by stage

Request `req-7060c0c1d556` (the drill's bad answer, claim c11, `triage-v1` / `kw-r1`, model `openai/gpt-oss-20b`). Prices: $0.075 / $0.30 per million input / output tokens (the rate quoted in tools/w7d_common.py).

## 1. Spans as logged (billed by the stage that made the call)

| span | stage | latency ms | tokens in | tokens out | cost USD |
|---|---|---:|---:|---:|---:|
| llm.lap1 | generation | 547.9 | 868 | 31 | 0.000074 |
| tool.get_claim | tools | 0.5 | 0 | 0 | 0.000000 |
| llm.lap2 | generation | 2731.1 | 1045 | 46 | 0.000092 |
| tool.search_policy | retrieval | 0.2 | 0 | 0 | 0.000000 |
| llm.lap3 | generation | 6987.0 | 1627 | 50 | 0.000137 |
| tool.search_policy | retrieval | 0.1 | 0 | 0 | 0.000000 |
| llm.lap4 | generation | 16056.3 | 2023 | 79 | 0.000175 |
| tool.compute_payout | tools | 0.0 | 0 | 0 | 0.000000 |
| llm.lap5 | generation | 10554.7 | 2139 | 87 | 0.000187 |

| stage | spans | latency ms | cost USD |
|---|---:|---:|---:|
| retrieval | 2 | 0.3 | 0.000000 |
| generation | 5 | 36877.0 | 0.000665 |
| tools | 2 | 0.5 | 0.000000 |
| **total** | 9 | 36878.7 | **0.000665** |

Read literally, retrieval and tools cost nothing and generation is the whole bill. That is true of the *calls* and is the wrong basis for deciding what to optimise: retrieval here is a local keyword search ($0, a few ms), but what it *returns* is carried in the transcript the model re-reads on every later lap.

## 2. Attributed by what caused the tokens

Lap k's input is the fixed prompt plus everything earlier laps added; each lap's additions are charged to the stage of the tool it ran, and re-charged on every lap that re-sends them (`attribute_cost` in tools/w11_reports.py).

| stage | input tokens caused | cost USD | share |
|---|---:|---:|---:|
| retrieval | 2538 | 0.000190 | 29% |
| generation | 4340 | 0.000413 | 62% |
| tools | 824 | 0.000062 | 9% |
| **total** | 7702 (+293 output) | **0.000666** | 100% |

`generation` here = the fixed prompt re-sent on each of the 5 laps plus every output token. That fixed prompt (system text + three tool schemas) is re-sent on every lap, so it is the largest line - which makes cutting a lap a bigger lever than trimming what search returns, and is why this attribution has to be done before either is tried.

## 3. Across the 24 completed requests of the RED suite (20b, v1/r1)

- mean cost per query **$0.00063** (7,578 tokens)
- attributed: retrieval **$0.00015** (24%), tools **$0.00006** (10%), generation **$0.00042** (66%)

## 4. What the fix cost (the same claim, c11)

| | v1 / kw-r1 (RED) | v2 / kw-r2 | v3 / kw-r2 |
|---|---:|---:|---:|
| tokens | 7995 | 9280 | 7792 |
| cost USD | 0.000665 | 0.000765 | 0.000650 |
| attributed to retrieval USD | 0.000190 | 0.000315 | 0.000171 |
| model calls | 5 | 4 | 4 |
| answer | covered / payout 4000.0 | covered / payout 4000.0 | excluded / payout 0.0 |
