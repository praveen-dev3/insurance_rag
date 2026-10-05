# Week 11 Practical — Task Set D

## Find the coverage answer that ignored an exclusion

**System under test:** the Week 7 claims agent (`tools/w7d_agent.py`), now run through an instrumented wrapper
(`tools/w11_app.py` + `tools/w11_obs.py`) that logs one redacted request per run - spans with latency, tokens and
cost, the prompt version and hash, the retrieved context ids. Model `openai/gpt-oss-20b`, the Week 7-10 model.

Reproduce:

```
python weeks.py w11d-eval --stage suite --label red   --prompt triage-v1 --retrieval kw-r1 --trials 2
python weeks.py w11d-eval --stage suite --label green3 --prompt triage-v3 --retrieval kw-r2 --trials 1 \
        --cases c11,c07,c12,c06,c04,c01,c02,c03,c05,c08,c09,c10        # resumable; see "Status of GREEN"
python tools/w11_drill.py seed --plant-claim c11 ; python tools/w11_drill.py start ; python tools/w11_drill.py find ...
python weeks.py w11d-eval --stage reports                              # trace.json, cost_by_stage.md, tenx.md
```

**Read this first.** The loop is **partly closed, not fully.** RED was measured in full (10/12, 20/24 trials). The
first fix (`triage-v2` + `kw-r2`) put the controlling exclusion rows in front of the model and **c11 still failed**.
The second fix (`triage-v3`) **turned c11 green on its one trial** (`req-842749140cb9`: excluded, E-36, payout 0) - but
gpt-oss-20b's 200,000-tokens/day cap means only that one GREEN case had run when this was written, so the
"rest of the suite still passes" half is **unproven**. No GREEN suite pass count is claimed: the honest figure is
**c11: 0/5 -> 1/1; the other 11 cases: not re-run.** What is claimed is what was measured.

---

## 1. The find (`eval/w11d/drill.md`)

| time-to-find | slice | timed by |
|---|---|---|
| **01:47** | **time** (yesterday) x **output text** (`covered`, `claim_triage`) -> 10 hits / 6 claims -> resolve `context_ids` -> read the claim | **self-drill: the same agent planted and found it. Not a squadmate.** |

Found `req-b0c8b1c0efcf` (2026-10-04 16:35 UTC, user `u-1291`, `triage-v1`/`kw-r1`): answered **covered, payout $4,000**
on claim c11 (shingles "dimpled and pitted", surface "intact", no leaks, replaced because "it looks bad from the street").
Under five minutes, so no missing field is named for the main find. Caveats about blindness, the synthetic
background traffic and the invalid second ("bonus") time are in `drill.md` and are not softened here.

## 2. The trace (`eval/w11d/trace.json`)

The planted record is a re-stamped copy of a real failing run, `req-7060c0c1d556`. `trace.json` is the original.
`triage-v1` (sha256 `76089605d263424c`), `kw-r1`, `openai/gpt-oss-20b`, claim c11.

| span | stage | latency ms | tokens in | tokens out | cost USD |
|---|---|---:|---:|---:|---:|
| llm.lap1 | generation | 547.9 | 868 | 31 | 0.000074 |
| tool.get_claim | tools | 0.5 | 0 | 0 | 0 |
| llm.lap2 | generation | 2,731.1 | 1,045 | 46 | 0.000092 |
| tool.search_policy (`hail`) | retrieval | 0.2 | 0 | 0 | 0 |
| llm.lap3 | generation | 6,987.0 | 1,627 | 50 | 0.000137 |
| tool.search_policy (`deductible`) | retrieval | 0.1 | 0 | 0 | 0 |
| llm.lap4 | generation | 16,056.3 | 2,023 | 79 | 0.000175 |
| tool.compute_payout | tools | 0.0 | 0 | 0 | 0 |
| llm.lap5 | generation | 10,554.7 | 2,139 | 87 | 0.000187 |
| **total** | | **36,878.7** | **7,702** | **293** | **0.000665** |

Retrieved context ids: `HO-0412#25, #26, #29, #32, #35, #43, #33, #37` (resolve with `python weeks.py resolve-chunk`).
The agent searched `hail` (top 5) and `deductible`. The ids are the purpose clause, the coverage basis, the exclusions
preamble, **E-32, E-35, E-33, E-37** and the deductible - **not `#34` (E-34, cosmetic damage) and not `#36` (E-36, granule loss / scuffing)**, the two rows
that describe this claim. That is the one-hop diagnosis the brief's last "common mistake" is about: because the
context ids were logged, "retrieval missed the exclusion" and "the model ignored it" are separable in a minute.
Here retrieval missed it.

## 3. Failure -> test -> fix

**The eval case** (`eval/w11d/eval_cases_added.json`, folded into the suite by `tools/data/w11d_cases.py`): `c11`, the
drill's claim, golden `excluded`, payout 0; and `c12` - the same form with a confirmed breach - golden
`covered`, payout 6,000 (2% of 300,000 = 6,000, not the 1,000 minimum). `c12` is there so "always find the
exclusion" cannot go green by saying *excluded* for every hail claim. The suite is the 10 Week-7 claims plus these two
(12 cases); a case passes only if **all** its trials pass, because a sampled model can pass once by luck.

### RED, before any fix (`eval/w11d/suite_red.txt`, 24 trials, v1/r1)

```
CASES  10/12 pass          TRIALS 20/24 pass          FAILING: c07, c11 (both trials each)
```

c11 failed 5 of 5 times in total, including the probe before the suite. `c07` (the Week 7 hail granule-loss claim
that Week 7 already knew failed) failed 2/2 here; it passed once in an earlier probe - it is flaky, c11 is not.
The eval case was added, and watched fail, **before** any fix was written.

### Fix, attempt 1 - retrieval layer: `kw-r1 -> kw-r2`, prompt `triage-v1 -> triage-v2`

Diagnosis from the context ids: the notes never share a word with the HO-0412 rows ("dimpled", "pitted" vs
"marring, scuffing or granule loss"), so keyword search returns the coverage clauses and never the row that excludes.
`kw-r2` attaches the governing form's whole exclusion table - and the note under it that reverses some rows - to any
search that touches the form, once per request; `triage-v2` tells the model to read every row against the notes.
Retrieval-side it worked: the next c11 run's context contained E-34, E-36 and the note (16 chunk ids vs 8).

**It did not turn c11 green.** `req-e0fa0927aaf5`: *"Loss is penetration (pitted) so not cosmetic, no exclusion
applies."* The controlling rows were in front of it and gpt-oss-20b read "pitted" as a breach against notes that say
the surface is intact. The first fix removed the retrieval cause and exposed a second, **generation** cause. (A
retrieval failure is never fixed by a prompt; the reverse also holds: this one was never going to be fixed by more
retrieval.) Cost of attempt 1 on c11: 9,280 tokens vs 7,995, +16% (`cost_by_stage.md` s.4).

### Fix, attempt 2 - prompt layer: `triage-v2 -> triage-v3`

Adds a rule that penetration is a fact the notes state and that "pitted/dimpled/dented" describe appearance
(`eval/w11d/prompt_versions.md`). It is general, not c11-specific, and `c12` (breach confirmed) guards against
over-correcting.

### Status of GREEN (what is and is not known)

| | prompt / retrieval | cases run | result |
|---|---|---|---|
| RED | v1 / r1 | 12 cases x 2 trials | **10/12** (20/24 trials) - c07, c11 fail |
| GREEN attempt 1 | v2 / r2 | c11 x 1 | **FAIL** (`req-e0fa0927aaf5`) - context fixed, model misread |
| GREEN attempt 2 | v3 / r2 | **c11 x 1** (of 12 queued) | **c11 PASS** (`req-842749140cb9`): `excluded`, E-36, payout 0 - "the roof surface was intact with no breach" |

So: **c11 went 0/5 (RED) to 1/1 (GREEN)** - n is one, against five failures, so it is strong evidence of a change
and weak evidence of a fix. It also used *fewer* tokens than RED (7,792 vs 7,995) and 16% fewer than the v2 attempt.
**The 11 other cases have not been re-run under v3/r2**, including `c07` (the other known failure, same mechanism),
`c12` (the guard against over-correcting: hail with a confirmed breach must stay `covered`, payout 6,000) and the
claims that never touch HO-0412. Until they have, the third "common mistake" - adding the case, seeing it green and not
re-running the suite - is **still open**, and a RED-vs-GREEN pass-count pair (the brief's "9/10 -> 11/11") does not
exist yet. The suite is resumable; the same command, left running, completes it at the rate the token bucket refills
(about one case an hour). `suite_green3.json` holds whatever has finished; from `tools/`:
`python -c "from w11_suite import *; print(format_summary(summarise('green3')))"` prints the counts with unrun cases
labelled "not run", never counted as passes.

One run was thrown away on the way: the first GREEN attempt (`req-ec3bea5c27c0`) hit the agent's 90-second wall-clock budget while waiting out a rate-limit 429 and was scored FAIL for it. That is an infrastructure stall, not a result; the suite now lifts the wall-clock cap and refuses to record a run that still hits it (`tools/w11_suite.py`). The record of that run is in `eval/w11d/green_v2_traces.jsonl`.

Why only one: Groq's free tier gives `gpt-oss-20b` 200,000 tokens/day, refilling at ~2.3 tokens/s, and one triage
costs 7,000-9,300 tokens. The RED suite (24 runs) used the day. The failure only reproduces on 20b - c11 passes on
`gpt-oss-120b` and `qwen3.8-27b` under the unfixed prompt - so a different model cannot stand in for the comparison.

## 4. Prompt version bump and the canary/rollback plan (`eval/w11d/prompt_versions.md`)

**Bump:** `triage-v1` (`76089605d263424c`) -> `triage-v3` (`9f7208b166842db6`); retrieval `kw-r1` -> `kw-r2`. Every request
logs `prompt_version`, `retrieval_version` and the prompt sha256. (`triage-v2` is an intermediate that failed c11
and should not ship.)

- **Canary:** send 5% of `claim_triage` traffic to `triage-v3`/`kw-r2` for the first 200 requests or 48 hours, alarming
  if the `covered` share on HO-0412 claims moves by more than 5 points or mean tokens/claim rises more than 25%
  (the fix measured +16%); promote only when the full 12-case suite passes on all trials.
- **Rollback:** flip the version flag back to `triage-v1`/`kw-r1` (both stay in `w11_app.PROMPTS`/`RETRIEVALS`); the
  affected requests are listable by `find --prompt triage-v3`, and the trigger is any `covered` answer on the new
  case's pattern or an adjuster complaint inside the window.

Not shippable until the other 11 cases have run under v3/r2: this plan is for a fix that has fixed its own case and has not yet shown it breaks nothing.

## 5. Cost per query by stage (`eval/w11d/cost_by_stage.md`)

Request `req-7060c0c1d556`: **$0.000665**, 7,995 tokens, 5 model calls, 36.9 s.

| stage | as logged | attributed to the stage that caused the tokens |
|---|---:|---:|
| retrieval | $0.000000 (0.3 ms) | $0.000190 (**29%**) |
| generation | $0.000665 | $0.000413 (62%) |
| tools | $0.000000 (0.5 ms) | $0.000062 (9%) |

Read as logged, retrieval is free and generation is everything. Attributed (a result is charged to its stage on
every later lap that re-sends it), a third of the bill is retrieval's output being carried through the loop. Across
the 24 RED requests: mean **$0.00063 / 7,578 tokens** per claim. This was done *before* the fix, which is what
made "+16% for the fix" a number with an owner (the extra exclusion schedule is retrieval-attributed:
$0.000190 -> $0.000315) rather than a surprise.

## 6. At 10x (`eval/w11d/tenx.md`)

**At 10x (600 claims/day) a rate limit breaks first: one triage costs 7,578 tokens, so the free tier's
200,000-tokens/day cap is hit after 26 claims (23x over at 10x) - while cost is $0.38/day and latency needs only
1.8 concurrent runs.** It is already over at 1x (60 claims/day); the volume is the capstone brief's 1,800 FNOLs a
month, the TPD figure is the 429 this repo's own run received, the 8-hour day and 2x peak are stated assumptions.

## 7. The "common mistakes", checked against what was done

- *Optimising before attributing cost* - attributed first (s.5).
- *Fixing before adding the case* - the case was added and failed (c11: 5 of 5 runs) before any fix existed.
- *Only searching inputs* - the find used output text and context ids.
- *Adding the case, seeing green, not re-running the rest* - **open**: c11 is green, the other 11 cases have not been re-run.
- *Logging the full note* - the log stores the note's sha256 and length only; claim numbers and claimant
  names are redacted on write and the write is refused if one survives (`RequestSink`, reusing `rag/tracing.py`).
- *Not logging context ids* - logged on every request; it is what made the diagnosis one hop.

## 8. Not done / not claimed

- A squadmate-timed drill, and a valid "beat your own time" (`drill.md`).
- A complete GREEN suite (11 of 12 cases not re-run). The command to finish it is above and is safe to re-run.
- The background traffic in the drill log is synthetic apart from the planted record and the re-stamped real runs.
