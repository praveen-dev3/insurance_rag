# Error taxonomy - integrated system, n=25 requests (label `main`)

Frequency is the share of the n requests exhibiting the mode; one request can exhibit several. Modes marked **integration** only exist because the parts were joined.

| # | mode | origin | severity | freq | n | example trace id |
|---|---|---|---|---|---|---|
| 1 | guard_rewrote_decision_language | **integration** | high | 76% | 19/25 | `req-a0c11c419245` |
| 2 | ungrounded_citation | **inherited** | high | 12% | 3/25 | `req-e1aceef67b4b` |
| 3 | expected_edition_not_cited | **inherited** | high | 4% | 1/25 | `req-2af22a07c008` |
| 4 | peril_misclassified_before_limits_lookup | **integration** | high | 4% | 1/25 | `req-2af22a07c008` |
| 5 | right_edition_wrong_or_missing_clause | **inherited** | medium | 16% | 4/25 | `req-0e394fea9b38` |
| 6 | loss_date_not_carried_to_citation | **integration** | medium | 12% | 3/25 | `req-e1aceef67b4b` |
| 7 | redundant_tool_call | **integration** | low | 100% | 25/25 | `req-a0c11c419245` |
