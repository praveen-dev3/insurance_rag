# The drill: find the coverage answer that ignored an exclusion

**Complaint, verbatim and complete:** "an adjuster says it told a claimant something was covered when the policy
excludes it, sometime yesterday." No trace id, no claim number, no timestamp.

## Result

| | time-to-find | slice that found it | field that made it quick |
|---|---|---|---|
| **Drill 1** (baseline log) | **01:47** | **time** (yesterday) **x output text** (`coverage_status: covered`, input type `claim_triage`) -> 10 hits over 6 distinct claims -> resolve each candidate's `context_ids` to clauses -> read the claim notes in the claims system | `output.coverage_status` (the answer is a structured, indexed field, not just text inside a blob) and `context_ids` (so "was the controlling exclusion in front of the model?" is a lookup) |

Found: `req-b0c8b1c0efcf`, 2026-10-04 16:35 UTC, user `u-1291`, `triage-v1` / `kw-r1`. Its retrieved context held
exclusion rows E-32, E-33, E-35 and E-37 of HO-0412's table and **not E-34 / E-36**, the two that describe the claim
(shingles "dimpled and pitted", surface "intact", no leaks, replaced "because it looks bad from the street"). It was
answered `covered`, payout $4,000. The original un-restamped run is `req-7060c0c1d556` (`trace.json`).

Under the five-minute bar, so no missing field has to be named for Drill 1. The field that was *not* there and would
have made it instant is described under "What this does not show".

## How it was run, and what that is worth - read this before quoting the time

- **Not squadmate-timed.** The brief asks for the plant and the clock to come from a named squadmate. Both were done
  by the same agent (Claude) that wrote the logging, using `tools/w11_drill.py`: `seed` plays the squadmate, `start`
  and `answer` are the clock. The 01:47 is the wall clock between those two commands and includes tool-call
  latency. It is **not** a figure from a human who did not write the code.
- **The plant is real, not typed.** `seed` takes one failing trace out of the RED suite (a real gpt-oss-20b run: real
  spans, tokens, context ids), re-stamps its id, time and user, and buries it among 154 other requests over four
  days and eight users (45% re-stamped real runs, 55% synthetic policy-question / claim-summary traffic, plus four
  cost spikes as distractors). Only a sha256 of the planted id is written to disk. The span latencies of the log copy
  carry a seeded 0.8-1.35x jitter, which is why `trace.json` uses the original run instead.
- **Blindness was partial.** I chose which claim to plant (`--plant-claim c11`), because the failure has to be one the
  suite can reproduce. I did not know the time, user or trace id and I did not read the sealed file.
- **The traffic is synthetic around the plant.** There is no production log. 155 requests is a fixture, not a
  measurement of volume.

To get the brief's number, have a squadmate run `python tools/w11_drill.py seed` without telling you
`--plant-claim`, and time `start` to `answer` themselves.

## Drill 2 (the bonus): did the field close the gap? Not demonstrated.

The bonus asks for a field that makes the find instant and a faster second time. What happened, in order:

1. **Field v1** `covered_without_exclusions_seen` (a `covered` answer whose context held no exclusion row at all).
   The second plant (`c07`, a real failing run) was **not flagged** - it had been shown four of ten rows. The field
   I built to close the gap had a false negative on the very next failure. The only hit was a legitimate `c10`.
2. **Field v2** `covered_with_unseen_exclusion_rows` (the governing form's table was not shown in full). It flags the
   second plant - and **all 12** `covered` answers from yesterday, because the unfiltered retriever never showed
   any `covered` answer a whole table. It has full recall and no precision: it did not narrow the list.
3. The second find took **00:10**, and that number is **invalid as a "beat my own time"**: I had printed the plant's
   context while debugging field v1, so I knew the answer before the clock restarted.

So the honest bonus result is: one field (`exclusion_rows_unseen`, flag `covered_with_unseen_exclusion_rows`) was
added and is in the log schema; it is a *recall* tool, not the instant-find the brief wants; and no valid second
time exists. Both drills' raw results: `drill_result_1_baseline.json` and `drill_result.json`.

## What this does not show

- The field that would have made the find instant is one that says an answer **contradicts the policy**, and no
  logged field can: that needs ground truth the production system does not have. The realistic version is a
  shadow check at write time that retrieves the whole exclusion schedule with the *semantic* retriever and flags
  `covered` answers where an unseen row ranks above the seen ones. Not built; untested guess.
- Output text search worked because this app's answer is one JSON object with a status field. A free-text answer
  ("this should be fine") would not have been found by `coverage_status` and would need the text indexed too.
