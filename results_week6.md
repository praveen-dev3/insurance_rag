# Week 6 Practical — Task Set D

## Validate the claim-summary judge before you trust its number

**Domain:** insurance claims · **Date:** 2026-08-26 · **Eval:** 25 cases,
5 taxonomy modes from Week 5, 2 regression cases replayed verbatim from
real failed traces

---

## The numbers

| | |
|---|---|
| Cases | **25** (23 authored + 2 regression) |
| Taxonomy modes covered | **5**, names taken verbatim from `taxonomy.md` |
| Assertions vs judged criteria | **5 assertions vs 1 judged criterion** (was 0 vs 5) |
| Hand labels | **25**, blind, committed at **`6d36d0b`** |
| First judge verdict commit | **`7db4bc5`** — *after* the labels |
| **agreement_before** (judge_v1) | **80.0%** — 20/25 |
| **agreement_after** (judge_v2) | **80.0%** — 20/25 |
| Judge-too-lenient cell | **2 → 0** |
| Judge-too-strict cell | **3 → 5** |

**The headline number did not move by a single case, and the judge got
materially better anyway.** That is the finding.

---

## 1. Blind protocol — the ordering is provable

```
6d36d0b  Week 6: 25 blind hand labels, committed BEFORE the judge is run
7db4bc5  Week 6: judge_v1 run, agreement_before = 80.0% (20/25)
57defc4  Week 6: prediction for the judge iteration, filed before judge_v2 exists
6b571d0  Week 6: judge_v2, built from two of judge_v1's own disagreements
1c40d49  Week 6: judge_v2 run, agreement_after = 80.0%
```

`6d36d0b` contains `eval/labels_25.json` and **no judge output of any
kind**. `7db4bc5` is the first commit in the repository containing a
verdict. `git log` is the evidence.

The ordering is also **enforced in code, not merely intended**:

```python
if not Path(args.labels).exists():
    raise SystemExit(
        "Refusing to run the judge: no labels at '...'.\n"
        "The 25 hand labels must be written and committed BEFORE the "
        "judge runs, or the agreement figure means nothing."
    )
```

So it was not possible to read the verdicts first and then write labels
that agreed with them.

**What the labeller saw:** the adjuster notes, the POLICY WORDING blocks
actually retrieved, and the summary. Nothing else — no assertion results,
no judge output, and not the `wording_says` note from the case file.

**Class balance, declared up front rather than discovered later.** The
labels came out **20 faithful / 5 unfaithful**, and `labels_25.json` says
so in a `class_balance_warning` field written before the judge ran:

> A judge that answered "faithful" every time would score 80% agreement on
> this set without reading anything. Raw agreement is therefore a weak
> statistic here and the confusion cells matter more than the headline.

That warning turned out to be the whole story. See §4.

---

## 2. Assertion / judge split — 5 assertions vs 1 judged criterion

`eval/judge_v0.txt` is the judge as it stood before the split: five
criteria, one model call, one number out. Four of the five were checkable
by a machine and were being paid for by the token.

| Criterion | Before | After |
|---|---|---|
| Claim number echoed in `CLM-YYYY-NNNNN` form | judged | **assertion** |
| Date of loss present and parseable | judged | **assertion** |
| Excess/deductible amount numeric | judged | **assertion** |
| Exclusion clause id cited whenever a denial is stated | judged | **assertion** |
| Every cited `chunk_id` resolves to a retrieved chunk | — | **assertion** (added) |
| Coverage statements supported by the retrieved wording | judged | **judged** — the only one left |

All four moved criteria are **deleted** from the judge prompt; the diff
`judge_v0.txt` → `judge_v1.txt` shows them removed and replaced by an
explicit instruction not to judge them.

The assertions do more than the judge did. `claim_number_echoed` does not
merely check the format — it checks the number is *the right one*, because
a correctly-shaped invented claim number is worse than a missing one: it
routes the file to a claim that exists and belongs to someone else.

### Assertion results — 1/25 pass

```
claim_number_echoed            0 failures
date_of_loss_parseable         0 failures
deductible_numeric            24 failures
exclusion_cited_on_denial      4 failures
citations_resolve              6 failures
```

**24 of 25 summaries state no deductible.** This is the Week 5 finding
reproduced on an independent 25-case set — `taxonomy.md` recorded 10 of 10
on the traces. The cause is unchanged: a summary issues one retrieval with
`top_k=3` and the exclusion table wins all three slots.

These five checks now cost nothing, never disagree with themselves between
runs, and never have an off day.

---

## 3. The one-command eval

```
python tools/run_w6.py
```

Generates the summaries, runs the assertions, runs the judge, and prints
the table. Terminal output (`eval/w6_table.txt`):

```
taxonomy mode                                        n   assert  faithful     pass
----------------------------------------------------------------------------------
Answers without the clause that decides the claim   10   0/10        5/10     0/10
Comes back with the wrong product's wording ...      3   0/3         2/3      0/3
Coverage position field contradicts its narrative    5   1/5         5/5      1/5
Quotes a clause under the wrong number ...           4   0/4         1/4      0/4
Reports no deductible or excess figure               3   0/3         2/3      0/3
----------------------------------------------------------------------------------
ALL                                                 25   1/25       15/25     1/25
```

Reported **by mode**, never as one average, because an average over 25
cases hides exactly what this table is for. *Coverage position field
contradicts its own narrative* is the only mode with any assertion pass at
all (1/5) and the only mode with a full pass — a single overall figure of
1/25 would have said the app is uniformly broken, and it is not.

The two regression cases carry their own rows in the JSON with
`source_trace_id` recorded:

| Case | From trace | What went wrong in production |
|---|---|---|
| `reg-c12` | `tr-wk5-0012` | Returned **COVERED** for a pipe that froze with the heating off entirely. E-14 excludes exactly that; the retrieved exclusion chunk carried only E-15/E-16/E-17. |
| `reg-c06` | `tr-wk5-0006` | Returned UNDETERMINED and attributed the secondary-power requirement to Clause 4.1. It is Clause 2.2, which was never retrieved. |

Their `notes` are copied character for character from the trace file.

---

## 4. Agreement, before → after

### agreement_before = 80.0% (20/25), judge_v1

```
cells: 17 both-faithful | 3 both-unfaithful | 2 judge-too-lenient | 3 judge-too-strict
judge too lenient : w6-01, w6-12
judge too strict  : w6-09, w6-10, w6-17
```

**80% is exactly what a judge answering "faithful" every time would have
scored** on a 20/5 label set. The judge is not that judge — it found 6
unfaithful where the constant answer finds 0, and 3 of the 6 were right —
but *the headline number alone cannot tell those two judges apart.* This is
the reason the labels file declared the imbalance before the run.

### The iteration

judge_v1's five disagreements were not five problems. They were two:

- **Too strict** (`w6-09`, `w6-10`, `w6-17`) — all three ruled unfaithful
  because a **citation** pointed at the wrong clause or chunk. The
  proposition was supported every time; only the pointer was wrong. And
  `citations_resolve` already checks that deterministically.
- **Too lenient** (`w6-01`, `w6-12`) — both accepted a **blanket negative
  claim** over an exclusion table the summary had only partly been shown.
  `w6-12` is the expensive one: "the exclusion table … does not cover
  general water damage from a pipe split", written from five of ten rows,
  with the dwelling twenty weeks vacant and E-72 among the five it never
  saw.

`judge_v2` adds one rule per direction, each carrying **a worked example
lifted verbatim from a case judge_v1 got wrong** — `w6-17` for the citation
rule, `w6-12` for the blanket-negative rule. Both examples are visible in
the `judge_v1.txt` → `judge_v2.txt` diff.

### agreement_after = 80.0% (20/25), judge_v2

```
cells: 15 both-faithful | 5 both-unfaithful | 0 judge-too-lenient | 5 judge-too-strict
judge too lenient : (none)
judge too strict  : w6-02, w6-04, w6-05, w6-09, w6-15
```

| | before | after |
|---|---:|---:|
| agreement | 80.0% | **80.0%** |
| judge-too-lenient (**misses a payout**) | 2 | **0** |
| judge-too-strict (wastes an afternoon) | 3 | 5 |

**judge_v1 missed 2 of the 5 unfaithful summaries. judge_v2 misses none.**
It buys that with two more false alarms. Those costs are not symmetric —
a false alarm costs an adjuster an afternoon, a miss costs a payout that
should not have happened — so the judge improved on the axis that matters
while the headline stood still.

A team reporting only "agreement: 80% → 80%, no change" would have
concluded the iteration failed and reverted it.

---

## 5. Where the prediction was wrong

The prediction (`w6_prediction.txt`, commit **`57defc4`**, filed before
judge_v2 existed) said, in one sentence:

> Adding `w6-17` and `w6-12` as few-shot examples will fix all three
> too-strict cases and both too-lenient cases, taking agreement from 80% to
> **100% (25/25)**.

**Actual: 80%.** Scored honestly:

| Prediction | Outcome |
|---|---|
| Both lenient cases fixed | ✅ `w6-01` and `w6-12` both flipped |
| All three strict cases fixed | ❌ `w6-10` and `w6-17` fixed; **`w6-09` did not** |
| Agreement → 100% | ❌ **80%** — four *new* false alarms appeared |
| "I expect w6-01 not to flip" | ❌ **wrong** — it flipped cleanly |

**Wrong in three ways, and the most interesting one is the third.**

I predicted `w6-01` was the case least likely to flip, because I had
labelled it unfaithful only to stay consistent with `w6-12` under my own
rule (d), and its unseen exclusion rows genuinely do not apply. I expected
the judge to learn "unfaithful when the unseen row *matters*". It did not —
it learned the rule as stated, "unfaithful when you cannot know whether it
matters", and applied it to `w6-01` correctly. **The judge generalised the
principle better than I predicted it would**, and it did so from a single
example.

And then it kept generalising, which is the second thing I got wrong. I
flagged a collateral-damage risk in the prediction, but described the wrong
one — I worried the citation rule would excuse a citation to a form never
retrieved. Instead the *blanket-negative* rule over-fired. All four new
false alarms cite it, in the judge's own words:

- `w6-04` — "makes a blanket negative claim that 'No exclusion applies'"
- `w6-05` — treats the **field** `Exclusion relied on: NONE` as a blanket claim
- `w6-15` — "'No other coverage clauses apply'" — on a **DENIED** position
- `w6-09` — on a **DENIED** position

Three of the five strict cases are DENIED positions, where a blanket
negative cannot inflate coverage and therefore cannot be load-bearing. My
rule says *"and that claim is load-bearing for the position taken"*; the
judge is not applying that qualifier. That is a precise defect with a
precise fix — restrict the rule to COVERED and UNDETERMINED positions.

**I have not made that fix.** Iterating a third time against the same 25
cases until the number improves is how you get a judge tuned to 25 cases,
and the brief is explicit that moving the ruler is not moving the thing
being measured.

### The disagreement where the judge may be right and I may be wrong

On `w6-02` judge_v2 said:

> …specifically ignoring **E-16** for wet rot, which is explicitly listed in
> the provided wording and directly applicable to the loss…

E-16 ("Rust, corrosion, wet rot or dry rot forming before the discharge")
*was* in the retrieved wording, and the loss involves wet rot to the
joists. I labelled that case faithful and did not consider E-16 at all.
Whether E-16 reaches rot that formed *from* eleven weeks of seepage rather
than *before* it is genuinely arguable.

**The label has not been changed.** Relabelling the case I disagreed with
would move agreement from 80% to 84% and would be precisely the failure the
brief names: agreeing with yourself with extra steps.

### Two disagreements read in full, with a verdict on who was right

| Case | Human | judge_v1 | judge_v2 | Who was right |
|---|---|---|---|---|
| `w6-12` | unfaithful | faithful | unfaithful | **Human.** The summary concluded the exclusion table "does not cover general water damage from a pipe split" from five of ten rows. The dwelling was vacant twenty weeks and E-72 — plumbing water damage in a dwelling vacant over 60 days — was among the rows it never saw. judge_v1's reason ("the analysis of the exclusion table is directly supported") shows it checked the rows in front of it and never asked whether those were all the rows. judge_v2 catches it. |
| `w6-17` | faithful | unfaithful | faithful | **Human.** The summary correctly applied three different dispositions (E-33 above $2,500, E-37 above $5,000, E-31 absolute) and correctly computed 2% of $580,000 = $11,600 against a $1,000 minimum. judge_v1 failed it because a `chunk_id` pointed at a neighbouring block. That is a citation defect, checked by `citations_resolve`, and calling it an unfaithfulness marks a summary that read the policy correctly as one that invented coverage. judge_v2 fixes it. |

---

## 6. The judge model changed mid-exercise, and why

The first `judge_v1` run returned **22 of 25 verdicts as HTTP 429**. Week
5's traffic had already spent `gpt-oss-120b`'s 200,000-token daily budget,
which refills at roughly 139 tokens a minute, so the API was asking four
minutes per call.

The run reported **"3 scored, 22 unscored"** — not a 100% agreement figure
computed from three cases. That is the entire reason `judge_summary`
returns `faithful=None` on error and `agreement()` drops unscored cases
from the denominator instead of counting them either way: **an outage must
not be able to move the number**, in either direction.

The judge is now `qwen/qwen3.8-27b` — a **different model family** from the
`gpt-oss-20b` generator. That is a stronger independence property than the
bigger gpt-oss sibling would have given: a judge sharing a tokenizer, a
training corpus and a house style with the thing it grades will forgive its
own idioms. Both judge runs used it, so the before/after comparison varies
the prompt and nothing else.

---

## Reproducing this

```bash
python tools/run_w6.py                                   # everything
python tools/run_w6.py --stage summaries                 # generate + assert only
python tools/w6_label.py --slice 0:5                     # what the labeller saw
python tools/run_w6.py --stage judge --judge judge_v1    # refuses without labels
python tools/run_w6.py --stage agreement --judge judge_v2
```

---

## Submission checklist

- [x] `eval/labels_25.json` — commit **`6d36d0b`**, before any verdict exists
- [x] `eval/judge_v1.txt` and `eval/judge_v2.txt`, diffed, both disagreement examples visible in v2
- [x] `w6_prediction.txt` — commit **`57defc4`**, before judge_v2 was authored
- [x] Terminal output of the single eval command, pass rate by mode — `eval/w6_table.txt`
- [x] agreement_before **80.0%** / agreement_after **80.0%**, with the cells that show what actually changed
- [x] Assertion count **5** vs judged criteria count **1**

---

## Bonus — RAGAS faithfulness and context precision

**Not the `ragas` package.** Installing it into this project's venv failed
repeatedly: a locked `jiter` `.pyd` left the environment without `openai`
at all and the pipeline had to be repaired before anything else could run.
The two metrics are therefore computed in `tools/w6_ragas.py` against the
published RAGAS definitions rather than by the library. That is a real
difference and it is stated rather than glossed — these are RAGAS-*defined*
metrics, not RAGAS-*library* outputs.

```
faithfulness       decompose the summary into atomic claims about the policy,
                   ask of each whether the retrieved passages entail it
                       = supported / total_claims

context_precision  (reference-free, LLM-judged) mark each retrieved passage
                   useful or not, then average precision@k over useful ranks
                       = sum_k (precision@k * v_k) / sum_k v_k
```

Scored on the **23 policy-backed cases** — the ones that retrieved actual
policy wording. `w6-14` and `w6-21` are excluded: they retrieved nothing but
the flood manual, so there is no policy wording for them to be faithful
*to*, and scoring them would put a number in the average for a reason
unrelated to the summary.

```
mean faithfulness      0.9957      (n = 23)
mean context precision 0.9130      (n = 23)
```

Both look like a healthy system. A dashboard showing that pair reads green.

### Confidently, faithfully wrong

The brief asks for one summary scoring 0.9+ faithfulness while retrieving
the wrong policy wording. The run produced something sharper, and it is not
one case but every one of them:

> **All five summaries I hand-labelled UNFAITHFUL score faithfulness
> exactly 1.000.** So does the regression case whose production output paid
> a claim it should have denied.

| case | faithfulness | context precision | human label | judge_v2 |
|---|---:|---:|---|---|
| `reg-c06` | **1.000** | 1.000 | **UNFAITHFUL** | UNFAITHFUL |
| `w6-01` | **1.000** | 0.833 | **UNFAITHFUL** | UNFAITHFUL |
| `w6-06` | **1.000** | 1.000 | **UNFAITHFUL** | UNFAITHFUL |
| `w6-12` | **1.000** | 1.000 | **UNFAITHFUL** | UNFAITHFUL |
| `w6-22` | **1.000** | 1.000 | **UNFAITHFUL** | UNFAITHFUL |
| `reg-c12` | **1.000** | 0.833 | faithful | faithful |

`reg-c12` is the purest case in the set: **faithfulness 1.000, context
precision 0.833**, and it is the regression case whose production output
returned **COVERED for a pipe that froze with the heating switched off
entirely**, because E-14 was never among the retrieved rows. Faithfulness
1.000 on a payout that should not have happened.

This is not the metric misfiring. It is the metric working exactly as
defined and answering a different question than the one that matters.
Faithfulness decomposes a summary into claims and checks each **against the
passages that were retrieved**. The defect in all five is a claim about
wording that was *not* retrieved:

- `w6-01` asserts "No other exclusions from the endorsement apply" having
  been shown 8 of 12 exclusion rows.
- `w6-12` concludes the exclusion table "does not cover general water damage
  from a pipe split" from five of ten rows, with the dwelling twenty weeks
  vacant and E-72 among the five it never saw.
- `reg-c06` treats a dead battery as a coverage condition on Clause 4.1,
  which requires only that the power source be *retained for inspection*.
- `w6-06` welds Clause 4.2's records requirement into the Clause 2.2 grant.
- `w6-22` assumes groundwater — a condition E-11 requires and the notes
  explicitly do not establish — and denies absolutely on it.

Every atomic claim in every one of them is entailed by a passage that was in
front of it. **A metric computed against the retrieved context is
structurally incapable of noticing the context was incomplete.**

### Why the averages hide it

Two separate mechanisms, and they are worth telling apart:

**1. Faithfulness has no variance left to hide anything with.**

```
faithfulness   1.000 x 22 cases
               0.900 x  1 case
```

Twenty-two of twenty-three cases return the identical value. A metric that
scores a correct denial, a correct coverage grant, and a summary that
invents a coverage condition all at exactly 1.000 is not measuring what
separates them — it is measuring whether the model quoted its inputs, and
this model always does. Mean 0.9957, usable information content near zero.
**The average does not hide the signal; there is no signal to hide.**

**2. Context precision does carry signal, and the mean flattens it.**

```
context precision   1.000 x 18      0.833 x 2
                    0.500 x  2      0.333 x 1
```

`w6-03` scores **0.333** — two of its three retrieved passages contributed
nothing the answer used — against a mean of 0.913. Eighteen cases at 1.000
drag the mean up until the three genuinely wasteful retrievals (`w6-03`,
`w6-18`, `w6-20`) vanish into a rounding difference. Per-case, retrieval
wasted two of three slots on 1 case in 23 and one of two on two more; in the
mean, that is 0.913 and looks like nothing.

**The pair is the finding.** Either number alone is reassuring and wrong:
faithfulness says the summary used its sources, context precision says the
sources were on topic, and **neither can say that the source which decides
the claim was never retrieved** — which is the top mode in `taxonomy.md`, at
20% of the Week 5 sample, and the one that pays out money it shouldn't.
