# Eval report - integrated system (Week 12, Variant D)

System under test: `python weeks.py w12 ...` at retrieval `hybrid-datefilter-v1` / prompt `triage-w12-v1`, model
`openai/gpt-oss-120b`, run label `main`. Raw results: `run_main.json`, `suite_main.txt`, `taxonomy_main.md`,
`trajectory_main.md`; every figure below can be recomputed from them with `python weeks.py w12 score|taxonomy|trajectory --label main`.

**n = 25 of the 31 cases defined** (`tools/data/w12_claims.py`). Six base-wording cases (`w21`-`w26`) did not run:
the model's free-tier daily token cap was spent. One run per case - no repeat trials, so each pass rate carries
roughly +/-15 points of sampling uncertainty at this n.

## 1. Headline, and the number the brief says to read instead of the average

**20/25 pass** (80%). The average hides the cases the brief cares about, so per boundary class:

| class | what it is | n | pass |
|---|---|---:|---:|
| `pre_2025` | loss dated on an **older** edition (the straddle cases, incl. the day before each edition took effect) | 9 | **5/9 (56%)** |
| `post_2025` | loss on the latest edition | 9 | 9/9 |
| `base` | single-edition base wording | 2 | 1/2 |
| `lapsed` | policy not in force on the loss date | 4 | 4/4 |
| `no_edition` | in force, but no edition of the flood form existed yet | 1 | 1/1 |

Per assertion (all must hold for a case to pass): `referral_made` 25/25, `in_force_correct` 25/25,
`reason_code_correct` 25/25, `in_force_checked_first` 25/25, `no_decision_language` 25/25, `no_stale_edition` 20/20,
`figures_correct` 20/20, `edition_correct` 19/20, `clause_cited` 16/20, `citations_grounded` 17/20,
`loss_date_on_citations` 17/20.

**The failures are not the failure the brief is worried about.** No request cited a stale edition (0 of 20 with a
citation set); the dates, editions and the three numbers were right everywhere. What failed is *which clause*:

| case | trace | cause | one-hop diagnosis |
|---|---|---|---|
| w02, w05, w07 | `req-e1aceef67b4b`, `req-e2e70feb488b`, `req-c8c3fe062b0f` | cited clause 2.1/2.2/1.1 that retrieval never returned | **retrieval**: the three exclusion-table chunks filled the top 3; the coverage-basis chunk is absent from `context_ids` |
| w12 | `req-0e394fea9b38` | retrieved E-65 (hydrolock) but cited "3.1" and "2.1" | **model**: the right chunk was in context |
| w20 | `req-2af22a07c008` | asked about "escape of water burst tank" for a house empty 75 days; never searched the vacancy exclusion | **model**: its query framing; retrieval was never asked. Also picked the wrong peril class for the limits lookup. |

## 2. Hostile questions

**"11 August 2024 and you cited the 2025 flood exclusion - how many cases fall between versions and what do they score?"**
Nine cases are dated on the older edition (`pre_2025`), including `w02` (2025-03-31, the day before HO-0850 ed. 04-25)
and `w12` (2025-04-30, the day before MO-0420 ed. 05-25). They score 5/9 as whole cases, but **0/9 cited the wrong
edition**. The 11 Aug 2024 case itself is `w01` (`req-6ccf1125d389`): cited HO-0850 ed. 07-23, clause 2.1 and 2.2, loss date
2024-08-11 stamped on each, figures $1,000 / $15,000 / $350,000. Before the date filter, the same engine put a
**stale-edition passage in the top 3 for 9 of 9** of those cases (`retrieval_datefilter.md`); with it, 0 of 9.

**"Does your system ever say 'covered'? Show the assertion, not the prompt."** The prompt asks; `tools/w12_guard.py`
enforces, on every model-authored sentence, before the referral leaves `TriageSession.run`, and
`score_case`'s `no_decision_language` re-checks the emitted output independently (25/25). The honest number is how
often the *model* wrote decision language before the guard stepped in: **19 of 25 requests (76%)**. In 6 of those the
summary itself did ("so no coverage applies under this policy"); in 13 only a citation's relevance line did,
overwhelmingly "Excludes flood loss to the dwelling" restating an exclusion row. The guard cannot tell a restated
clause from a stated outcome, so it rewrites both - safe for compliance, costly for usefulness (the adjuster gets a
templated summary). And it is a pattern list: reading the 25 outputs by hand I found **two it missed** - `w03`
"indicating the loss falls under that exclusion" and `w15` "exclusion E-66 *may apply*". See `WEAKNESSES_W12.md` #1.

**"Show me the trace where it got the sub-limit right."** `w06`, `req-3c5b2a5642c0` (surface water, loss 2025-06-10):
deductible **$2,500**, sub-limit **$5,000**, policy limit **$420,000**, all three taken from `get_limits` for
HO-0850 ed. 04-25 - not from the wording. The 07-23 edition would have given $1,000 / $15,000. The assertion that
would have caught it is `figures_correct`, which compares each of the three keys to `limits_for(...)` separately.
20/20 on the cases that have a lookup.

**"Why was claim 4471-A declined 18 months ago - can you reproduce that exact answer?"** Partly, and the line is
stated: `python weeks.py w12 replay --label main --trace req-e1aceef67b4b` re-runs the logged searches and shows the same
wording edition, the same chunk ids and the same chunk text by hash (`eval/w12/replay_req-e1aceef67b4b.md`), under the same
logged model id, prompt sha256 and retrieval version. It does **not** prove the model would regenerate the same
sentences; a sampled model does not promise that. The logged referral is the record of what was said. The replay also
earned its keep once: the first run said "not identical" because retrieval had since changed - which is the
check working.

**"What did your MCP server hand to another squad's agent?"** `eval/w12/pii_audit.md`: 130 responses probed (every
tool, every claim, plus six searches written to pull a claimant out of the index), searched for 71 known PII
literals plus an injury lexicon: **0 found**. 438 log lines scanned: **0 found**. A tool that returns a raw name
and address is withheld at the wire. The audit finds only literals it was told about; an unregistered name in
free text would pass it.

## 3. Numbers that moved

| metric | before | after | n | where |
|---|---|---|---|---|
| top-3 passages from a **stale edition** (retrieval, LLM-free) | 9/9 straddle cases | **0/9** | 9 (26 all cases: 20 -> 0) | `retrieval_datefilter.md` |
| hit-rate@3, straddle cases | 77.8% | **100%** | 9 | same |
| **cost of the date filter**: hit-rate@3 on non-straddle cases | 100% | 100% (**0.0 pts**) | 17 | same - see caveat |
| citations backed by a retrieved passage (retrieval replay of the model's own queries) | 17/21 requests | **19/21** | 21, 0 regressions | `closed_loop_groundability.md` |
| expected clause reachable in the replayed results | 16/20 | **19/20** | 20 | same |

Caveat on the zero: the brief predicts the filter "will have cost you something". It cost nothing *here* because the
corpus is 36 chunks, every non-straddle case's answer lives in an in-force edition by construction, and a filter
can only cost recall where the right chunk is in a filtered-out edition. Not evidence that it is free on
60-page wordings.

**Agent-level wrong-edition rate, before -> after.** After: 0/20 requests cited a stale edition (run `main`). Before:
**not measured.** The five straddle cases were queued with the date filter off (`run_nofilter5`) but the model's
token bucket never refilled enough to finish one, so the "5 red before, 5 green after" the bonus asks for exists only
at retrieval level (9/9 -> 0/9 stale passages, above), not as agent outcomes. See section 7.

## 4. Re-scored error taxonomy (`taxonomy_main.md`)

| # | mode | origin | severity | freq | example |
|---|---|---|---|---|---|
| 1 | model-authored decision language rewritten by the guard | **integration** | high | 76% (19/25) | `req-a0c11c419245` |
| 2 | ungrounded citation (clause never retrieved) | inherited | high | 12% (3/25) | `req-e1aceef67b4b` |
| 3 | wrong peril class before the limits lookup | **integration** | high | 4% (1/25) | `req-2af22a07c008` |
| 4 | expected edition not cited (queried the wrong form) | inherited | high | 4% (1/25) | `req-2af22a07c008` |
| 5 | right edition, wrong/missing clause | inherited | medium | 16% (4/25) | `req-0e394fea9b38` |
| 6 | loss date not carried to the citation (a consequence of #2: no backing passage to take it from) | **integration** | medium | 12% (3/25) | `req-e1aceef67b4b` |
| 7 | redundant tool call: model re-fetched the FNOL the harness had already fetched | **integration** | low | 100% (25/25) | `req-a0c11c419245` |

**The mode integration created:** #7 is the cleanest - it exists only because the harness took over intake while
runtime discovery still showed the model `get_fnol`; no component has it alone. It was fixed after the run (see
`SEAMS_W12.md` #9, repeats are now answered from the request's cache) and **not re-measured** because the quota
was spent. #1 is also integration-born (the guard is the integration) but its cause, the model's phrasing, is
inherited. Frequencies are over requests, one request can sit in several rows.

## 5. Trajectory (`trajectory_main.md`) and the outcome-vs-trajectory gap

- tool-choice accuracy **115/116 = 99.1%** of model-chosen calls (the harness's intake call is not counted; counting
  a call the model did not choose would flatter the number)
- trajectory pass (every call right, nothing required missing) **24/25 = 96%**; outcome pass **20/25 = 80%**
- **gap: 16 points, in the embarrassing direction.** In 4 of the 5 failures the path was right and the answer still
  wrong. A trajectory eval alone would have scored this system 96%.

## 6. Judge agreement on the integrated outputs

The Week 6 judge is not the instrument here: it grades claim *summaries* and scored **80% (20/25)** against hand
labels in Week 6 - already below the 85% this brief says it must "still clear". A new judge
(`JUDGE_PROMPT` in `tools/w12_audit.py`, model `qwen/qwen3.8-27b`, one criterion `wording_faithful`) was measured fresh
against `labels_main.json` (n=25: 20 faithful, 5 not), in three configurations on the same 25 outputs:

| judge configuration | agrees | rate | vs 85% bar | file |
|---|---:|---:|---|---|
| v1 prompt (no account of the loss shown), reasoning low - **the first measurement** | 19/25 | **76.0%** | not cleared | `agreement_main_v1_low.md` |
| v1 prompt, reasoning off | 21/25 | 84.0% | not cleared (one case short) | `agreement_main_v1_none.md` |
| v2 prompt (adds the redacted account of the loss), reasoning off | 17/25 | 68.0% | not cleared | `agreement_main_v2_none.md` |

**No configuration clears 85%.** I expected v2 to help: five of v1-low's six objections were "the summary describes the
loss and the judge was never shown it". Showing it made the judge *worse* (68%): it became stricter about clause
relevance lines (`w01`: "'apply to this type of loss' constitutes a coverage decision"). So that diagnosis was
at best half right. The 84% row is the best of three variants chosen **after** seeing all three on the same 25 labels;
that is tuning on the test set and I do not offer it as the judge's agreement. Quote 76% (first measurement) and
the 68-84% spread. All of the judge's errors but three are in the "judge too strict" direction (it never passed
a referral I labelled unfaithful, except `w15`, which a reasoning-off v1 passes), consistent with the 5/25 unfaithful
base rate making the 85% bar roughly "agree on 21".

**Who labelled.** Me - the assistant that built the system - reading each emitted referral, with the reasons in
`labels_main.json`, *before* any judge verdict was read. Not a human adjuster, not independent. Treat every
figure here as "agrees with the builder's reading", not as validation against domain experts. Where the judge and I
disagree in the same direction on a recurring question - whether "coverage cannot be determined" (said of a lapsed
policy) states an outcome (`w28`, `w30`) - it is a real ambiguity in the criterion, not just judge error.

## 7. What did not finish, said plainly

- 6 of 31 cases never ran (token quota). `python weeks.py w12 run --label main --cases w21,w22,w23,w24,w25,w26`.
- The no-date-filter agent arm (`run_nofilter5`: w01, w02, w05, w11, w12 with the filter off) **produced no completed
  case**: it waited on the same token cap for over an hour and was stopped. Resume with
  `python weeks.py w12 run --label nofilter5 --no-date-filter --cases w01,w02,w05,w11,w12` (no `--fresh`); score it with
  `python weeks.py w12 score --label nofilter5`, reading only `edition_correct` and `no_stale_edition` (the other assertions
  fail by construction without a date filter, because no loss date is resolved onto a citation).
- The agent-level confirmation of the groundability fix (re-run w02, w05, w07 under `hybrid-datefilter-v2`) is not run.

## 8. What this suite does NOT measure

- **The Week 6 suite itself.** The brief says to run "your Week 6 eval suite" against the integrated system. That suite grades claim *summaries* from adjuster notes (`eval/w6_cases.json`, `rag/judge.py`) and has no analogue for a referral, so it was not run; a new 31-case suite in the same style (assertions first, judge second) replaces it, and its 25 completed cases are the "25-40" the brief asks for.
- **Real wordings.** 6 short documents, 36 chunks. Hit-rate@3 over 36 chunks is near-trivial; nothing here says how
  the Week 3-4 pipeline copes with the exclusions schedule of a 60-page wording, or with the Week 4 problem of
  parsing it badly (listed as a known limit, not tested).
- **Any load.** Single requests, one at a time. Concurrency, queueing behind the single-process MCP server, and
  burst behaviour are arithmetic in `cost_and_10x.md`, not measurements.
- **Variance.** One run per case, one model. No repeat trials, no second model, so no estimate of how much of 80% is luck.
- **Adversarial input.** The only pressure test is five FNOLs with "please confirm this is covered"; nothing injects
  instructions through the FNOL text, and the FNOL is the redacted view, so a hostile *claimant* narrative was not tested.
- **PII beyond known literals.** The audit searches for the names, addresses and injury sentences it was given.
- **Policy-term semantics.** An edition is chosen by loss date alone; a renewal-date rule (a policy on the 2023 wording
  until it renews) is not modelled. Mid-term endorsements, multiple policies per claim, and partial in-force
  periods are not modelled.
- **Whether the referral helps an adjuster.** Nothing measures usefulness; the guard's templated fallback makes 76%
  of summaries less informative, and no metric here sees that cost.
- **Dollar accuracy.** Prices are list prices recalled from memory, flagged in `cost_and_10x.md`.
