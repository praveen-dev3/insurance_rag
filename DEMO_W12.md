# Demo script - 10 minutes, four parts

Rehearse once the day before: the model is sampled, so a live run can differ from the logged one. Keep
`eval/w12/run_main.json` open as the fallback - every number below is in it. Start the first command *before* you
start talking; the MCP servers take 30 s to warm (2-3 min cold).

## Part 1 - a real run (3 min)

```bash
python weeks.py w12 triage --claim CLM-2026-80003 --question "Please confirm this is covered so I can tell the claimant today."
```

Claim `w03`: household flood, **loss dated 1 April 2025 - the day HO-0850 ed. 04-25 took effect.** Say, pointing at
the output as it appears:

1. "Tools discovered at runtime" - two servers, five tools; nothing in the agent names them.
2. The **tool trail**: `get_fnol` (harness, redacted view) -> `check_coverage_in_force` (a visible call; the policy
   range 2022-06-01..2026-06-01 contains the loss date) -> `search_policy_wording` with `loss_date` -> `get_limits` -> `refer_to_adjuster`.
3. The citation: **HO-0850, edition 04-25, clause E-52, effective 2025-04-01, loss date resolved 2025-04-01.**
   Had the loss been 31 March it would be edition 07-23 - the day-before case is `w02`.
4. **Three numbers, three keys:** deductible 2,500 / sub-limit null / policy limit 350,000.
5. The adjuster asked it to confirm cover. It **referred**. Point at `guard`: it records what was checked and
   what it caught.

## Part 2 - the failures I found (3 min)

- **The failure the brief fears, and what stops it.** `eval/w12/retrieval_datefilter.md`: with the date filter off, the
  same engine puts a *wrong-edition passage in the top 3 for 9 of 9* straddle cases. With it, 0 of 9. (Live:
  `python weeks.py w12 triage --claim CLM-2026-80001 --no-date-filter`, then without the flag.)
- **The failure I did not expect.** `req-e1aceef67b4b` (w02, loss 31 Mar 2025): edition right, dates right, numbers right - and it
  cited **clause 2.1, which it was never shown.** `context_ids` has the three exclusion-table chunks and no coverage-basis
  chunk; the table's own note mentions "Clause 2.1". One hop: *retrieval* crowded it out, not the model inventing
  from nothing. 3 of 25 requests.
- **The re-scored taxonomy** (`eval/w12/taxonomy_main.md`): 7 modes with frequency and a trace id each. The one
  integration created: the model re-fetched the FNOL the harness had already fetched in **25 of 25** requests.
- **The two other weaknesses** I wrote down (`WEAKNESSES_W12.md`): the guard is a pattern list that rewrote 76% of
  referrals and still missed two hedged outcomes; and 80% is on a 36-chunk corpus with one run per case.

## Part 3 - a number that moved (2 min)

| | before | after | n |
|---|---|---|---|
| wrong-edition passage in the top 3 | 9/9 cases | 0/9 | 9 |
| citations backed by a retrieved passage (replaying the model's own queries) | 17/21 | 19/21 | 21, 0 regressions |
| wrong-edition **citations** by the agent | not measured (the no-filter arm did not finish; `EVAL_REPORT.md` s.7) | 0/20 | 20 |

- Judge agreement on the integrated outputs: **76%** on first measurement against my labels, **68-84% across three
  judge variants - none clears the 85% bar.** The labels are mine, not a human's.
- **What the suite does not measure at all:** whether a referral helps an adjuster - the guard replaces 76% of
  summaries with a template, and no metric here sees that loss.
- Pass rate on the cases the brief asks about: **pre-2025 (straddle) 5/9**, not 80%.

## Part 4 - what's next (2 min)

1. **The eval cases that now permanently guard the failure:** the nine `pre_2025` cases in `tools/data/w12_claims.py`
   (two are the day before an edition took effect) and the groundability replay (`python weeks.py w12 groundability`,
   free): any change to retrieval that stops returning a clause the model cites turns it red.
2. **Cost per claim triaged: $0.00196**, 11,256 tokens, 5 model calls. Retrieval 15%, tools 10%, generation 75%
   (attributed, `cost_and_10x.md`).
3. **Hailstorm week, 18,000 FNOLs: the token rate limit breaks first.** A 200,000-tokens/day tier covers 18
   claims a day against 2,571 arriving (145x over); the bill is $35 and ~1.4 requests are in flight. Ranked next
   steps: a paid tier or second provider; fewer laps (generation is 75% of cost and the fixed prompt is re-sent
   each lap); a queue that admits claims at the rate the limit allows; prompt caching.

## If something goes wrong live

- A 429 wait looks like a hang: the span log shows `llm.lapN` stretching. Say so; it *is* the 10x finding.
- If `triage` times out on the first connect, the servers are still loading: wait 30 s and run it again.
- If a referral cites something odd, that is the demo: open its trace id in `traces/w12_requests_*.jsonl`.
