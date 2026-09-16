# Week 8 Task Set D: mitigation before -> after

Mitigation: `Budget.max_iterations` 10 -> 5. Nothing else changed - same prompt, same tools, same three tool schemas, same model.

## Top failure mode: `step_overrun` (8 of 10 claims at baseline)

**8 -> 3**

## Price paid

| | before | after | delta |
|---|---:|---:|---:|
| outcome pass rate | 0.700 | 0.600 | -0.100 |
| trajectory pass rate | 0.700 | 0.700 | +0.000 |
| step efficiency | 1.294 | 1.118 | -0.176 |
| total cost, 10 claims (USD) | 0.00728 | 0.00539 | -0.00189 |
| total tokens, 10 claims | 87749 | 63936 | -23813 |
| total wall clock, 10 claims (s) | 568.8 | 1386.7 | +817.9 |

Outcome flips (a claim that passed/failed the outcome eval changed sides):
- `c03`: FAIL -> PASS
- `c06`: PASS -> FAIL
- `c10`: PASS -> FAIL

**Budget now fires where it did not before, on: ['c06', 'c10']** - the direct price of the tighter cap: a claim that needed its extra lap (the redirect leg or a deductible search) no longer gets it, and stops early instead of finishing late.

## Regression check: every mode, before -> after

| mode | before | after | |
|---|---:|---:|---|
| budget_exceeded | 0 | 2 | WORSE |
| hallucinated_argument | 1 | 0 | better |
| missing_required_form | 0 | 1 | WORSE |
| step_overrun | 8 | 3 | better |

Modes that got worse or newly appeared: `budget_exceeded`, `missing_required_form`
