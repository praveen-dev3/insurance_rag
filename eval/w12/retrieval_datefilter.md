# Loss-date-aware retrieval - LLM-free, same engine, same queries, filter off vs on

`off` = engine scoped to the product only (what retrieval did before); `on` = the in-force editions enforced by code (tools/w12_retrieval.py).

| group | n | hit-rate@3 off | hit-rate@3 on | delta | cases with a stale-edition passage in top-3 (off -> on) |
|---|---|---|---|---|---|
| STRADDLE: loss on an older edition (pre_2025) | 9 | 7/9 = 77.8% | 9/9 = 100.0% | +22.2 pts | 9 -> 0 |
| post_2025 (latest edition applies) | 9 | 9/9 = 100.0% | 9/9 = 100.0% | +0.0 pts | 9 -> 0 |
| base wording (single edition) | 8 | 8/8 = 100.0% | 8/8 = 100.0% | +0.0 pts | 2 -> 0 |
| NON-straddle = post_2025 + base | 17 | 17/17 = 100.0% | 17/17 = 100.0% | +0.0 pts | 11 -> 0 |
| all cases with an expected clause | 26 | 24/26 = 92.3% | 26/26 = 100.0% | +7.7 pts | 20 -> 0 |

No-edition case w31 (loss before any HO-0850 edition took effect): form returned with filter off = True, with filter on = False.

Per-case, straddle group (top-3 as (form, edition, first code)):

- w01: off [('HO-0850', '04-25', ['E-50']), ('HO-0850', '07-23', ['E-50']), ('HO-0850', '07-23', [])]  ->  on [('HO-0850', '07-23', ['E-50']), ('HO-0850', '07-23', []), ('HO-0850', '07-23', [])]
- w02: off [('HO-0850', '04-25', ['E-50']), ('HO-0850', '07-23', ['E-50']), ('HO-0850', '07-23', [])]  ->  on [('HO-0850', '07-23', ['E-50']), ('HO-0850', '07-23', []), ('HO-0850', '07-23', [])]
- w05: off [('HO-0850', '04-25', []), ('HO-0850', '07-23', []), ('HO-0850', '04-25', ['E-55'])]  ->  on [('HO-0850', '07-23', []), ('HO-0850', '07-23', ['E-50']), ('HO-0850', '07-23', [])]
- w07: off [('HO-0850', '04-25', []), ('HO-0850', '07-23', []), ('HO-0850', '04-25', ['E-50'])]  ->  on [('HO-0850', '07-23', []), ('HO-0850', '07-23', ['E-50']), ('HO-0850', '07-23', [])]
- w10: off [('HO-0850', '07-23', ['E-50']), ('HO-0850', '07-23', []), ('HO-0850', '04-25', ['E-55'])]  ->  on [('HO-0850', '07-23', ['E-50']), ('HO-0850', '07-23', []), ('HO-0850', '07-23', [])]
- w11: off [('MO-0420', '05-25', ['E-65']), ('MO-0420', '09-23', ['E-65']), ('MO-0420', '05-25', [])]  ->  on [('MO-0420', '09-23', ['E-65']), ('MO-0420', '09-23', []), ('MO-0420', '09-23', [])]
- w12: off [('MO-0420', '05-25', ['E-65']), ('MO-0420', '09-23', ['E-65']), ('MO-0420', '05-25', [])]  ->  on [('MO-0420', '09-23', ['E-65']), ('MO-0420', '09-23', []), ('MO-0420', '09-23', [])]
- w15: off [('MO-0420', '05-25', []), ('MO-0420', '09-23', []), ('MO-0420', '05-25', ['E-65'])]  ->  on [('MO-0420', '09-23', []), ('MO-0420', '09-23', ['E-65']), ('MO-0420', '09-23', [])]
- w18: off [('HO-0850', '07-23', ['E-50']), ('HO-0850', '04-25', ['E-50']), ('HO-0100', '01-22', ['E-01'])]  ->  on [('HO-0850', '07-23', ['E-50']), ('HO-0100', '01-22', ['E-01'])]
