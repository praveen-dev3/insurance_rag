# Week 7 Practical — Task Set D

## Race the claims agent against a fixed workflow

**Domain:** insurance claims · **Model:** `openai/gpt-oss-20b` (Groq, `reasoning_effort=low`) ·
**Cases:** 10 claims, 3 flagged `dependency` (`tools/data/w7d_claims.py`) · **Corpus:**
the six endorsement forms in `tools/data/endorsement_content.py`, searched by
`tools/w7d_policy_corpus.py`

---

## The numbers

| metric | agent | workflow |
|---|---:|---:|
| pass rate | **9/10** | **8/10** |
| p50 latency | **43.72 s** | **8.38 s** |
| total tokens (10 claims) | **82,769** | **11,889** |
| cost / claim | **$0.00069** | **$0.00013** |

Full per-claim rows: [eval/w7d/race.csv](eval/w7d/race.csv). Headline JSON:
[eval/w7d/race_summary.json](eval/w7d/race_summary.json). Reproduce with:

```
python weeks.py w7d-race --stage race
```

**The workflow wins three of the four numbers outright — latency, tokens and cost, by
5-7x — and loses the fourth by exactly one claim out of ten.** That one claim is not
free-form flakiness: the agent and workflow disagree on the *same* two claims in
opposite directions (below), and only one of those two disagreements is the kind Task
Set D's dependency clause describes.

---

## 1. Where they actually differ

Both systems got 7 of the 10 claims right *and agreeing*. Where they diverge:

| claim | dependency? | golden | agent | workflow |
|---|:---:|---|---|---|
| c03 | no | excluded (E-17, seepage ≥14 days) | excluded ✓ | **covered ✗** ($3,700) |
| c04 | **yes** | covered under HO-0521 ($13,000) | covered ✓ | **excluded ✗** ($0) |
| c07 | no | excluded (E-34, cosmetic, no penetration) | **covered ✗** ($3,000) | excluded ✓ |

c04 is the claim `tools/data/w7d_claims.py` names as the clearest dependency case: HO-0304's
own exclusion table (E-19) redirects sewer back-up to HO-0521, and only HO-0521's own
clauses — found by a *second* search, against a form nobody knew to check before reading
the first result — say whether the claim is actually payable. The agent chased that
redirect turn by turn and got it right. The workflow's step 2b hard-codes exactly this
redirect-and-re-search branch, and it worked — every clause the agent used (HO-0521's
coverage grant, its $1,000 deductible, the battery-backup condition) was sitting in the
workflow's single prompt too (verified by hand against the exact prompt sent). The
workflow's one-shot decision call read "excluded here" off the first form and stopped,
without following through to the form the exclusion named. That is a *reasoning* failure
inside one call, not a *retrieval* failure and not a control-flow ceiling — the branch to
fetch the right text already existed and ran.

c07 cuts the other way: a hail claim with cosmetic-only damage (no penetration), which
E-34 excludes outright. The workflow's single call read the exclusion correctly. The
agent, given five tool calls' worth of room to reconsider, talked itself into "covered"
anyway and priced a windstorm deductible for a claim that was never payable. This is not
the dependency pattern either — it is the inverse failure, a multi-turn agent overriding
a clause it already had in front of it.

c03 (excluded ✓ for the agent, wrongly covered for the workflow) turns on the same class
of issue as c04: the workflow's one-shot call under-weighted the E-17 duration clause
("occurring over a period of fourteen (14) days or more") against a notes description
("dripping slowly for approximately three weeks") that never says "fourteen days" in so
many words. The agent's multi-turn search surfaced the clause and the note attached to it
in a dedicated turn and applied it correctly.

---

## 2. The third tool

Requirement: one job, an enum for the claim-status parameter, no overlap with `get_claim`
or `search_policy`. Full diff: [eval/w7d/tool_description_diff.md](eval/w7d/tool_description_diff.md).

**Draft (rejected):** `"description": "Handles the claim decision and payout."`, with a
free-string `status` parameter. Two jobs in one tool ("decide *and* compute"), no enum,
and "handles the claim" overlaps both `get_claim` ("handles" the claim file) and
`search_policy` (deciding coverage from wording is what searching is *for*).

**Final:**

```json
{
  "name": "compute_payout",
  "description": "Compute the payable amount for one already-assessed claim: the loss amount minus the deductible when the claim is covered, zero otherwise. Does not decide coverage, does not fetch a claim file, and does not search policy wording - call get_claim and search_policy first and pass in what they found.",
  "parameters": {
    "claim_id": {"type": "string"},
    "claim_status": {"type": "string", "enum": ["covered", "excluded", "undetermined"]},
    "loss_amount": {"type": ["number", "null"]},
    "deductible": {"type": ["number", "null"]}
  }
}
```

One job (arithmetic on numbers it is handed), an enum on `claim_status`, and each
sentence of the description names a boundary against one of the other two tools by name.

---

## 3. Budget enforcement and the termination log

All four budgets (`Budget` in `tools/w7d_common.py`) are checked in `run_agent`'s loop
*before* every model call, not after: `max_iterations=10`, `max_tokens=16000`,
`max_cost_usd=0.02`, `max_wall_clock_s=90.0` — sized off the real race (the deepest
claim, c04, took 6 laps / ~12k tokens / ~86s including one rate-limit wait), so none of
the 20 real runs above ever tripped one.

To prove the check actually fires rather than being an unenforced constant, `budget-demo`
reruns c04 with `max_iterations` deliberately set to 1:

```
python weeks.py w7d-race --stage budget-demo
```

```
budget-termination demo: claim c04, max_iterations=1

[lap 1] calling openai/gpt-oss-20b, 2 messages so far
[lap 1] tool get_claim({'claim_id': 'c04'}) -> {'claim_id': 'c04', ... 'form_number': 'HO-0304', ...}
[budget] max_iterations (1) reached before lap 2

outcome: budget_exceeded
budget_reason: max_iterations
iterations used: 2
wall_clock_s: 2.117
```

Full log: [eval/w7d/budget_termination.log](eval/w7d/budget_termination.log). The loop
completes `get_claim`, then stops cleanly with `outcome="budget_exceeded"` and a named
reason instead of proceeding to `search_policy` — no exception, no retry, no spin. The
other three budgets (`max_tokens`, `max_cost_usd`, `max_wall_clock_s`) are checked with
the identical pattern on the same line of the loop; `max_iterations` is exercised here
because it is the one a single lap can deterministically trip.

---

## 4. Verdict

The decision rule: does the path vary by input beyond what fixed branches anticipate?
Here it doesn't - every claim's control flow was one of three shapes, and the workflow's
one `if` branch (step 2b, redirect-and-re-search) covers all three unmodified. c04, the
dependency case, is where that branch *worked* and the one-shot decision call still read
it wrong: a prompting failure inside one call, not a control-flow ceiling only a loop
climbs. Weighed against a 5x latency and 7x token/cost tax for one extra pass, plus a
second disagreement (c07) where the agent's extra turns talked it out of the answer a
single call got right, the honest reading is that **no claim here required an agent** -
it required the one decision call to read a redirected form's clauses as carefully as the
first form's, which is a prompt fix, not an architecture change.

---

## 5. Submission checklist

- [x] Agent and workflow both runnable by one command each — `python weeks.py w7d-race --stage race`
      runs both over the same 10 claims (`run_agent` / `run_workflow` in
      `tools/w7d_agent.py` / `tools/w7d_workflow.py`)
- [x] race.csv / table with all 8 numbers over the same 10 claim numbers —
      [eval/w7d/race.csv](eval/w7d/race.csv), table in §"The numbers" above
- [x] Log excerpt of the budget-triggered termination, showing which budget fired —
      [eval/w7d/budget_termination.log](eval/w7d/budget_termination.log), §3 above
- [x] Diff of the third tool's description and parameter enums —
      [eval/w7d/tool_description_diff.md](eval/w7d/tool_description_diff.md), §2 above
- [x] Verdict paragraph naming the claim class that does or does not need an agent — §4 above
