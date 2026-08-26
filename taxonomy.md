# Claims assistant — failure taxonomy

**Sample:** 20 traces drawn with `random.Random(20260826).sample(sorted(trace_ids), 20)`
from the 70 random-population traces in `traces/claims_traces.jsonl`.
The 12 traces tagged `demo` were excluded from the frame.
**Read on:** 2026-08-26. **App at:** commit `582b225`, unchanged throughout.

| Mode | Count | % of 20 | Severity | Example trace_id |
|---|---:|---:|---|---|
| Answers without the clause that decides the claim | 4 | 20.0% | wrongly denies or wrongly pays a claim | `tr-wk5-0012` |
| Coverage position field contradicts its own narrative | 4 | 20.0% | wrongly denies a claim | `tr-wk5-0014` |
| Comes back with the wrong product's wording, or nothing, and declines | 3 | 15.0% | annoys the adjuster | `tr-wk5-0020` |
| Reports no deductible or excess figure | 2 | 10.0% | annoys the adjuster | `tr-wk5-0003` |
| Quotes a clause under the wrong number, or cites without naming the form | 2 | 10.0% | annoys the adjuster | `tr-wk5-0005` |
| *No failure observed* | 5 | 25.0% | — | `tr-wk5-0026` |

Rows sum to 20 of 20.

---

## What each mode means

**Answers without the clause that decides the claim.** The exclusion row,
coverage grant or condition that actually settles the question was not among
the three chunks that reached the prompt. Three times the app noticed and
declined; once it did not notice. In `tr-wk5-0012` a pipe froze while the
insured had the heating switched off entirely — E-14 excludes exactly that —
and the app returned **COVERED**, because the exclusion-table chunk it was
given carried only E-15, E-16 and E-17. That single trace is the reason this
mode's severity is "wrongly pays".

**Coverage position field contradicts its own narrative.** The labelled field
says one thing and the prose beneath it says another. `tr-wk5-0014` sets
**DENIED** and then explains that the fence portion is covered; `tr-wk5-0010`
leaves the Deductible field UNKNOWN while quoting $5,000 two lines later. The
field is what a routing queue reads, so the field is what will be acted on.

**Comes back with the wrong product's wording, or nothing, and declines.**
For a homeowners basement claim with no form number on file, all three
retrieved chunks were FEMA NFIP flood-manual page ranges. For a homeowners
theft question, the one survivor was the motor wording. The app declined in
every case, which is the safe outcome and still leaves the adjuster with
nothing.

**Reports no deductible or excess figure.** The Deductible field reads
UNKNOWN, so the file cannot be routed on the amount.

**Quotes a clause under the wrong number, or cites without naming the form.**
`tr-wk5-0005` welds a records condition from Clause 4 onto E-44, whose own
disposition is "Excluded absolutely" — turning an absolute exclusion into a
conditional one. `tr-wk5-0039` emits a citation whose form-number slot holds
"5.1" instead of HO-0633.

---

## The number the table hides

Each trace above carries its **single most consequential** defect, so a defect
that is present everywhere but never the worst thing is invisible in the counts.
One is:

> **The Deductible field read UNKNOWN in 10 of the 10 claim-summary traces in
> the sample — 100%, not the 10% the mode row shows.**

Eight of those ten are filed under a more serious mode. The mode row says 2
because only twice was it the worst thing in the trace.

The cause is visible in the traces and is not the model's: a claim summary
issues **one** retrieval over the whole notes with `top_k=3`, and on this
corpus all three slots are won by exclusion-table rows, which is what the notes
are mostly about. The deductible clause is never in the running. The proof is
`tr-wk5-0026`, where an adjuster asked about the HO-0304 deductible *directly*:
Clause 5.3 came back as the top chunk at rerank **8.3** and the answer was
"$2,500 per loss" with a citation that resolves. The clause is retrievable. The
summary task just never asks for it.
