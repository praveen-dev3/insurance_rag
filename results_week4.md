# Week 4 Practical — Task Set D

**Label the failures, then buy back hit-rate@3 with exactly one change**

Domain: insurance claims · Module M2 — Retrieval & RAG

---

## Headline

| | Before | After | Δ |
|---|---|---|---|
| **hit-rate@3** (same 12 questions) | **9 / 12** (0.750) | **11 / 12** (0.917) | **+2** |
| **p50 retrieval latency** | **32.7 ms** | **34.4 ms** | **+1.7 ms (+5%)** |
| R (retrieval) failures | 3 | 1 | −2 |
| G (generation) failures | 0 | 0 | 0 |
| Not-In-Corpus | 0 | 0 | 0 |

**The one change:** add BM25 alongside the dense retriever and fuse the two
rankings with Reciprocal Rank Fusion, k=60. Nothing else moved.

**Shipping decision: keep it.** Two questions bought back for 1.7 ms. Note
that hybrid+RRF was *already* the shipped default before this task — the
before/after was obtained by ablation, not by adding something new. See
[§10](#10-shipping-decision); it matters, and pretending otherwise would be
inventing work.

**The team lead's proposal — swap the model — would have fixed nothing.**
Zero of the twelve questions were generation failures. Detail in [§7](#7-the-model-swap-would-have-bought-nothing).

Raw evidence: `eval/results/week4/week4.json`. Reproduce with
`python tools/run_week4.py`.

---

## 1. What was held fixed

The brief's first listed mistake is changing two things and reporting one
delta. Everything below is pinned identically across both arms, and the
pinning is enforced in code (`common_options()` in
[tools/run_week4.py](tools/run_week4.py)), not by discipline:

| | Value | Why it is not a variable |
|---|---|---|
| Chunker | `structure` | Settled in Week 3. Pinning it is also what makes chunk-id ground truth stable. |
| Corpus | 7 documents in `eval/corpus/` | See [§9](#9-a-note-on-the-corpus). |
| Embedding model | `bge-small` | The other thing the brief warns against changing mid-experiment. |
| **Cross-encoder** | **OFF in both arms** | It is the *other* change the brief offers. Enabling it alongside fusion would make the delta unattributable. Measured separately in [§6](#6-the-other-change-measured-not-shipped). |
| MMR | OFF in both arms | It is the bonus. [§8](#8-bonus--mmr). |
| Reranker score floor | disabled in both arms | Not held constant — *removed*. A floor can drop a candidate in one arm and not the other, which would silently confound hit-rate@3 with a refusal mechanism. |
| k | 3 | |

The only difference between the two runs is `mode="dense"` versus
`mode="hybrid"`.

---

## 2. The 12-question golden set

[`eval/golden_set.jsonl`](eval/golden_set.jsonl) — one JSON object per line,
each carrying the chunk_id known to answer it.

**6 of 12 carry an exact token dense retrieval is structurally bad at** — an
exclusion code, a form number, or an edition — against a required minimum of
four. The 12 chunk_ids are distinct.

| # | Question | Exact token | Correct chunk_id | Form / clause |
|---|---|---|---|---|
| w01 | Does exclusion E-17 apply under form HO-0304 ed. 03-24 when a supply line bursts? | `E-17`, `HO-0304`, `ed. 03-24` | `HO-0304_water_damage_ed_03-24.pdf#41a175ccd467f366` | HO-0304 / Exclusion Table 3.1 |
| w02 | Insured is claiming hail dents that did not puncture the shingles. Does E-34 on HO-0412 knock it out? | `E-34`, `HO-0412` | `HO-0412_windstorm_hail_ed_06-24.pdf#ad3bf2520b492b14` | HO-0412 / Exclusion Table 3.1 |
| w03 | Sump pump had no service records at all. Which exclusion code on HO-0521 do I cite? | `HO-0521` | `HO-0521_water_backup_sump_ed_01-24.pdf#46e937071b908b3a` | HO-0521 / Exclusion Table 3.1 |
| w04 | Guest hurt during a short-let stay. Does E-53 bite if they only rented the place 10 days that year? | `E-53` | `HO-0633_home_sharing_business_ed_09-23.pdf#fcd483afbf55f3b3` | HO-0633 / Exclusion Table 3.1 |
| w05 | What does E-72 exclude on DP-0208 ed. 05-24? | `E-72`, `DP-0208`, `ed. 05-24` | `DP-0208_dwelling_fire_water_ed_05-24.pdf#453be6c836c15c62` | DP-0208 / Exclusion Table 3.1 |
| w06 | Under HO-0710 ed. 11-23, what counts as a supply line? | `HO-0710`, `ed. 11-23` | `HO-0710_definitions_general_conditions_ed_11-23.pdf#4a3af5524b7032d0` | HO-0710 / Clause 2 Definitions |
| w07 | Is water damage from a burst pipe covered on a homeowners policy? | — | `HO-0304_water_damage_ed_03-24.pdf#58951661516ea86b` | HO-0304 / Clause 2 |
| w08 | How much will we pay out for mould after a covered water loss? | — | `HO-0304_water_damage_ed_03-24.pdf#78a58d7c6b096028` | HO-0304 / Clause 5 |
| w09 | What deductible applies on a wind claim? | — | `HO-0412_windstorm_hail_ed_06-24.pdf#74bc08047bdcfa9a` | HO-0412 / Clause 5 |
| w10 | Roof is 18 years old. Do we settle replacement cost or actual cash value? | — | `HO-0412_windstorm_hail_ed_06-24.pdf#4dcd4c55d0c3a315` | HO-0412 / Clause 2 |
| w11 | Is there a cap on sewer backup claims per year? | — | `HO-0521_water_backup_sump_ed_01-24.pdf#bdf919e11b2faf1a` | HO-0521 / Clause 5 |
| w12 | If two endorsements both cover the same loss and they disagree, which one wins? | — | `HO-0710_definitions_general_conditions_ed_11-23.pdf#b8f81cecfb4488dd` | HO-0710 / Clause 3 |

**Chunk ids are resolved, not typed.** Each question is authored as a
(question, anchor) pair, where the anchor is a literal line of the
endorsement carrying the answer; [tools/build_w4_golden.py](tools/build_w4_golden.py)
then looks up which chunk contains it. A hand-copied chunk_id is a
transcription with no error detection — if it is wrong, hit-rate@3 is
measured against a chunk that does not answer the question and the whole
run is quietly meaningless. The resolver **fails loudly** if an anchor
matches anything other than exactly one chunk, and it did: the first run
aborted because `"2.1 We cover direct physical loss..."` appears verbatim in
both HO-0304 and DP-0208. Anchors are now scoped by form.

**Honest caveat on "REAL adjuster questions."** These are authored, not
harvested from a ticket queue — I do not have access to one. The mitigation
is the one that matters for the brief's warning: they were written to
include the exact-token lookups the system was *expected to fail*, not the
paraphrases it was expected to pass. Three of the six exact-token questions
did fail at baseline. A set written to flatter the retriever would not have
produced a 3-failure baseline.

---

## 3. Baseline: hit-rate@3 = 9/12, p50 = 32.7 ms

Dense vectors only, no BM25, no reranker. Written down before anything
changed.

| # | Exact token | hit@3 | Rank | Label |
|---|---|---|---|---|
| w01 | ● | ✗ | — | **R** |
| w02 | ● | ✓ | 2 | OK |
| w03 | ● | ✓ | 2 | OK |
| w04 | ● | ✗ | — | **R** |
| w05 | ● | ✗ | — | **R** |
| w06 | ● | ✓ | 2 | OK |
| w07 | | ✓ | 1 | OK |
| w08 | | ✓ | 1 | OK |
| w09 | | ✓ | 1 | OK |
| w10 | | ✓ | 1 | OK |
| w11 | | ✓ | 2 | OK |
| w12 | | ✓ | 1 | OK |

**9/12 = 0.750.**

The three failures are w01, w04, w05 — **all three carry an exact token, and
all six non-exact-token questions passed.** The failure is not spread evenly
across the set; it is concentrated entirely in the half of the set that dense
embeddings are structurally bad at. That is the tally doing its job before a
single line of retrieval code was touched.

---

## 4. The tally, with one line of evidence per failure

| Label | Count | Meaning |
|---|---|---|
| **R** — retrieval fetched bad context | **3** | w01, w04, w05 |
| **G** — model misused good context | **0** | — |
| **Not-In-Corpus** | **0** | by construction; see below |
| OK | 9 | |

Evidence lines, taken from the trace via
`classify_by_chunk_id()` in [rag/diagnostics.py](rag/diagnostics.py):

**w01 — R**
> Correct chunk absent from top-3; fusion had it at rank 4. Top-3 were
> [HO-0304/Exclusion Table 3.1, HO-0521/3. Exclusions Applicable To Back-Up
> And Overflow, HO-0521/Exclusion Table 3.1].

The query names `E-17` and `HO-0304 ed. 03-24`. Two of the three returned
chunks are from **HO-0521**, a different form entirely — semantically
adjacent water-exclusion prose, exactly the failure the problem statement
describes. The correct chunk was retrieved at rank 4, one place outside the
window.

**w04 — R**
> Correct chunk absent from top-3; fusion had it at rank 8. Top-3 were
> [HO-0633/4. Exceptions To The Exclusions, DP-0208/4. Conditions,
> HO-0633/Exclusion Table 3.1].

**w05 — R**
> Correct chunk absent from top-3; fusion had it at rank 5. Top-3 were
> [HO-0521/Exclusion Table 3.1, DP-0208/3. Exclusions Applicable To Water
> Damage, DP-0208/unspecified].

The query names `E-72` and `DP-0208`. The **top-1 result is from HO-0521** —
wrong form, wrong policy line.

**Why Not-In-Corpus is zero, and proof the label fires.** Requirement 1 asks
that all 12 questions carry a known-correct chunk_id, so every one of them is
answerable by construction and Not-In-Corpus is structurally unreachable in
this set. Reporting `0` without evidence would be indistinguishable from a
label that does not work, so the three out-of-corpus questions from Week 3
were run through the same classifier against the same index
(`eval/results/week4/not_in_corpus.json`):

| Question | Label | Evidence |
|---|---|---|
| Reserve-setting threshold for claim CLM-2024-88431 | **Not-In-Corpus** (correct_refusal) | Out of corpus; app refused. Top-3 were [DP-0208, HO-0521, HO-0304]. |
| Adjuster assigned to CLM-2024-88431 and their authority | **Not-In-Corpus** (correct_refusal) | Out of corpus; app refused. |
| Replacement-cost valuation for 42 Ridgeline Drive | **Not-In-Corpus** (correct_refusal) | Out of corpus; app refused. Top-3 were [HO-0304/Clause 2.2, DP-0208/Exclusion Table 3.1, DP-0208]. |

All three refused with plausible context in the prompt — the score floor was
disabled, so the LLM saw three chunks and declined anyway.

---

## 5. The one change, and the number

**Change: add BM25 and fuse with RRF (k=60).** Chosen from the tally, not
from a menu.

The tally says 3 R, 0 G. Every R failure is a query containing a literal
token — `E-17`, `E-53`, `E-72`, `HO-0304`, `DP-0208` — and a dense embedding
represents `E-17` as a point in a space where it sits close to `E-19` and
`E-71`, because they are lexically and distributionally near-identical. No
amount of reranking a dense candidate list fixes this: a cross-encoder can
only reorder what dense already retrieved, and in w05 the correct chunk was
at dense rank 5 out of a 20-candidate pool. BM25 scores a literal token match
directly, so `E-72` in the query matches `E-72` in the chunk and nothing else.
RRF fuses *ranks* rather than scores, which matters because BM25 scores and
cosine distances are not on the same scale and never were.

### Result

| # | Exact token | Before | After | Verdict |
|---|---|---|---|---|
| w01 | ● | ✗ | ✓ rank 2 | **FIXED** |
| w02 | ● | ✓ rank 2 | ✓ rank 2 | already passing |
| w03 | ● | ✓ rank 2 | ✓ rank 2 | already passing |
| w04 | ● | ✗ | ✗ | **STILL BROKEN** |
| w05 | ● | ✗ | ✓ rank 3 | **FIXED** |
| w06 | ● | ✓ rank 2 | ✓ rank 2 | already passing |
| w07 | | ✓ rank 1 | ✓ rank 1 | already passing |
| w08 | | ✓ rank 1 | ✓ rank 1 | already passing |
| w09 | | ✓ rank 1 | ✓ rank 1 | already passing |
| w10 | | ✓ rank 1 | ✓ rank 1 | already passing |
| w11 | | ✓ rank 2 | ✓ rank 3 | already passing |
| w12 | | ✓ rank 1 | ✓ rank 1 | already passing |

| | Before | After |
|---|---|---|
| hit-rate@3 | **9/12 (0.750)** | **11/12 (0.917)** |
| p50 latency | **32.7 ms** | **34.4 ms** |
| mean latency | 35.2 ms | 35.0 ms |
| p95 latency | 45.2 ms | 42.3 ms |
| samples | 84 | 84 |

**Latency was measured properly, because the first attempt was noise.** A
single pass gives 12 samples per arm, and two consecutive runs of the *same*
configuration produced p50 33.6 ms and p50 59.1 ms — a 76% swing on
background load alone. Reporting either would have been reporting noise as a
result. The figures above are 7 repeats × 12 questions = 84 samples per arm,
**interleaved question-by-question** so that any drift in machine load is
split across both arms instead of charged to whichever ran second.

At 84 samples the honest reading of +1.7 ms is that BM25 over a 123-chunk
index is **approximately free** — it is an in-memory rank-BM25 scan, and the
p95 actually went *down*. The cost of this change is not latency; it is the
BM25 index build at startup and the memory it occupies, neither of which is
material here.

### What was fixed, and what was not

**Fixed — w01 and w05, both exact-token R-failures.** In both, the correct
chunk was already being retrieved by dense at rank 4 and rank 5; BM25 matched
the literal code and RRF pulled it into the window. This is the mechanism the
change was chosen for, working exactly as the tally predicted.

**Not touched — w04.** BM25 moved the correct chunk from fusion rank 8 to
rank 5, still outside the top-3. Its top-3 after the change:

| Rank | Form | Clause | dense rank | BM25 rank |
|---|---|---|---|---|
| 1 | HO-0633 | 4. Exceptions To The Exclusions | 1 | 1 |
| 2 | HO-0633 | 5. Conditions | 4 | 6 |
| 3 | DP-0208 | Exclusion Table 3.1 | 9 | 2 |

**But w04 is partly a ground-truth artifact, and saying so matters more than
claiming the scalp.** The question is *"does E-53 bite if they only rented 10
days?"* The labelled chunk is the E-53 row. The chunk actually retrieved at
rank 1 is HO-0633 Clause 4.2 — the exception that **disapplies** E-53 within
the 14-day allowance. That is the clause that answers the question. And the
answer produced was correct:

> No. Because the total rental period is only ten days—within the fourteen‑day
> allowance—Exclusion E‑53 does not apply; any bodily‑injury claim would be
> handled under the policy's liability coverages.
> `[chunk_id=HO-0633_home_sharing_business_ed_09-23.pdf#1acf2836c995db59 | HO-0633 | 4.2]`

So w04 scores as a retrieval miss while the app answers it correctly from a
better chunk. The metric is right to be strict — I labelled the E-53 row as
the answer location and it was not retrieved — but the correct engineering
read is that this question has **two** valid answer locations and my ground
truth records one. The honest hit-rate@3 is 11/12; the honest count of
questions the app gets wrong is **1/12 at retrieval and 0/12 at answer**.

**No regressions.** w11 slipped from rank 2 to rank 3 but stayed in the
window.

---

## 6. The other change, measured, not shipped

Running the cross-encoder on top of the fused list — the second option the
brief offers — as information only, never folded into the delta above:

| Configuration | hit@3 | p50 latency |
|---|---|---|
| dense only | 9/12 | 32.7 ms |
| **dense + BM25 + RRF** | **11/12** | **34.4 ms** |
| dense + BM25 + RRF + cross-encoder | 10/12 | **744.6 ms** |

**The cross-encoder makes it worse and costs 22× the latency.** It misses
w04 *and* w11 — it demotes w11 out of the top-3, a question both other
configurations pass. On this set, at k=3, it is 710 ms for −1 question.

This is directly actionable, because `RERANKER` currently defaults to
`ms-marco` in [rag/config.py](rag/config.py) — the shipping app is paying
that 710 ms today. Two caveats before anyone rips it out: Week 3 measured the
cross-encoder favourably at k=5 on a different question set, and 12 questions
is a small sample on which to overturn that. The correct next step is one
more experiment, not a config change.

---

## 7. The model swap would have bought nothing

The team lead wanted to swap the model. The tally says:

| Label | Before | After |
|---|---|---|
| R | 3 | 1 |
| **G** | **0** | **0** |

**Zero generation failures in either arm.** Every question whose correct
chunk reached the top-3 was answered correctly from it. There was no failure
of the kind a better model addresses. Swapping it would have cost budget and
moved hit-rate@3 by exactly zero, because hit-rate@3 does not involve the
model at all.

### The measurement bug that nearly produced the opposite conclusion

The first labelled run reported **5 G failures**, which would have pointed
straight at the model. All five were false positives in my own checker.

The model writes `E‑17` using U+2011 (non-breaking hyphen), not the ASCII
`E-17` in the document, and separates tokens with U+202F (narrow no-break
space). A naive `phrase.lower() not in answer.lower()` therefore reported
that an answer reading *"Exclusion E‑17 is limited to constant or repeated
seepage…"* did not contain `E-17`. w09 compounded it by answering *"two
percent (2 %)"* where the check wanted `2%`.

Every one of those five answers was correct. Had I trusted the first tally, I
would have "fixed" a prompt that was never broken — and the R:G ratio, which
is the entire basis for choosing the change, would have been 3:5 instead of
3:0.

The fix is `normalize_for_match()` in [rag/diagnostics.py](rag/diagnostics.py):
fold typographic Unicode to ASCII, close the gap in `2 %`, and let a required
phrase be a list of acceptable renderings, because *"2%"* and *"two percent"*
are the same claim and pinning one spelling measures house style rather than
correctness.

---

## 8. Bonus — MMR

MMR applied over the fused candidate list, hybrid retrieval, cross-encoder
off, lambda swept once. λ = 1.0 is pure relevance, 0.0 pure diversity.

| Configuration | hit@3 | distinct forms in top-3 | distinct clauses in top-3 | p50 |
|---|---|---|---|---|
| **no MMR (shipped)** | **11/12** | 1.583 | 2.583 | 34.4 ms |
| MMR λ=0.9 | 9/12 | 2.000 | 2.667 | 59.5 ms |
| MMR λ=0.7 | 7/12 | 2.417 | 2.917 | 55.9 ms |
| MMR λ=0.5 | 6/12 | 2.583 | 2.750 | 54.7 ms |
| MMR λ=0.3 | 6/12 | 2.583 | 2.667 | 57.2 ms |

**MMR does exactly what it promises and it is not worth it.** Diversity rises
monotonically as λ falls — distinct forms in the top-3 go from 1.58 to 2.58,
so the top-3 really does stop being three slices of one form. And hit-rate@3
collapses from 11/12 to 6/12 on the way.

The trade is not subtle. Even the gentlest setting tested, λ=0.9, costs two
questions to gain 0.42 distinct forms, and adds 25 ms. Every step further
costs more than it buys.

The reason is the premise. The bonus supposes the top-3 is "the same exclusion
text repeated across three form editions" — a redundancy problem MMR is built
for. **That is not what this index does.** The corpus has one edition of each
form, and the Week 3 structure chunker already stamps every chunk with its
form and clause, so the top-3 averages 2.58 distinct *clauses* before MMR is
switched on. The redundancy MMR exists to remove had already been removed by
chunking. What MMR does here instead is push a *correct* chunk out of the
window to make room for a different form — which is precisely the risk the
brief names, and it is realised at every lambda tested.

**Would not ship.** If the top-3 ever does fill with near-duplicates — a
plausible future once multiple editions of the same form are indexed
together, which is exactly what HO-0710 Clause 3.1 exists to arbitrate — this
should be re-measured. Today it costs 5 questions and 25 ms to solve a
problem the index does not have.

---

## 9. A note on the corpus

The experiment reads from `eval/corpus/`, built by
[tools/prepare_corpus.py](tools/prepare_corpus.py), not directly from
`insurance_docs/`.

`insurance_docs/` is a working directory, and during this session it was
cleared and repopulated three times by activity unrelated to this task —
including a 31 MB FEMA NFIP flood-insurance manual appearing in it, and
`policy.pdf` being deleted twice. An evaluation whose corpus silently changes
between the baseline run and the after run is not an evaluation; it is two
unrelated measurements with a delta printed between them.

`prepare_corpus.py` therefore rebuilds the six endorsements from
source-controlled text, restores `policy.pdf` from git if it is missing, and
**names anything it deliberately excludes** so the exclusion is on the record:

```
Deliberately NOT in the evaluation corpus (present in insurance_docs/ but
out of scope for this task): fema_nfip_flood-insurance-manual_102025.pdf
```

It also refuses to run if the corpus is not exactly seven documents.

---

## 10. Shipping decision

**Keep BM25 + RRF (k=60). It is already the default, and this is the number
that justifies it.**

This has to be stated plainly, because it changes what the deliverable is.
`DEFAULT_MODE` in [rag/config.py](rag/config.py) was **already** `hybrid`
before this task started — BM25, RRF and the fusion path were built in an
earlier week. There was no un-improved baseline left on disk to measure
against, so the before/after was obtained as an **ablation**: switch fusion
off, measure, switch it back on, measure again. The delta is identical either
way, but the direction of the work was backwards from how the brief describes
it, and calling that a "change I made" would be a fabrication.

The number: **hit-rate@3 9/12 → 11/12 for +1.7 ms p50** (84 samples per arm,
interleaved). Two of the three R-failures bought back, no regressions, and
the two it fixed are exactly the exact-token lookups the tally predicted. The
cost is indistinguishable from measurement noise on this corpus, and p95
improved. Before this run, hybrid was shipped on the strength of it being the
obviously-correct thing to do. It now has evidence.

**Do not ship MMR.** −5 questions, +25 ms, to remove a redundancy the chunker
already removed.

**The one config change actually on the table: turn the cross-encoder off.**
`RERANKER` defaults to `ms-marco` today, so the shipping app pays ~710 ms per
query for a configuration that scores **10/12 against hybrid's 11/12** on this
set. I am not changing it in this diff. It contradicts the Week 3 measurement
at k=5, and 12 questions is a thin basis for overturning that — this needs
its own before/after with its own golden set, which is precisely the
discipline this week is about. Flagged, not actioned.

**Do not swap the model.** 0 of 12 failures were generation failures.

---

## 11. Code diff

**There is no new retrieval code in this diff, and that is the honest
answer.** The retrieval change under test — BM25 + RRF k=60 — already existed
and was already the default. What this task added is the apparatus that can
tell whether it earns its place: a chunk-id golden set, a failure classifier
that produces R/G/Not-In-Corpus with trace evidence, a p50 latency
measurement, and a runner that holds exactly one variable.

New:

| File | Purpose |
|---|---|
| [`tools/prepare_corpus.py`](tools/prepare_corpus.py) | Builds and verifies the fixed 7-document evaluation corpus. |
| [`tools/build_w4_golden.py`](tools/build_w4_golden.py) | The 12 questions; resolves anchors to chunk_ids; writes `eval/golden_set.jsonl`. |
| [`tools/run_week4.py`](tools/run_week4.py) | Both arms, the tally, the latency benchmark, the MMR sweep, the cross-encoder reference. |
| [`eval/golden_set.jsonl`](eval/golden_set.jsonl) | 12 questions with known-correct chunk_ids. |

Changed:

| File | Change |
|---|---|
| [`rag/evaluation.py`](rag/evaluation.py) | Added `percentile()` and `latency_summary()`; `latency_ms` now reports **p50** first, then mean and p95. Previously p95-only — which on a 12-question set is the maximum, not a tail. |
| [`rag/diagnostics.py`](rag/diagnostics.py) | Added `TASK_LABELS` (R / G / Not-In-Corpus), `Diagnosis.task_label`, `classify_by_chunk_id()` for chunk-level verdicts with a trace-derived evidence line, and `normalize_for_match()` / `missing_phrases()` to stop typographic Unicode being scored as a generation failure. |
| [`rag/config.py`](rag/config.py) | Unchanged for retrieval. `DEFAULT_MODE` was already `hybrid`; `RERANKER` is left at `ms-marco` pending the experiment in §6. |

The retrieval configuration under test is set per-call in
`common_options()` in [tools/run_week4.py](tools/run_week4.py) rather than by
editing config, so the two arms cannot drift apart through a stale
environment variable.

---

## Reproducing

```bash
python tools/prepare_corpus.py     # 7-document corpus, verified
python tools/build_w4_golden.py    # resolve chunk_ids -> eval/golden_set.jsonl
python tools/run_week4.py          # both arms, tally, latency, MMR, cross-encoder
```

Artefacts land in `eval/results/week4/`: `week4.json`, `not_in_corpus.json`.
