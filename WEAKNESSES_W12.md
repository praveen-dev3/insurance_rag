# Top-3 known weaknesses

**Dated 2026-10-05, written after the eval run and before any review.** The brief asks for these to be written on
the Wednesday "before anyone asked". I cannot backdate that and have not tried: this is the list as of the end of the
build, written without a reviewer's prompting. Ranked by what I would fix first.

## 1. The no-decision guard is a pattern list, and a pattern list is not a guarantee

`tools/w12_guard.py` rewrote 19 of 25 referrals (76%) - and still let two through that a human reading the output
marked as stating an outcome: `w03` ("indicating the loss falls under that exclusion", `req-bb2b5a59d5e7`) and `w15`
("exclusion E-66 may apply because the vehicle was left in a location warned about flooding", `req-81aea0cc551a`,
which also invented the warning). Both passed `no_decision_language`, because the assertion uses the same kind of
pattern the guard does. The other direction hurts too: 13 of the 19 rewrites were a citation line that merely
restated an exclusion row ("Excludes flood loss to the dwelling"), so the adjuster got a templated summary instead
of the facts. A regulator's "never state a coverage decision" is a *meaning* test, and nothing here tests meaning
except an LLM judge that agrees with my labels 68-84% of the time depending on how it is configured. **Fix first:** a second, independent check that
reads the emitted prose (the judge, scoped to this one question, with labels from someone else), and a guard that
distinguishes quoting wording from applying it.

## 2. 80% on a corpus small enough to be easy, with one run per case

36 chunks in 6 documents; hit-rate@3 over that is near-trivial, and the date filter's measured cost of **0.0 points**
is a statement about the corpus, not about the filter. The straddle cases the brief cares about scored 5/9, and the
causes (a coverage clause crowded out of the top 3; a model that cites a clause because a note mentions it) are
the ones that get *worse* with 60-page wordings, not better. One model, one run per case, 25 of 31 cases: the
80% could be 65% or 95% on a re-run and nothing here says which. **Fix first:** index the real exclusions schedule
and measure hit-rate@3 per mode; run each case 3 times and report pass^3.

## 3. The free tier cannot carry even steady state, and the only limit measured is a single request

One triage is ~11,000 tokens; the daily allowance is 200,000; **18 claims a day** against the brief's 60. That is
not a hailstorm problem, it is a Tuesday problem, and it ate this project twice: Week 11's 20b suite spent the day's
tokens, and 6 of 31 capstone cases and the agent-level no-filter arm never ran because of it. Nothing was run under
concurrent load, the policy-wording server is one single-threaded process, and the latency figures include rate-limit
waits that a span cannot distinguish from slow generation. **Fix first:** a paid tier or a second provider, then a
queue in front of the agent that admits work at the rate the limit allows and says so.

## Smaller, known

- The PII audit searches for literals it was *given*; a name nobody registered, in free text, would pass it.
- The judge agrees with my labels 76% of the time on first measurement (68-84% across three variants), against labels from one non-human labeller - below the 85% the brief sets, and worse when I "improved" it.
- An edition is chosen by loss date alone; the renewal-date rule that a real policy follows is not modelled.
- The redundant-FNOL fix (SEAMS #9) and the pair-completion fix (SEAMS #11) were not re-measured at agent level.
