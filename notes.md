# Week 5 — reading 20 traces by hand

Companion to [taxonomy.md](taxonomy.md). Everything here is evidence for the
rows in that table.

---

## 1. The seeded sample

```
trace file : traces/claims_traces.jsonl        82 traces
frame      : 70 random-population traces       (the 12 tagged `demo` excluded)
seed       : 20260826
selection  : random.Random(20260826).sample(sorted(trace_ids), 20)
drawn      : 10 claim-summary traces, 10 adjuster-Q&A traces
```

The ids are sampled from the **sorted** id list, not from the file in disk
order. That is the whole reproducibility of the exercise: appending one more
trace to a JSONL file reshuffles every position-based sample, and the seed
would then no longer name the same twenty traces.

```
tr-wk5-0003  tr-wk5-0005  tr-wk5-0006  tr-wk5-0007  tr-wk5-0008
tr-wk5-0009  tr-wk5-0010  tr-wk5-0012  tr-wk5-0014  tr-wk5-0020
tr-wk5-0026  tr-wk5-0027  tr-wk5-0039  tr-wk5-0040  tr-wk5-0056
tr-wk5-0061  tr-wk5-0062  tr-wk5-0067  tr-wk5-0068  tr-wk5-0069
```

Machine-readable: `eval/w5/sample.json`. Reproduce with
`python tools/w5_sample.py --seed 20260826 --n 20`.

---

## 2. Replay evidence — `tr-wk5-0009`

Replayed from the trace record alone (`python tools/w5_replay.py tr-wk5-0009`).
The replayer reads only the trace: the recorded queries, the recorded retrieval
options, the recorded chunk_ids, the recorded prompt version and hashes, and the
recorded model parameters. It never looks the case up in the population file.

| Stage | Result |
|---|---|
| Retrieval | **identical** — same 3 chunk_ids, same order |
| Prompt template sha256 | `45b782ce052f1c74` recorded = `45b782ce052f1c74` rebuilt — **match** |
| Prompt rendered sha256 | `64940c1f88a42154` recorded = `64940c1f88a42154` rebuilt — **match** |
| Output | **not byte-identical** |

The rendered-prompt hash matching is the load-bearing check: it proves the
replayed model call received the same bytes the original did, so any output
difference is the model and not the harness.

**What differed.** The two outputs are character-for-character identical for
the first **447 characters** — every labelled field (claim number, date of
loss, policy line, coverage position, exclusion, deductible) and most of the
narrative. They diverge in the closing sentence only:

```
original : ... unclear whether the water damage itself is covered, and the claim
           remains unresolved pending further policy review.
replayed : ... unclear whether the water damage itself is covered, and the
           exclusion list alone does not resolve the claim. Further policy
           review or additional coverage clauses are needed to determine the
           final position.
```

The replay also emitted markdown hard-break trailing spaces the original did
not. **`temperature=0` is not determinism**, and a trace pipeline that assumes
it is will report phantom regressions.

### Fields that had to be added

The trace schema was written against the list the brief names, so the run that
produced these traces already carried prompt version, chunk_ids with per-stage
scores, model and params, and raw output. Two fields were added *because the
replay needed them* and would not otherwise have been obvious:

- **`input.history`** — the Q&A path replays prior turns before the grounded
  prompt. Without it, every follow-up turn (e.g. `tr-wk5-0026`, turn 2) replays
  as a first turn and diverges for a reason that looks like model noise.
- **`model.reasoning_effort`** — gpt-oss emits unshown reasoning tokens whose
  budget changes the answer. A replay that picked up today's config default
  instead of the recorded value would silently be replaying a different call.

### What could NOT be reconstructed

- **Chunk text.** Not stored — it would multiply the file size by roughly forty.
  Replay resolves text by `chunk_id` against the live index, so a re-index that
  changes chunk boundaries makes historical traces unreplayable. The prompt-hash
  check detects that rather than letting it pass as a model difference.
- **The exact server-side model build.** `openai/gpt-oss-20b` is a moving
  target; nothing in the trace pins the weights.
- **Sampling non-determinism.** No `seed` was sent (recorded as `null`, honestly).
  This is the divergence above.

---

## 3. Redaction is before the write, not after

Confirmed, and enforced in two places rather than promised in one:

1. `ClaimFile.redacted()` pseudonymises the claimant name and claim number at
   the point the claim **enters the app** — before retrieval, before the model
   call. The real identifiers never leave the process, so they are not in a
   third-party API's logs either.
2. `TraceWriter.write()` redacts again and then **verifies**, raising and
   refusing to write if any registered claimant name or any un-minted claim
   number survives. That check is what makes the ordering a property of the
   code rather than a comment.

Claim numbers become stable HMAC surrogates *in the same `CLM-YYYY-NNNNN`
shape* rather than `[REDACTED]`, so two traces about one claim stay linkable
and the downstream format assertion stays testable.

**The check earned its keep during the build.** The best-effort name regex had
`re.IGNORECASE` set, which made `[a-z]` match uppercase — so it matched inside
its own surrogates and registered `"FF"` out of `[CLAIMANT-FF16E0]` as a
claimant name. A two-character "name" then matched hex digits in every chunk_id
in the record, and the writer refused every trace. A redactor that merely
redacted would have shipped that silently.

---

## 4. The 20 open-coding sentences

One sentence per trace, describing what was **seen**. Not a diagnosis, not a
category, not a fix. All twenty were written and committed with every `mode`
field `null` (commit `a5faea1`) **before** any clustering was attempted; the
modes were added in a second pass over the sentences, in a separate commit.

**Zero code changes were made to the app during this step.** The app is exactly
as it was when the traces were produced.

| # | trace_id | What I saw |
|---|---|---|
| 1 | `tr-wk5-0003` | Denied the hail claim on E-34 with a citation that resolves, and the Deductible field says UNKNOWN even though the claim is on HO-0412; the three chunks that reached the prompt were the exclusion table, the roof-surfacing clause and the conditions clause. |
| 2 | `tr-wk5-0005` | Denied on E-44 and the narrative says the exclusion applies "unless the insured provides service records for the preceding 24 months", which is language from the separate Clause 4 conditions chunk rather than from E-44's own disposition, and the summary carries no chunk_id citation anywhere. |
| 3 | `tr-wk5-0006` | Answered UNDETERMINED, attributed a power-source requirement to "clause 4.1", and said the wording does not clarify what happens when the power source is unavailable; Clause 2.2, which states the eight-hour secondary power requirement, was not among the three chunks retrieved. |
| 4 | `tr-wk5-0007` | Answered UNDETERMINED and said in terms that "the wording of Clause 4.2 is not provided"; all three retrieved chunks came from page 1 of HO-0633 and Clause 4.2 sits on page 2. |
| 5 | `tr-wk5-0008` | Denied on E-53, referring to Clause 4.1 and Clause 5.1 by number and reasoning from the 41 nights in the notes, and the summary carries no chunk_id citation. |
| 6 | `tr-wk5-0009` | Answered with the bare refusal sentence and a narrative saying the wording "includes exclusions for water damage and mould (E-75, E-76) but does not provide a corresponding coverage clause"; the three retrieved chunks were DP-0208 exclusion-table and scope chunks and did not include the Clause 2.1 coverage grant. |
| 7 | `tr-wk5-0010` | Denied on Clause 2.2 with "Exclusion relied on: NONE", and the Deductible field says UNKNOWN while the narrative in the same summary states the $5,000 figure — the Clause 5 deductible chunk was retrieved at position 2. |
| 8 | `tr-wk5-0012` | Answered COVERED for a pipe that froze while the insured had the heating switched off entirely, reasoning that the burst is sudden and accidental and E-17 does not reach it; the exclusion-table chunk that reached the prompt carried only E-15, E-16 and E-17, and the E-14 freezing row was not in any retrieved chunk. |
| 9 | `tr-wk5-0014` | Set the position to DENIED naming E-33, and the narrative in the same summary says the fence portion "is covered"; three chunk_id citations, all of which resolve. |
| 10 | `tr-wk5-0020` | For a claim whose file recorded no form number, all three chunks that reached the prompt were FEMA NFIP flood-manual page ranges with policy_line "unspecified" and rerank scores near −5.4, and the output was the one-line refusal sentence and nothing else. |
| 11 | `tr-wk5-0026` | Answered "$2,500 per loss" with a citation that resolves, on a second-turn question about the HO-0304 deductible, where Clause 5.3 was the top chunk at rerank 8.3. |
| 12 | `tr-wk5-0027` | Nothing survived the relevance floor — three candidates dropped, zero reached the prompt — and the answer was the refusal sentence, for a question about a weeping joint running about a month. |
| 13 | `tr-wk5-0039` | Answered that failing to produce the rental log raises a presumption the allowance was exceeded, with a citation whose form-number field reads "5.1 \| 5.1" instead of naming HO-0633. |
| 14 | `tr-wk5-0040` | Answered the question "Is that excluded?" with "Yes" and then said in the next two sentences that the activity is not excluded and is covered. |
| 15 | `tr-wk5-0056` | Reproduced the HO-0710 definition of sudden and accidental almost verbatim with a citation that resolves, having retrieved the definition chunk at rerank 6.6 ahead of the HO-0304 and DP-0208 coverage grants. |
| 16 | `tr-wk5-0061` | Answered "Yes" to whether E-49 applies and then quoted its disposition, "Excluded unless remediation certified", which makes the answer conditional on a fact the question never stated. |
| 17 | `tr-wk5-0062` | Answered that loss of use beyond thirty days is excluded, citing the HO-0521 exclusion table, with a FEMA flood-manual page range sitting in the retrieved set at position 3 with rerank −5.4. |
| 18 | `tr-wk5-0067` | For a question about theft during a short let, two candidates were dropped below the floor, the single survivor was policy.pdf — the motor wording — at rerank −4.2, and the answer was the refusal sentence. |
| 19 | `tr-wk5-0068` | Answered that solar collectors are excluded unless scheduled, with a citation that resolves, from a retrieved set in which all three chunks scored negative on the reranker. |
| 20 | `tr-wk5-0069` | Quoted E-39 and its disposition for a question about loss of use where the dwelling is still habitable, with a citation that resolves. |

I did not write "I don't know why this failed" for any of the twenty, but the
closest is #16: the app quoted E-49's disposition correctly and answered "Yes"
anyway, and I cannot tell from the trace whether it read the disposition and
disregarded it or answered before reaching it.

---

## 5. Why a public benchmark would have missed the top three modes

A public RAG benchmark scores whether a retrieved passage supports an answer,
and all three of my top modes are invisible to that test: in `tr-wk5-0012` the
passage genuinely supports every sentence written — the E-14 row that would
have contradicted it simply was not in the corpus slice retrieved, and no
benchmark scores the passage that never arrived. The second mode is a
*formatting* failure with a financial consequence, where the narrative is
correct and the labelled field a routing queue reads is not; a benchmark
comparing generated text to a reference answer marks that as broadly right,
because most of the text is. The third mode requires knowing that E-17 on the
homeowners line and E-71 on the dwelling-fire line say almost the same thing
and dispose of it differently — a fact about *this* insurer's form library that
exists in no public corpus, so no public benchmark contains a single item that
could have exposed it.

---

## 6. Prediction

See [prediction.txt](prediction.txt), committed with today's date **before any
fix**. Commit hash recorded in `results_week5.md`.
