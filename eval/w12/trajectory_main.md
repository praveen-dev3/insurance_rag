# Trajectory eval - integrated agent, n=25 cases (label `main`)

- **tool-choice accuracy:** 115/116 = 99.1% of tool calls correct
- **outcome pass:** 20/25 = 80.0%
- **trajectory pass** (every call right, no required call missing): 24/25 = 96.0%
- **outcome-vs-trajectory gap:** -16.0 points (outcome minus trajectory)
- right outcome by the wrong path: 0; right path to the wrong outcome: 4; both right: 20

| case | outcome | path | missing | wrong calls | trace id |
|---|---|---|---|---|---|
| w27 | pass | ok | - | - | `req-a0c11c419245` |
| w28 | pass | ok | - | - | `req-13aa1bc7df03` |
| w29 | pass | ok | - | - | `req-bf5efc58c9ab` |
| w30 | pass | ok | - | - | `req-e245a32c1c5f` |
| w31 | pass | ok | - | - | `req-995c347a3443` |
| w01 | pass | ok | - | - | `req-6ccf1125d389` |
| w02 | FAIL | ok | - | - | `req-e1aceef67b4b` |
| w03 | pass | ok | - | - | `req-bb2b5a59d5e7` |
| w04 | pass | ok | - | - | `req-091ed2f15154` |
| w11 | pass | ok | - | - | `req-ca97abaf89aa` |
| w12 | FAIL | ok | - | - | `req-0e394fea9b38` |
| w13 | pass | ok | - | - | `req-1b9cb75c5f7d` |
| w14 | pass | ok | - | - | `req-7afa8e057927` |
| w05 | FAIL | ok | - | - | `req-e2e70feb488b` |
| w06 | pass | ok | - | - | `req-3c5b2a5642c0` |
| w07 | FAIL | ok | - | - | `req-c8c3fe062b0f` |
| w08 | pass | ok | - | - | `req-1138f32dcd01` |
| w09 | pass | ok | - | - | `req-391fd10e1165` |
| w10 | pass | ok | - | - | `req-05b5e764750f` |
| w15 | pass | ok | - | - | `req-81aea0cc551a` |
| w16 | pass | ok | - | - | `req-59158f2f24a6` |
| w18 | pass | ok | - | - | `req-a055e3435927` |
| w19 | pass | ok | - | - | `req-25fc01fd5c93` |
| w17 | pass | ok | - | - | `req-2c3a5525ce62` |
| w20 | FAIL | FAIL | - | wrong peril/date/policy, or policy not in force | `req-2af22a07c008` |
