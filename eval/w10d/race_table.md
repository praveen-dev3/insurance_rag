# Week 10 Task Set D: race table

Same 10 Week-6 eval cases as every Task Set D since Week 7 (c01, c02, c03, c04, c05, c06, c07, c08, c09, c10), same judge (`grade()` from `w7d_common.py`: status + payout only), same model (`w7d_agent`'s `MODEL`).

| metric | single agent | orchestrator |
|---|---:|---:|
| pass rate | 7/10 (0.700) | 7/10 (0.700) |
| p50 latency (s) | 44.65 | 38.41 |
| p99 latency (s) | 4577.32 | 63.98 |
| total tokens (10 claims) | 72469 | 63081 |
| cost per claim (USD) | $0.00061 | $0.00059 |

**Context re-send multiplier: 0.9x** (orchestrator tokens / single-agent tokens, 63081 / 72469). Dominant hand-off: **`orchestrator -> exclusions-worker`, 84% of all orchestrator tokens** (53194 of 63081) - see `eval/w10d/handoffs.log` for the per-claim breakdown.
