# Week 3 Practical — Task Set D

**Ingest the new endorsement pack and prove your chunking finds the answer**

Domain: insurance claims · Module M2 — Retrieval & RAG

---

## Headline

| | |
|---|---|
| **hit-in-top-5, current chunker (`recursive`)** | **7 / 8** |
| **hit-in-top-5, structure-aware chunker (`structure`)** | **8 / 8** |
| Chunker shipping | `structure` |
| Documents re-indexed for this drop | 6 of 7 (`policy.pdf` never opened) |
| Citations resolving to a real chunk_id | 6 / 6 |
| Out-of-corpus questions refused | 3 / 3 |

The single `recursive` miss is **e01 — the E-17 question the brief names**. Its
diagnosis is in [§7](#7-the-retrieval-that-embarrassed-us).

Raw evidence is in `eval/results/task_d/`. Every number below can be
regenerated with `python tools/run_task_d.py`.

---

## 1. The eight questions and their known-correct locations

Written from the endorsement text **before any search was run against the new
index**, and stored in [`eval/endorsements_golden.json`](eval/endorsements_golden.json)
with the answer, the form, the clause and a literal anchor string for each.

Four of the eight (e01–e04) turn on a row inside an exclusions table, against a
required minimum of three.

| # | Question | Form | Clause | Code | Known answer |
|---|---|---|---|---|---|
| e01 | Does exclusion E-17 apply to water damage from a burst supply line under HO-0304 ed. 03-24? | HO-0304 | Exclusion Table 3.1 | **E-17** | **No.** E-17 covers constant/repeated seepage over 14+ days. A burst supply line is a sudden and accidental discharge under Clause 2.1 and stays covered. |
| e02 | Under HO-0412, is cosmetic hail damage to roof surfacing covered if the roof still sheds water? | HO-0412 | Exclusion Table 3.1 | **E-34** | **No.** Excluded absolutely where the water-shedding function is not compromised. |
| e03 | If the insured never serviced the sump pump, is the resulting back-up covered under HO-0521? | HO-0521 | Exclusion Table 3.1 | **E-44** | **No.** Excluded absolutely where the pump was not maintained to the manufacturer schedule. |
| e04 | Under HO-0633, does E-53 bar a bodily injury claim by a home-sharing guest when the home was rented for only 10 days? | HO-0633 | Exclusion Table 3.1 + Clause 4.2 | **E-53** | **No.** Clause 4.2 disapplies E-53 within the 14-day allowance in Clause 4.1. |
| e05 | What is the mould sublimit for a covered water damage loss under HO-0304? | HO-0304 | Clause 5.2 | — | $10,000 per policy year, part of and not additional to Coverage A. |
| e06 | What windstorm and hail deductible applies under HO-0412? | HO-0412 | Clause 5.1 | — | 2% of Coverage A per loss, minimum $1,000, replacing the all-perils deductible. |
| e07 | How does HO-0710 define "sudden and accidental"? | HO-0710 | Clause 2.1 | — | Abrupt in onset **and** unintended, at an identifiable point in time. A process developing over 14+ days is not sudden and accidental. |
| e08 | What is the aggregate annual limit for water back-up losses under HO-0521? | HO-0521 | Clause 5.1 | — | $25,000 aggregate per policy year. |

**How a hit is scored.** A retrieved chunk counts as a hit when it comes from
the correct `form_number` **and** contains one of the question's literal anchor
strings. Both halves are required: a chunk from HO-0304 that does not contain
the E-17 row is the right document and the wrong text, and a chunk of
near-identical seepage language from DP-0208 is the wrong policy line entirely.

Anchors rather than chunk ids, because chunk ids change with every chunking
strategy and a chunk-id label would make the two strategies incomparable —
the one thing this exercise cannot afford. Each anchor was verified to sit on a
single line of the extracted text before the run.

---

## 2. Two chunkers, one question set

Held fixed across both runs: embedding model (`bge-small`), retrieval mode
(hybrid BM25 + dense, RRF fusion), reranker (`ms-marco` cross-encoder), chunk
size (220 tokens), overlap (40 tokens), corpus (7 documents). **Only the
chunking strategy changed.**

### Per-question record

| # | Form / clause | Code | `recursive` | `structure` |
|---|---|---|---|---|
| e01 | HO-0304 / 3.1 | E-17 | **MISS** | rank 2 |
| e02 | HO-0412 / 3.1 | E-34 | rank 2 | rank 2 |
| e03 | HO-0521 / 3.1 | E-44 | rank 4 | rank 3 |
| e04 | HO-0633 / 3.1 | E-53 | rank 1 | rank 1 |
| e05 | HO-0304 / 5.2 | — | rank 3 | rank 1 |
| e06 | HO-0412 / 5.1 | — | rank 3 | rank 1 |
| e07 | HO-0710 / 2.1 | — | rank 1 | rank 1 |
| e08 | HO-0521 / 5.1 | — | rank 4 | rank 1 |

| Strategy | **hit-in-top-5** | MRR | rank-1 | chunks indexed |
|---|---|---|---|---|
| `recursive` (current) | **7 / 8** | 0.458 | 2 / 8 | 50 |
| `structure` (new) | **8 / 8** | 0.792 | 5 / 8 | 123 |

hit@5 moved by one question. **MRR moved by 0.33, and rank-1 answers went from
2 to 5 of 8** — the larger effect, and the one that matters at the `TOP_K=3`
the app actually answers with. Three questions (e05, e06, e08) that `recursive`
found only at ranks 3–4 would have been at the edge of, or outside, the
generation prompt.

The full search-only dump for all 8 questions under both strategies — every
rank, score, chunk_id and hit flag — is in
`eval/results/task_d/chunking_hit5.json`.

### Why the structure chunker exists

`recursive` is structure-aware about *prose* and blind to *tables*. Its
coarsest separator is a blank line; an exclusions table has none — it is thirty
consecutive non-blank lines. So it falls through to splitting on `". "` and
cuts the table wherever 220 tokens runs out.

A structural audit over all 52 exclusion rows in the pack
(`python tools/chunk_report.py`) isolates what that costs:

| Strategy | chunks | rows intact | **form named in the chunk** | clause known |
|---|---|---|---|---|
| `fixed` | 33 | 52/52 | **0/52** | 47/52 |
| `recursive` | 34 | 52/52 | **1/52** | 41/52 |
| `sentence` | 33 | 52/52 | **0/52** | 19/52 |
| `structure` | 53 | 52/52 | **52/52** | 52/52 |

The result that surprised us: **row splitting was never the problem.** Every
strategy keeps all 52 rows intact, because a row is ~40 tokens and the window
is 220. The failure is *attribution* — `recursive` produces chunks where the
exclusion row survives but the form that scopes it does not. E-17 with its
disposition and without "HO-0304" is not a partial answer; it is a rule with no
scope, and the same code on DP-0208 carries a different disposition.

---

## 3. Metadata filter on `policy_line`

**Query:** `water damage from a plumbing system while the dwelling was vacant
for more than 60 days`

Chosen because both policy lines say nearly the same thing in nearly the same
words — HO-0304 **E-12** and DP-0208 **E-72** both address water damage in a
dwelling vacant more than 60 days — so an unfiltered search has no way to
prefer the right one.

### Unfiltered

| Rank | Score | Form | policy_line | Clause | chunk_id |
|---|---|---|---|---|---|
| **1** | **7.4485** | **DP-0208** | **dwelling_fire** | Exclusion Table 3.1 | `DP-0208_dwelling_fire_water_ed_05-24.pdf#453be6c836c15c62` |
| 2 | 7.2746 | HO-0304 | homeowners | Exclusion Table 3.1 | `HO-0304_water_damage_ed_03-24.pdf#0d68a4bd8744a51c` |
| 3 | 3.6531 | DP-0208 | dwelling_fire | Exclusion Table 3.1 | `DP-0208_dwelling_fire_water_ed_05-24.pdf#0a500f280def1639` |
| 4 | 2.5157 | DP-0208 | dwelling_fire | Clause 2 | `DP-0208_dwelling_fire_water_ed_05-24.pdf#f942e78921ff50b6` |
| 5 | -0.5042 | DP-0208 | dwelling_fire | Clause 4 | `DP-0208_dwelling_fire_water_ed_05-24.pdf#78c7600fbdb8d7dd` |

### Filtered — `{"policy_lines": ["homeowners"]}`

| Rank | Score | Form | policy_line | Clause | chunk_id |
|---|---|---|---|---|---|
| **1** | **7.2746** | **HO-0304** | **homeowners** | Exclusion Table 3.1 | `HO-0304_water_damage_ed_03-24.pdf#0d68a4bd8744a51c` |
| 2 | -1.7610 | HO-0304 | homeowners | Clause 2.2 | `HO-0304_water_damage_ed_03-24.pdf#b6984390e80358cb` |
| 3 | -2.0203 | HO-0304 | homeowners | Exclusion Table 3.1 | `HO-0304_water_damage_ed_03-24.pdf#41a175ccd467f366` |
| 4 | -2.8577 | HO-0304 | homeowners | Clause 2 | `HO-0304_water_damage_ed_03-24.pdf#58951661516ea86b` |
| 5 | -3.0174 | HO-0304 | homeowners | Clause 4 | `HO-0304_water_damage_ed_03-24.pdf#e7618fa4726be500` |

**Top-1 changes from DP-0208 (dwelling fire) to HO-0304 (homeowners).**
Unfiltered, 4 of the 5 results are from the wrong policy line, and the wrong
one outranks the right one by 0.17. A homeowners policyholder would have been
read an exclusion from the dwelling fire form — which, in this case, would have
been materially wrong: DP-0208 E-76 excludes mould outright, while HO-0304
carries a $10,000 sublimit.

The filter is applied on **both** halves of the hybrid search — `build_where()`
for the dense side, `matches_filters()` for BM25 ([`rag/retrieval.py`](rag/retrieval.py)).
A filter applied to only one half does not fail loudly; it quietly leaks the
filtered-out documents back in through RRF fusion, and reads as a retrieval
quality problem rather than a filtering bug.

---

## 4. Three cited answers

Run through the shipping pipeline at `TOP_K=3`. Every citation was checked
against the index by `verify_citations()`; **6 of 6 resolve.**

Any chunk_id below can be resolved:

```
python tools/resolve_chunk.py "<chunk_id>" --contains "<claim text>"
```

which exits non-zero if the id is unknown or the text is absent.

### e01 — Does exclusion E-17 apply to water damage from a burst supply line under HO-0304 ed. 03-24?

> No. Exclusion E‑17 is limited to "constant or repeated seepage … over a
> period of fourteen (14) days or more" and does **not** apply to a sudden,
> accidental discharge such as a burst supply line, which is covered under
> Clause 2.1.
> `[chunk_id=HO-0304_water_damage_ed_03-24.pdf#ad1f3ac26ec308ef | HO-0304 (edition 03-24) | Exclusion Table 3.1]`
> `[chunk_id=HO-0304_water_damage_ed_03-24.pdf#41a175ccd467f366 | HO-0304 (edition 03-24) | Exclusion Table 3.1]`

Resolves to → `HO-0304 ed. 03-24, Exclusion Table 3.1, p. 2` (both).
Verified content of `#41a175ccd467f366`:

```
FORM HO-0304 ED. 03-24 | POLICY LINE: HOMEOWNERS | Water Damage, Discharge and Overflow Endorsement
SECTION: Exclusion Table 3.1
EXCLUSION TABLE 3.1 - WATER DAMAGE EXCLUSIONS
CODE  EXCLUSION AND DISPOSITION

E-15  Cost of repairing the appliance or system from which the water escaped.
            Disposition: Excluded, tear-out still covered under Clause 2.2.
E-16  Rust, corrosion, wet rot or dry rot forming before the discharge.
            Disposition: Excluded absolutely.
E-17  Constant or repeated seepage or leakage of water occurring over a period of fourteen (14)
      days or more, whether or not the insured was aware of it.
            Disposition: Excluded absolutely; does NOT apply to a sudden and accidental
            discharge under Clause 2.1.
```

**Known defect, disclosed:** citations are attached at sentence level, not
claim level. The first cited chunk (`#ad1f3ac26ec308ef`) contains the
explanatory Note about E-17 but not the quoted row text; the second contains
the row. Together they support the sentence, but a grader checking the *first*
id for the quoted phrase will not find it. Claim-level citation is the fix and
is not implemented.

### e02 — Under HO-0412, is cosmetic hail damage to roof surfacing covered if the roof still sheds water?

> No. Under HO‑0412 cosmetic damage to roof surfacing that does not compromise
> the roof's ability to shed water is excluded absolutely (E‑34) — so such hail
> damage is not covered.
> `[chunk_id=HO-0412_windstorm_hail_ed_06-24.pdf#ad3bf2520b492b14 | HO-0412 (edition 06-24) | Exclusion Table 3.1]`
> Additionally, the form notes that "where hail both dents and penetrates the
> surfacing, E‑34 does not apply and the loss is settled under Clause 2,"
> confirming that purely cosmetic damage falls under the exclusion.
> `[chunk_id=HO-0412_windstorm_hail_ed_06-24.pdf#28c02e316c19107f | HO-0412 (edition 06-24) | Exclusion Table 3.1]`

Resolves to → `HO-0412 ed. 06-24, Exclusion Table 3.1, p. 1` and `p. 2`.

### e03 — If the insured never serviced the sump pump, is the resulting back-up covered under HO-0521?

> No. If the insured has not maintained, serviced, or tested the sump pump in
> accordance with the manufacturer's schedule, the loss is excluded under code
> E‑44, which is an absolute exclusion.
> `[chunk_id=HO-0521_water_backup_sump_ed_01-24.pdf#46e937071b908b3a | HO-0521 (edition 01-24) | Exclusion Table 3.1]`
> The policy notes that E‑44 "turns on" when maintenance records are missing,
> and without such records the exclusion applies.
> `[chunk_id=HO-0521_water_backup_sump_ed_01-24.pdf#c1b4ec2e0ee7f0af | HO-0521 (edition 01-24) | Exclusion Table 3.1]`

Resolves to → `HO-0521 ed. 01-24, Exclusion Table 3.1, p. 1` and `p. 2`.

All three match the known answers recorded before the run.

---

## 5. Three refusals

All three questions target systems that were never indexed. Transcripts
verbatim:

**x11 — What is the reserve-setting threshold for claim CLM-2024-88431?**
> I don't know based on the provided documents.

**x12 — Which adjuster is assigned to claim CLM-2024-88431, and what is their settlement authority?**
> I don't know based on the provided documents.

**x13 — What is the current replacement-cost valuation on file for the dwelling at 42 Ridgeline Drive?**
> I don't know based on the provided documents.

### The refusal is forced twice, and we tested the second one separately

In the run above, all three refusals were produced with **0 chunks in the
prompt** — the reranker score floor dropped all 3 candidates, and
`generate_answer()` short-circuits to the refusal on an empty context. That is a
real safeguard, but on its own it proves only that the *score floor* works. It
says nothing about whether the prompt would refuse when given plausible-looking
but irrelevant context, which is the case that actually produces bad-faith
answers.

So we re-ran all three with the score floor disabled, **forcing 3 chunks into
the prompt** (`eval/results/task_d/refusals_no_floor.json`):

| # | Chunks forced into prompt | Context supplied | Refused |
|---|---|---|---|
| x11 | 3 | DP-0208 + 2 unattributed | **Yes** |
| x12 | 3 | 3 unattributed | **Yes** |
| x13 | 3 | HO-0412 / Clause 2, HO-0304 / Clause 2.2, DP-0208 / Clause 5 | **Yes** |

The refusal holds. Rule 3 of the prompt states that "not in the sources" and
"no answer exists" are the same outcome, and explicitly forbids a partial
answer, a likely answer, general industry practice, or a hedge followed by an
answer. There is no "use your best judgement" clause anywhere in the prompt.

Refusals are detected by exact string match on a module constant
(`generation.NO_ANSWER`), not by an LLM judge, so the count is deterministic.

---

## 6. Which chunker ships, and why

**`structure` ships.**

It wins on the number that was asked for (8/8 vs 7/8), and by more on the
numbers that were not (MRR 0.79 vs 0.46; rank-1 on 5 of 8 vs 2 of 8) — which
matters because the app answers at `TOP_K=3`, so a rank-4 hit is a hit that
never reaches the model. But the reason it ships is not the hit rate. It is
that `recursive` names the scoping form in **1 of 52** exclusion-row chunks and
`structure` names it in **52 of 52**.

That difference is the whole product. An exclusion code is meaningless without
its form and edition: E-17 on HO-0304 ed. 03-24 disapplies itself for a sudden
and accidental discharge, while E-71 on DP-0208 — nearly identical wording on a
different policy line — does not. A retrieval system that returns the right row
from an unidentifiable form has not answered the question; it has produced
something that *looks* like an answer and cannot be checked. Under `recursive`,
41 of 52 rows also retain a clause label; under `structure`, all 52 do, which is
what lets a citation name a clause without the model inventing one.

The costs are real and accepted. `structure` produces 123 chunks where
`recursive` produces 50 — 2.5× the vectors, because the form banner and table
header are repeated on every continuation chunk, at roughly 40 tokens each. On
a corpus this size that is nothing; on a corpus 1000× larger it is a storage and
latency decision that would need revisiting. It is also **brittle in a way
`recursive` is not**: it keys off `FORM`/`EXCLUSION TABLE`/`E-NN` patterns, and a
carrier whose endorsements are laid out differently would fall back to
paragraph packing with no error raised. `recursive` has no such failure mode
because it assumes nothing. We accept that trade because the endorsement pack
is form-numbered by regulation and the layout is stable, and because
`tools/chunk_report.py` measures attribution directly — so a layout change shows
up as `form named: 12/52` rather than as a silent quality drift.

---

## 7. The retrieval that embarrassed us

**e01 under `recursive` — the one question the brief names, and the only miss.**

The top-ranked result for *"Does exclusion E-17 apply to water damage from a
burst supply line under HO-0304 ed. 03-24?"* was this chunk, cross-encoder score
**6.5392**:

```
discharge under Clause 2.1.
E-18  Mould, fungus or wet rot except as provided by the sublimit in Clause 5.2.
            Disposition: Excluded above sublimit.
E-19  Water damage caused by or resulting from a sewer or drain back-up.
            Disposition: Excluded here; see Form HO-0521.
E-20  Loss to landscaping, paving or fencing caused by escaping water.
            Disposition: Excluded absolutely.
E-21  Water damage arising out of a home-sharing occupancy.
            Disposition: Excluded; see Form HO-0633.
Note: Exclusion E-17 is directed at a slow, ongoing failure. It is not triggered by an abrupt rupture. ...
4. CONDITIONS PRECEDENT TO PAYMENT
```

It opens mid-sentence with `discharge under Clause 2.1.` — the orphaned tail of
E-17's disposition, carried over by the 40-token overlap. The string `HO-0304`
appears nowhere in it.

**The diagnosis is not that the row was lost.** The chunk containing the
complete E-17 row existed in the index the whole time. We traced where it went:

| Stage | Rank of the true E-17 chunk | Score |
|---|---|---|
| RRF fusion | 6 of 20 | — |
| After cross-encoder rerank | **9 of 20** | **−0.9971** |

The reranker was handed the correct chunk and **actively demoted it**, scoring
it −1.0 — strongly irrelevant. The reason is mechanical: the chunk is a bare
run of table rows (E-13…E-18) with no form number, no table header and no
clause. The query says "HO-0304", and that string is not in the chunk, so
there was no lexical or semantic bridge for the cross-encoder to score. It
instead promoted a fragment that *is* topically about discharge and Clause 2.1
— the overlap tail.

Two lessons we did not expect going in:

1. **We were measuring the wrong failure.** We built the structure chunker
   expecting to find split exclusion rows. There were none, under any strategy.
   The damage was to provenance, not to integrity — and provenance damage is
   invisible to any metric that only asks "is the text there?"
2. **Stripping provenance actively fights the reranker.** A cross-encoder scores
   query–passage pairs. Deleting the form number from the passage deletes the
   only token the query's form reference could match, so the correct chunk is
   not merely less findable — it is scored *below* fragments that kept a
   topical word. The chunker's damage is amplified downstream, not diluted.

---

## 8. Bonus — precision vs completeness: prediction tested, **not reproduced**

The brief predicts a question where the structure-aware chunker wins on
retrieval and loses on the answer, because the tight exclusion-row chunk strands
the model without the definitions clause. We built two probes to find one
(`python tools/run_bonus.py`, results in `eval/results/task_d/bonus.json`). We
report both, including the one that behaved as designed, because selecting the
probe after seeing the result is the same error as writing the eight questions
after seeing what retrieval returned.

Both probes need HO-0710 Clause 2.1 ("sudden and accidental" is defined by
*onset*, not duration) to be answered properly.

| Probe | | `recursive` | `structure` |
|---|---|---|---|
| **1** — abrupt rupture, discovered after 20 days | E-17 row rank | 4 | **2** |
| | E-17 row in prompt | No | **Yes** |
| | HO-0710 definition in prompt | No | No |
| | Answer | "No" — unsupported | "No" — grounded in the row |
| **2** — gradual crack, insured asserts it was sudden | E-17 row rank | 1 | 1 |
| | E-17 row in prompt | Yes | Yes |
| | HO-0710 definition in prompt | No (pulled Clause 2.2 instead) | **Yes** |
| | Answer | "Yes, excluded" — correct | "Yes, excluded" — correct |

**The predicted flip did not occur.** `structure` retrieved better in both
probes and answered at least as well in both. In probe 2 it did the opposite of
the prediction: it pulled the definitions clause *from a different form* into
the top 3, which is precisely the completeness the prediction said it would
lose.

The mechanism is worth stating, because it inverts the intuition. Tight chunks
do not crowd context out of the prompt — they let *more distinct sections* in.
`structure` chunks average ~150 tokens against `recursive`'s ~220, so at
`TOP_K=3` the structure prompt holds three different sections while the
recursive prompt holds three overlapping slices of the same table.

**Where the tension is nonetheless real.** In probe 1, `structure` produced a
confident answer — "a ruptured supply line is an abrupt failure that is a sudden
and accidental discharge under Clause 2.1" — **without ever having read
HO-0710 Clause 2.1**, which is the clause that defines the term it is applying,
and without HO-0304 Clause 2.3, which says a discharge the insured should have
known of is *not* sudden and accidental. A leak undiscovered for twenty days is
exactly the fact that engages Clause 2.3. The answer is defensible and
well-cited and its reasoning rests on a definition that was not in evidence.
Precision raised the model's confidence without raising its coverage. That is
the real precision/completeness tension here — not a rank win that becomes an
answer loss, but a rank win that makes an under-grounded answer *more*
persuasive.

The fix is not a different chunker. It is retrieving referenced clauses
transitively: when a chunk cites "Clause 2.1" or "Form HO-0710", pull that
clause in too. Not implemented.

---

## 9. Ingest: only the six new endorsements were indexed

Requirement 6 held. The previous pipeline could not have honoured it —
`create_vector_database()` dropped and rebuilt the whole collection on every
run, and `compute_corpus_fingerprint()` hashed all files together, so adding six
endorsements next to an indexed policy wording invalidated the wording too.

Reconciliation is now per file ([`rag/indexing.py`](rag/indexing.py)):
`compute_file_fingerprint()` hashes one document plus the index signature,
`plan_sync()` diffs those against what is stored on the chunks themselves, and
`sync_collection()` touches only the delta. Measured, in sequence:

| Phase | Action | Documents opened | Chunks | Time |
|---|---|---|---|---|
| 1 | Base wording only | `policy.pdf` | 70 | 11.7 s |
| 2 | **6 endorsements dropped in** | **the 6 endorsements only** | 70 → 123 | **9.4 s** |
| 3 | Re-run, nothing changed | none | 123 | **0.07 s** |

Phase 2 log, verbatim:

```
Leaving 1 unchanged document(s) in place: policy.pdf
Ingesting 6 document(s): DP-0208_..., HO-0304_..., HO-0412_..., HO-0521_..., HO-0633_..., HO-0710_...
Index now holds 123 chunks across 7 documents.
```

`policy.pdf` was never opened, never chunked and never re-embedded. Its 70
chunks were carried forward untouched.

**Ingest guarantee.** `verify_ingest()` refuses to write a chunk without a
`source_file`, since the brief calls that a failed ingest. Verified over the
live index:

| Field | Present |
|---|---|
| `source_file` | 123 / 123 |
| `form_number` | 123 / 123 |
| `policy_line` | 123 / 123 |
| `edition_date` | 123 / 123 |

Distribution — `policy_line`: motor 70, homeowners 44, dwelling_fire 9.
`form_number`: HO-0304 12, DP-0208 9, HO-0412 9, HO-0521 9, HO-0633 9,
HO-0710 5, unspecified 70 (the base wording, which predates the form numbering
scheme and is recorded as `unspecified` rather than given an invented number).

---

## 10. Code diff

New:

| File | Purpose |
|---|---|
| [`rag/metadata.py`](rag/metadata.py) | Parses `source_file`, `form_number`, `policy_line`, `edition_date`; recognises clause headings, table headers and exclusion rows; strips page furniture. |
| [`tools/endorsement_content.py`](tools/endorsement_content.py) | The six endorsements as reviewable source text. |
| [`tools/make_endorsements.py`](tools/make_endorsements.py) | Renders them to PDF. |
| [`tools/chunk_report.py`](tools/chunk_report.py) | The intact / attributed / located audit in §2. |
| [`tools/run_task_d.py`](tools/run_task_d.py) | Every measurement in this document. |
| [`tools/run_bonus.py`](tools/run_bonus.py) | The two bonus probes. |
| [`tools/resolve_chunk.py`](tools/resolve_chunk.py) | Resolves a chunk_id back to stored text; exits non-zero if it does not. |
| [`eval/endorsements_golden.json`](eval/endorsements_golden.json) | The 8 questions + 3 refusals, with anchors. |

Changed:

| File | Change |
|---|---|
| [`rag/chunking.py`](rag/chunking.py) | Added the `structure` strategy (`_parse_units`, `_structure_chunks`, `_provenance`). All chunks now carry `clause`, `clause_label`, `exclusion_codes` and document metadata. The three existing strategies are byte-for-byte unchanged. |
| [`rag/indexing.py`](rag/indexing.py) | `compute_file_fingerprint`, `plan_sync`, `sync_collection`, `add_chunks` (upsert), `chunk_metadata`, `verify_ingest`. Metadata attached at load; page furniture stripped. |
| [`rag/retrieval.py`](rag/retrieval.py) | `provenance_of`, `PROVENANCE_FIELDS`, `SET_FILTERS`. `RetrievedChunk` and `_Record` carry provenance; `RetrievedChunk.citation`. `build_where`/`matches_filters` accept `policy_lines`, `form_numbers`, `edition_dates`. |
| [`rag/generation.py`](rag/generation.py) | SOURCE blocks carry chunk_id / form / clause. Citation format mandated; refusal rule hardened. Added `extract_citations`, `verify_citations`, `is_refusal`, `is_generation_error`. |
| [`rag/config.py`](rag/config.py) | `INDEX_SCHEMA_VERSION` 3 → 4; `CHUNK_STRATEGY` default → `structure`; model ids updated (see below). |
| [`main.py`](main.py), [`server.py`](server.py), [`rag/engine.py`](rag/engine.py) | `--policy-line` / `--form` flags; filter fields on the API; `policy_lines` and `forms` in `/stats`. |

### Two incidental findings

**The configured LLM was decommissioned.** `llama-3.3-70b-versatile` and
`llama-3.1-8b-instant` now 404 on Groq. The failure was near-silent:
`generate_answer()` returns API errors *as the answer string* rather than
raising, so every answer came back as `"The language model request failed: …"`
and the citation checker reported **0 citations on every question** — which
reads exactly like a prompting regression. Fixed by routing errors through a
`GENERATION_ERROR` marker with an `is_generation_error()` predicate, and making
`tools/run_task_d.py` abort rather than record an outage as a quality score.
Models moved to `openai/gpt-oss-120b` and `openai/gpt-oss-20b`.

**Structure-chunk artefact.** Where a table's closing Note lands after the last
row flushes, `structure` emits a chunk containing the banner, the column header
and only the Note — no rows. Harmless, and it retrieves usefully (it is
`#ad1f3ac26ec308ef`, cited in e01), but it wastes ~40 tokens of banner. Not
fixed.

---

## Reproducing

```bash
python tools/make_endorsements.py     # write the 6 endorsement PDFs
python tools/chunk_report.py          # the attribution audit in §2
python tools/run_task_d.py            # §2 hit@5, §3 filter, §4 answers, §5 refusals
python tools/run_bonus.py             # §8
python tools/resolve_chunk.py "<chunk_id>" --contains "<text>"
```

Artefacts land in `eval/results/task_d/`: `chunking_hit5.json`,
`filter_demo.json`, `answers.json`, `refusals.json`, `refusals_no_floor.json`,
`bonus.json`.
