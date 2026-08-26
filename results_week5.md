# Week 5 Practical — Task Set D

## Read 20 real traces and hand back a ranked taxonomy

**Domain:** insurance claims · **App:** the claims assistant in this repo, on
its default settings · **Date:** 2026-08-26

---

## Summary of numbers

| | |
|---|---|
| Traces in the file | **82** (70 random-population + 12 curated demo) |
| Sample size | **20**, seeded |
| Seed | **20260826** |
| Selection | `random.Random(20260826).sample(sorted(trace_ids), 20)` |
| Failure modes named | **5**, plus a no-failure row |
| Top mode | *Answers without the clause that decides the claim* — **4/20 = 20%** |
| Top mode, curated demo set | **0/10 = 0%** |
| Prediction commit | **`ad526e4`**, dated 2026-08-26, before any fix |
| Open-coding commit (modes all null) | **`a5faea1`** |

---

## 1. The system that produced the traces

Everything ran on the app's **default** settings — hybrid retrieval with RRF,
`top_k=3`, the ms-marco cross-encoder, the default score floor, no metadata
filters and no query transforms. Running the traffic under tuned settings
would have produced a taxonomy of a system nobody actually uses.

Corpus: 24,523 chunks across 8 documents — six endorsements (HO-0304, HO-0412,
HO-0521, HO-0633, HO-0710, DP-0208), the base motor wording, and the 31 MB FEMA
NFIP flood-insurance manual. The flood manual is in there because it is in
`insurance_docs/`; it is what the app can actually search.

Traffic: 24 claim-summary requests and 46 adjuster questions, including
multi-turn follow-ups. Written from the claims-desk side and **not** tuned after
seeing what the app did with them.

### The first trace run had to be thrown away

The first 82-trace run came back with **65 of 82 outputs** being the string
`The language model request failed: Error code: 429`. The Groq free tier meters
8,000 tokens/minute and 200,000/day *per model*, and 70 traces of
`gpt-oss-120b` spent the whole daily budget.

Nothing in the app noticed, because `rag/generation.py` returns a failed request
as the answer text rather than raising — correct for a CLI session, catastrophic
for a trace corpus. It turns one afternoon of rate limiting into 65
apparently-terrible answers, and **a taxonomy built on those would have
described Groq's free tier rather than the claims assistant.**

Fixed in `rag/llm.py` (commit `0c5c585`): 429s are retried, reading the wait out
of the error body rather than backing off blindly, and a request that still
cannot be served raises instead of being smuggled downstream as content. The app
was moved to `gpt-oss-20b` and the judge to `gpt-oss-120b`, which fits the two
daily budgets and is the better design anyway — **a judge that is the same model
as the generator grades its own homework.** The re-run produced 82 traces with
**zero** API errors.

---

## 2. Requirement-by-requirement

### 1. Traces are replayable — `tr-wk5-0009` ✔

`python tools/w5_replay.py tr-wk5-0009`

| Stage | Result |
|---|---|
| Retrieval | **identical** — same 3 chunk_ids, same order |
| Prompt template sha256 | `45b782ce052f1c74` = `45b782ce052f1c74` **match** |
| Prompt rendered sha256 | `64940c1f88a42154` = `64940c1f88a42154` **match** |
| Output | identical for the first **447 characters**, then diverges |

The rendered-prompt hash match is the load-bearing check: the replayed model
call received the same bytes the original did, so any difference in output is
the model, not the harness. The two outputs agree on every labelled field and
most of the narrative, and split only in the closing sentence — **`temperature=0`
is not determinism.**

**Fields added because replay needed them:** `input.history` (without it every
follow-up turn replays as a first turn) and `model.reasoning_effort` (gpt-oss
emits unshown reasoning tokens whose budget changes the answer).

**Could not be reconstructed:** chunk *text* (resolved by id from the live
index — a re-index makes historical traces unreplayable, which the prompt-hash
check detects rather than hides); the server-side model build; and sampling
non-determinism, since no `seed` was sent and the trace records that honestly
as `null`.

**Redaction is before the write, not after** — and enforced twice.
`ClaimFile.redacted()` pseudonymises at the point the claim enters the app, so
identifiers never reach the LLM at all; `TraceWriter.write()` redacts again and
then **refuses to write** if any registered name or un-minted claim number
survives. Claim numbers become stable HMAC surrogates in the same
`CLM-YYYY-NNNNN` shape rather than `[REDACTED]`, so traces stay linkable and the
Week 6 format assertion stays testable.

That check caught a live bug during the build: the best-effort name regex had
`re.IGNORECASE` set, so `[a-z]` matched uppercase, the pattern matched inside
its own surrogates, and `"FF"` from `[CLAIMANT-FF16E0]` was registered as a
claimant name — which then matched hex digits in every chunk_id and refused
every trace. A redactor that merely redacted would have shipped that silently.

### 2. Seeded random sample of 20 ✔

Seed **20260826**, drawn from the **sorted** id list over the 70-trace
population (the 12 `demo` traces excluded from the frame). Sorting matters:
appending one trace reshuffles any position-based sample and the seed stops
naming the same twenty.

Full list in [notes.md](notes.md) §1 and `eval/w5/sample.json`.

### 3. All 20 open-coded, zero fixes ✔

Twenty sentences in [notes.md](notes.md) §4. **Committed with every `mode` field
`null` in `a5faea1`, before any clustering existed** — that commit is the
evidence, not an oversight. Modes were assigned in a second pass over the
sentences in `ad526e4`.

**Zero code changes to the app during coding.** The app is unchanged from
`582b225`, the commit that produced the traces.

### 4. The taxonomy ✔

See [taxonomy.md](taxonomy.md).

| Mode | Count | % of 20 | Severity | Example |
|---|---:|---:|---|---|
| Answers without the clause that decides the claim | 4 | 20.0% | wrongly denies **or wrongly pays** | `tr-wk5-0012` |
| Coverage position field contradicts its own narrative | 4 | 20.0% | wrongly denies a claim | `tr-wk5-0014` |
| Comes back with the wrong product's wording, or nothing, and declines | 3 | 15.0% | annoys the adjuster | `tr-wk5-0020` |
| Reports no deductible or excess figure | 2 | 10.0% | annoys the adjuster | `tr-wk5-0003` |
| Quotes a clause under the wrong number, or cites without naming the form | 2 | 10.0% | annoys the adjuster | `tr-wk5-0005` |
| *No failure observed* | 5 | 25.0% | — | `tr-wk5-0026` |

**The one that pays out money it shouldn't:** `tr-wk5-0012`. A pipe froze while
the insured had the heating switched off entirely — E-14 excludes exactly that —
and the app returned **COVERED**. The exclusion-table chunk it was handed
carried E-15, E-16 and E-17. The E-14 row was in no retrieved chunk.

**The number the table hides.** Each trace carries its single worst defect, so a
defect present everywhere but never the worst is invisible. The **Deductible
field read UNKNOWN in 10 of 10 claim-summary traces — 100%, not the 10% the mode
row shows.** Eight of those ten are filed under a more serious mode.

The cause is in the traces: a summary issues **one** retrieval over the whole
note with `top_k=3`, and all three slots go to exclusion-table rows. The proof
the clause is retrievable at all is `tr-wk5-0026`, where an adjuster asked for
the HO-0304 deductible *directly* and Clause 5.3 came back top at rerank **8.3**
with the right answer and a resolving citation.

### 5. Dated, falsifiable prediction ✔

[prediction.txt](prediction.txt), commit **`ad526e4`**, 2026-08-26, before any fix.

> Scope the summary retrieval to the form the claim file names, retrieve the
> limits-and-deductible clause separately, and raise `top_k` from 3 to 8.
>
> - `deductible_numeric` assertion pass rate: **0% → at least 70%**
> - *Answers without the clause that decides the claim*: **20% → under 10%**
> - *Wrong product's wording, or nothing*: **15% → under 5%** (on cases naming a form)
> - `tr-wk5-0012` specifically flips **COVERED → DENIED on E-14**

It also records what would falsify each and where I already expect to be wrong:
`tr-wk5-0009` wanted the Clause 2.1 coverage **grant**, and a query built from an
adjuster's damage note does not look like a coverage grant no matter how many
slots it gets.

### 6. Why a public benchmark misses the top 3 ✔

In [notes.md](notes.md) §5, three sentences. The short of it: in `tr-wk5-0012`
the retrieved passage genuinely supports every sentence written, and no
benchmark scores the passage that never arrived; the second mode is a formatting
failure with a financial consequence that reference-matching marks as broadly
right; and the third requires knowing that E-17 on homeowners and E-71 on
dwelling fire say nearly the same thing and dispose of it differently — a fact
about *this* insurer's form library that exists in no public corpus.

---

## Bonus — the curated demo set

Ten more traces open-coded from the 12 tagged `demo`, using **the same mode
list** derived from the random sample.

| | Random sample | Curated demo set |
|---|---:|---:|
| Traces | 20 | 10 |
| Top mode *Answers without the clause that decides the claim* | **4 (20%)** | **0 (0%)** |
| Any failure observed | **15 (75%)** | **0 (0%)** |

### What the team has been telling itself for the last month

The demo set is not a fair sample and never was. Every one of its twelve
questions names its form number in the question text — "under form HO-0304 ed.
03-24", "on HO-0412", "under HO-0521 ed. 01-24" — which hands the retriever an
exact token to match and collapses a 24,523-chunk corpus to one two-page
document. Real adjuster traffic does not do this: it says *"sump pump had no
service records, covered?"* and leaves the form to be inferred.

Two traces make the point better than the percentages. `tr-wk5-0006`, from the
random sample, needed HO-0521 Clause 2.2 — the eight-hour secondary power
requirement — could not retrieve it, and returned UNDETERMINED. `tr-demo-0009`
asks for **that same clause of that same form**, naming the form, and gets it at
rerank 5.5 with a correct answer and a resolving citation. Same clause, same
index, same day. The only difference is that the demo question says "HO-0521".

The same holds for the deductible. Ten of ten claim summaries said UNKNOWN;
`tr-demo-0008` asks "what deductible applies under HO-0412" and answers "2% of
the Coverage A limit, minimum $1,000" from a top chunk at rerank **8.9**.

So for a month the monthly review has been demonstrating that the retriever
works well **when it is told where to look**, and reporting that as evidence the
assistant works. Every failure in the taxonomy above lives in the gap between
those two statements. The demo set cannot fall, so it has never once caught a
regression, and its 0% failure rate is a measurement of the questions, not of
the app.

---

## Reproducing this

```bash
python tools/w5_traffic.py                 # the 70-trace population
python tools/w5_traffic.py --demo          # the 12 curated demo traces
python tools/w5_sample.py --seed 20260826 --n 20
python tools/w5_replay.py tr-wk5-0009
python tools/w5_read.py --sample eval/w5/sample.json
python tools/w5_taxonomy.py --coding eval/w5/open_coding.json
```

Every number in `taxonomy.md` is computed by `tools/w5_taxonomy.py` from the
coding file, not typed by hand.
