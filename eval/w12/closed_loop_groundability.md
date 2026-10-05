# Week 12 closed loop - groundable citations (retrieval replay, LLM-free)

Failure under test: the model cited a clause that retrieval never returned (`ungrounded_citation`, 3 of 25 integrated requests, e.g. `req-e1aceef67b4b`). Diagnosis from the logged context ids: the exclusion-table chunks filled the top 3 and the `2. Coverage Basis` chunk was not among them. Fix: retrieval layer, `_complete_pairs` in tools/w12_retrieval.py (retrieval version `hybrid-datefilter-v1` -> `hybrid-datefilter-v2`).

Replayed: every logged search of run `main`, the model's own queries, unchanged.

| arm | requests with every cited clause groundable | expected clause reachable | case passes both | stale-edition passages | mean passages/request |
|---|---|---|---|---|---|
| RED (pair completion off) | 18/21 | 16/20 | 17/21 | 0 | 3.0 |
| GREEN (pair completion on) | 20/21 | 19/20 | 19/21 | 0 | 3.2 |

Per-case changes (RED -> GREEN):

- w02 (pre_2025): groundable False -> True, reachable False -> True
- w05 (pre_2025): groundable False -> True, reachable False -> True
- w07 (pre_2025): groundable False -> False, reachable False -> True

Cases that were fine and are now not (silent regressions): **0** 
