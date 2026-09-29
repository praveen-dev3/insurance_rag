# Week 10 Practical — Task Set D

## Race the claims squad against your single agent

**Systems under test:** `tools/w7d_agent.py`'s `run_agent` (the single agent, unchanged
since Week 7) against `tools/w10d_orchestrator.py`'s `run_orchestrator` (new this week) —
three hand-offs, not one loop: a notes-summary worker, an exclusions worker restricted to
`search_policy` + `compute_payout` only (never `get_claim`, never the raw adjuster notes —
it gets the notes-summary worker's distilled JSON instead), and a synthesis step that
composes the final answer. Same 10 Week-6 eval cases every Task Set D since Week 7 has
used (`data/w7d_claims.py`), same judge (`grade()` from `w7d_common.py`), same model.

Reproduce everything below with:

```
python weeks.py w10d-eval --stage race      # both arms, 4 metrics, multiplier
python weeks.py w10d-eval --stage failure   # inject a 500 on c04
python weeks.py w10d-eval --stage verdict   # keep/kill from the numbers above
python weeks.py w10d-eval --stage all       # all three, in order
```

---

## 1. The race table

`eval/w10d/race.csv` (one row per system per claim), `eval/w10d/race_table.md`:

| metric | single agent | orchestrator |
|---|---:|---:|
| pass rate | 7/10 (0.700) | 7/10 (0.700) |
| p50 latency (s) | 44.65 | 38.41 |
| p99 latency (s) | **4577.32** | 63.98 |
| total tokens (10 claims) | 72,469 | 63,081 |
| cost per claim (USD) | $0.00061 | $0.00059 |

Pass rate ties exactly at 7/10, but **not on the same claims** — same disjoint-failure
shape Week 8 found between outcome and trajectory evals, this time between the two
systems:

| | single-agent FAIL | single-agent PASS |
|---|---|---|
| **orchestrator FAIL** | c04, c07 | c06 |
| **orchestrator PASS** | c03 | c01, c02, c05, c08, c09, c10 |

c04 (the HO-0304→HO-0521 redirect claim) and c07 (hail granule-loss, no penetration) beat
both systems the same way; c03 (a slow drip past the "abrupt" wording) is a single-agent
miss the orchestrator's narrower worker got right; c06 (hail with penetration) is the
reverse — the orchestrator's exclusions worker reached the right coverage call but
mis-resolved the deductible (`payout 22000.0 != 16000`), a computation error the single
agent, working from the same tools, did not make on this run.

**The p99 number is the one worth not averaging away.** Single-agent p99 is 4,577s (76
minutes) — driven entirely by `c01` hitting a Groq free-tier rate-limit wait
(`wall_clock_s=5022.9` in `eval/w10d/race.csv`), the exact kind of shared-tenancy stall
Week 8's own race notes already documented on a different claim. That is **not** evidence
the single-agent architecture is inherently 80x slower than the orchestrator at p99 — it
is one external rate-limit hit landing on one arm's run. Reported anyway, because Task Set
D's own common-mistakes list names exactly this failure: "reporting p50 only because p99
was embarrassing."

---

## 2. The context re-send multiplier — and the surprise

**Multiplier: 0.9x** (63,081 orchestrator tokens / 72,469 single-agent tokens). The
orchestrator did **not** cost more here — the common mistake Task Set D's own list warns
about ("re-sending the full adjuster note history to both workers on every hop, then
concluding multi-agent is inherently expensive") is the mistake this design specifically
avoided: the exclusions worker never receives the raw notes, only the notes-summary
worker's distilled JSON (a few hundred tokens instead of a full note block repeated into
every hand-off).

**Dominant hand-off, from `eval/w10d/handoffs.log`: `orchestrator -> exclusions-worker`,
53,194 of 63,081 tokens — 84% of all orchestrator tokens.** That is not the "resend"
tax the multiplier's usual bad case names — it is the same cost driver the single agent
has too: a multi-lap tool-calling loop over `search_policy`/`compute_payout` (3–5 laps
per claim here). Splitting the notes summary and synthesis into their own cheap hand-offs
(7% and 9% of the token bill respectively) barely moved the total, because the loop that
actually costs tokens was never the one being split out.

---

## 3. Worker-failure injection: c04, exclusions worker returns HTTP 500

`tools/w10d_orchestrator.py`'s `_run_coverage_worker` raises `ClaimsWorkerError("HTTP
500: ...")` before making any call of its own when `inject_failure=True` — simulating the
worker process itself being down, not a mid-call error. **No retry logic exists anywhere
in the orchestrator**, so what happens next is the un-engineered default, not a designed
fallback (`eval/w10d/failure_case.md`):

| | status | payout | `compute_payout` called? | grade |
|---|---|---:|---|---|
| clean (no fault) | covered | 13,000 | yes | PASS |
| **HTTP 500 injected** | **undetermined** | **0** | **no** | FAIL |

**Verdict: degraded, not lied, not retried.** The synthesis step's rationale states
plainly: *"Coverage determination could not be made due to a system error preventing the
exclusions worker from processing claim c04."* It did not fabricate a coverage position
from the notes-summary alone — the exact "declares the claim covered with no exclusions
check" failure Task Set D §4 warns about did **not** happen on this run. That is a
property of the synthesis prompt's explicit instruction not to round a conditional finding
up to plain coverage (§SYNTHESIS_SYSTEM in `w10d_orchestrator.py`), not a guarantee — a
model that ignored that instruction under the same missing-worker input would have
produced exactly the dangerous case instead, and nothing downstream of the synthesis call
would have caught it.

---

## 4. Verdict

`eval/w10d/verdict.md`:

> **KEEP** — tied pass rate (7/10 both) is not itself a reason to switch, but a strictly
> cheaper bill (0.9x, not >1x) with no latency downside is: the narrow-prompt-fewer-tools
> worker split earns its keep on cost alone here, even though it did not buy a single
> extra correct claim.
>
> **Sunk-cost warning, named out loud:** two weeks (7–9) of tooling were built for the
> single agent — that history is not a reason to keep it now that a cheaper option ties it
> on pass rate, and it is equally not a reason to switch just because the orchestrator is
> newer.

Cited numbers: the 0.9x token multiplier (§2) and the tied 7/10 pass rate (§1). Latency is
named but not load-bearing on its own — p99's gap is a rate-limit artifact (§1), not an
architecture result.

---

## 5. Bonus challenge

### AgentCard the orchestrator would advertise

```json
{
  "name": "claims-triage-orchestrator",
  "description": "Decomposes a homeowners/dwelling-fire claim into an adjuster-note summary and a coverage/exclusions check, then synthesises a cited coverage and payout decision.",
  "url": "https://internal.example/agents/claims-triage-orchestrator",
  "version": "0.1.0",
  "capabilities": {"streaming": false, "pushNotifications": false},
  "defaultInputModes": ["application/json"],
  "defaultOutputModes": ["application/json"],
  "skills": [
    {
      "id": "triage-claim",
      "name": "Triage one claim",
      "description": "Given a claim ID, returns coverage_status, exclusion_code, deductible and payout, cited to the policy form searched.",
      "inputModes": ["application/json"],
      "outputModes": ["application/json"]
    }
  ],
  "authentication": {"schemes": ["bearer"]}
}
```

Deliberately one skill, not three — the two workers and the synthesis step are internal
hand-offs, not capabilities this orchestrator advertises to a caller; a caller asking a
different agent for `triage-claim` should not need to know the exclusions worker exists,
same reasoning as `w9d_run.py`'s host/capability split (§4 of that write-up).

### The failed case on the A2A task lifecycle

`c04` (§3, HTTP 500 injected) reached a state with `coverage_status="undetermined"` —
under A2A's task lifecycle this is not `failed` (the pipeline did complete and return a
well-formed response, it did not crash) and it is not silently `completed` either (the
business question was not actually answered). It should have ended **`input-required`**,
not `failed`: the honest next step for an undetermined coverage finding caused by a
down dependency is to pause for an adjuster to either re-trigger the check or manually
confirm coverage — not to hand the caller a terminal answer that reads as final. The
orchestrator currently has no `input-required` state to return into; it collapses the
"worker is down" and "worker said undetermined for a legitimate reason" cases into the
same terminal `completed` response, which is a real gap this exercise did not close.

**What A2A buys over a plain REST call to the worker, in two lines:** a REST call to the
exclusions worker returns 200 or an error with no shared vocabulary for "I need more
information before I can finish" — A2A's task states (`submitted → working →
input-required/failed/completed`) give the *caller* a standard way to tell "still
working," "stuck and needs you," and "done" apart without inventing its own status
codes. That distinction is exactly what this orchestrator's `undetermined` output
currently erases.

---

## 6. Submission checklist

- [x] `eval/w10d/race_table.md` — 4 metrics x 2 arms, same 10 named claims — §1
- [x] `eval/w10d/handoffs.log` — every hand-off, per claim, with its token count — §2
- [x] Multiplier line: 0.9x, attributed to `orchestrator -> exclusions-worker` (84%) — §2
- [x] `eval/w10d/failure_case.md` — the injected 500 and what the orchestrator actually did (degraded) — §3
- [x] `eval/w10d/verdict.md` — KEEP, two numbers cited, sunk-cost named — §4
- [x] Bonus: AgentCard + A2A task-lifecycle mapping — §5
