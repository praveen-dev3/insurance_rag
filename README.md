# Insurance Claim RAG

Ask questions about insurance PDFs and get answers grounded in those
documents, with the file and page cited on every claim — plus the tooling to
find out *why* it is wrong when it is wrong, and to prove a fix with a number.

Embeddings and reranking run locally. Only the final generation call leaves the
machine. Three front ends over one engine: a **React chat UI with a retrieval
inspector**, a **CLI**, and an **evaluator**.

---

## Contents

- [The pipeline](#the-pipeline)
- [Design decisions — what we used and why not the alternatives](#design-decisions--what-we-used-and-why-not-the-alternatives)
- [Measured results](#measured-results)
- [Layout](#layout)
- [Setup](#setup)
- [Running the chat UI](#running-the-chat-ui)
- [Running the CLI](#running-the-cli)
- [Running the evaluator](#running-the-evaluator)
- [Failure separation](#failure-separation)
- [Configuration](#configuration)
- [API](#api)
- [Known limits](#known-limits)

---

## The pipeline

```
                          question
                             │
   ┌─────────────────────────┴──────────────────────────┐
   │ QUERY TRANSFORMS                                    │
   │  condense  follow-up  →  standalone question        │
   │  rewrite   user phrasing → policy vocabulary  (opt) │
   │  HyDE      draft answer, embed that instead   (opt) │
   └─────────────────────────┬──────────────────────────┘
                             │
        ┌────────────────────┴────────────────────┐
        ▼                                         ▼
  DENSE  bge-small-en-v1.5                 SPARSE  BM25 Okapi
  HNSW, cosine, top 20                     top 20, zero-score dropped
        │                                         │
        └────────────────────┬────────────────────┘
                             ▼
                  RRF FUSION   1/(60 + rank)
                             │
                    MMR  (optional)  λ·relevance − (1−λ)·redundancy
                             │
                    RERANK  cross-encoder / BGE / Cohere
                             │  drops everything below the relevance floor
                             ▼
                grounded prompt → LLM → cited answer
                             │
                    DIAGNOSE (optional)
                    retrieval failure? generation failure?
```

Every stage records what it saw and what it passed on, into a
`RetrievalTrace`. That trace is what the inspector renders and what the failure
classifier reasons over.

---

## Design decisions — what we used and why not the alternatives

The short version, then the reasoning for the choices that are not obvious.

| Layer | Chosen | Main alternatives | Why this one |
|---|---|---|---|
| PDF text | **pypdf** | PyMuPDF, pdfplumber, `unstructured`, LlamaParse | Pure Python, no system libraries, no API key |
| Chunking | **hand-written recursive splitter** | LangChain splitters, semantic chunking | ~150 lines, page provenance built in, three strategies swappable and measurable |
| Token budget | **tiktoken** | model tokenizers, word counts | Fast, deterministic, no model load to count |
| Embeddings | **BAAI/bge-small-en-v1.5**, local | OpenAI `text-embedding-3`, Cohere Embed, MiniLM | Top MTEB retrieval at 130 MB, free, offline |
| Vector store | **Chroma (embedded)** | FAISS, Qdrant, Weaviate, pgvector, Pinecone | Persistent, metadata filtering, HNSW, zero servers |
| ANN index | **HNSW, cosine** | IVF-Flat, brute force | Chroma's default, tunable, right for a small mutable corpus |
| Keyword search | **rank_bm25 (Okapi)** | Elasticsearch/OpenSearch, SQLite FTS5, Tantivy | No JVM, no container; full control of tokenisation |
| Fusion | **Reciprocal Rank Fusion** | weighted score blend, learned fusion | No score-scale reconciliation, no per-corpus tuning |
| Reranker | **ms-marco cross-encoder**, local | Cohere Rerank, BGE-reranker, LLM-as-reranker | 90 MB, free, offline; the other two are wired up behind a flag |
| Diversity | **MMR** | clustering, hash dedup | Uses vectors already in the index; one λ to tune |
| LLM | **Groq `llama-3.3-70b-versatile`** | OpenAI, Anthropic, local llama.cpp | Fast enough that streaming feels instant; grounded QA does not need a frontier model |
| LLM SDK | **`openai` client, Groq base URL** | `groq` SDK, LiteLLM | Provider swap is a one-line base-URL change |
| Orchestration | **none — plain Python** | LangChain, LlamaIndex, Haystack | The stages *are* the deliverable; a framework hides them |
| API | **FastAPI** | Flask, Django, Litestar | Pydantic validation, SSE, sync handlers on a threadpool |
| Streaming | **Server-Sent Events** | WebSocket, long polling | One-directional is all this needs; plain HTTP |
| UI | **React + Vite + TypeScript** | Streamlit, Gradio, Next.js | The inspector needs real layout control |
| UI state | **React state + props** | Redux, Zustand, TanStack Query | One screen, one conversation |
| Styling | **plain CSS + custom properties** | Tailwind, MUI, shadcn | Six components; theming is 40 tokens |
| Markdown | **90-line renderer** | react-markdown + rehype | Renders correctly on half-streamed text |
| Evaluation | **hand-written metrics** | RAGAS, TruLens, DeepEval | Retrieval metrics must be deterministic and LLM-free |
| Packaging | **uv** | pip + venv, Poetry, PDM | Lockfile, fast resolution, one tool |

### Why no LangChain or LlamaIndex

This is the decision everything else follows from. Both frameworks would have
supplied a hybrid retriever, a reranker wrapper and a chunker out of the box —
perhaps 400 lines of the roughly 2,000 here.

They were rejected because **the pipeline stages are the product, not
plumbing.** The point of this project is to be able to say "the cross-encoder
scored the right chunk at −8.36, below the −8.0 floor, and that is why the
answer was wrong". That requires every stage to hand back its own ranked list
with its own scores attached, which means owning the objects that flow between
stages. Getting the equivalent trace out of a framework's chain means either
fighting its callback system or reaching past its abstractions — at which point
the abstraction has cost more than it saved.

Second reason: dependency weight. LangChain pulls a large transitive tree that
changes fast, for a project whose actual dependencies are four libraries and two
models.

The honest cost: more code to maintain, and no free integrations. If this grew
to a dozen document types with a dozen loaders, that trade would flip.

### Why local embeddings, and why BGE specifically

Hosted embeddings (OpenAI `text-embedding-3-small`, Cohere Embed) are excellent
and would have removed a 130 MB download. They lose on three counts here:
insurance documents are personal data and the whole corpus would have to be
uploaded to be indexed; re-indexing during a chunking sweep would mean six full
passes over the corpus at API prices; and every retrieval evaluation would need
a network round trip per question.

Among local models, **bge-small-en-v1.5** was picked over `all-MiniLM-L6-v2`
(the obvious default) because it scores substantially higher on the MTEB
retrieval benchmark at the same 384 dimensions and a similar size, and it takes
512 tokens per passage rather than 256 — which is what makes a 220-token chunk
safe. MiniLM, `bge-base` and both E5 sizes are all still selectable via
`EMBEDDING_MODEL`.

**The asymmetry is the part that is easy to get wrong.** E5 and BGE are trained
with different prefixes for queries and passages (`query: ` / `passage: ` for
E5; an instruction on the query for BGE). Omitting the prefix does not error —
the vectors still come out, they are just worse. So the prefixes live with the
model definition in [rag/embeddings.py](rag/embeddings.py), and embeddings are
computed there rather than through Chroma's built-in embedding function, which
has no way to express "encode queries differently from documents". MMR needs the
candidate vectors anyway, so owning the encoder pays twice.

### Why Chroma, not FAISS or a server database

| Candidate | Why not |
|---|---|
| **FAISS** | Fastest of the lot, but it is an index, not a store: no document text, no metadata, no filtering. All three would have to be rebuilt around it |
| **Qdrant / Weaviate / Milvus** | Better at scale and better filtering, but each needs a running server or a Docker container. That is real setup friction for a corpus that fits in memory |
| **pgvector** | Excellent if Postgres is already there. It is not, and adding a database server to run one query is disproportionate |
| **Pinecone** | Hosted, paid, and sends the corpus off the machine — the same objection as hosted embeddings |

Chroma is embedded (`PersistentClient` on a local directory), stores documents,
metadata and vectors together, supports the `$and` / `$in` / `$gte` filtering
the page-range filter needs, and ships HNSW with the knobs exposed.

Lock-in is limited by design: [rag/retrieval.py](rag/retrieval.py) touches only
`query`, `get` and `add`. Swapping the store means reimplementing three calls.

### Why rank_bm25, not Elasticsearch

BM25 is the whole reason hybrid retrieval works here — `TN06BJ2206` and
"Section II-1(ii)" are exactly the tokens a vector model blurs. The question was
only where to get it.

Elasticsearch and OpenSearch are the industrial answer, and they would bring
filtering, persistence and scale along with the scoring. They also bring a JVM
and a container to a project that otherwise runs with `python main.py`.

`rank_bm25` is a few hundred lines of pure Python. Its index is rebuilt in
memory at startup from the chunks already in Chroma, which means **there is no
second store to keep in sync** — the vector index remains the single source of
truth for what is indexed, and a re-index cannot leave the two halves
disagreeing.

The cost is honest and documented: scoring is O(corpus) per query and the index
is rebuilt on every process start. Fine at thousands of chunks, wrong at
millions. At that point the sparse half moves to Elasticsearch and the fusion
code does not change.

### Why RRF, not a weighted score blend

The alternative is to normalise both scores and blend them:
`α·cosine + (1−α)·bm25`. It is tempting because α looks like a dial you can
tune.

It was rejected because the two scores are not commensurable. A cosine distance
lives in [0, 2] with a corpus-dependent distribution; a BM25 score is unbounded
and scales with document length and corpus statistics. Min-max normalising them
per query makes the blend depend on how good the *worst* result happened to be,
which is not a property anyone wants to tune against. And α would need
re-tuning for every corpus.

RRF ignores magnitudes entirely and sums `1/(60 + rank)` across the lists a
chunk appears in. A chunk both retrievers rank well beats one that only a single
retriever loved, with nothing to tune. Its known weakness — it cannot tell a
dominant BM25 hit from a marginal one, since only the rank survives — is exactly
what the reranking stage exists to correct.

### Why a local cross-encoder, with hosted reranking still wired up

Cohere Rerank is, on average, the better model. It is also a paid API call on
every query and another copy of the corpus leaving the machine. `ms-marco-MiniLM-L-6-v2`
is 90 MB, runs on CPU in about a second for a 20-candidate shortlist, and is the
default for that reason.

All three live behind one `score(question, texts)` interface in
[rag/rerankers.py](rag/rerankers.py), including `none`, so "what does reranking
actually buy?" is a measurable question rather than an article of faith — see
the sweep below, where it buys +0.094 hit@1 on top of fusion.

Each reranker carries **its own relevance floor**, because the scores are not
comparable: ms-marco and BGE emit unbounded logits, Cohere emits 0–1 relevance.
A single global threshold would be silently wrong for two of the three.

### Why Groq, through the OpenAI SDK

Generation here is extraction and faithful summarisation over three short
passages, tightly constrained by the prompt. That is not a task where a frontier
model earns its latency: what the user notices is time-to-first-token, and Groq
is very fast.

The `openai` client is pointed at Groq's OpenAI-compatible endpoint rather than
using the `groq` SDK, so moving to OpenAI, Together, or a local vLLM server is a
change to `GROQ_BASE_URL` and a model name. Using the vendor SDK would have
bought nothing and cost that portability.

### Why SSE, not WebSockets

The stream is one-directional: the server sends sources, then the trace, then
tokens, then a verdict. Nothing flows the other way mid-answer. SSE is plain
HTTP — it survives proxies, needs no separate upgrade path, and the whole client
is the ~40-line reader in [frontend/src/api.ts](frontend/src/api.ts).

The one wrinkle: the browser's `EventSource` can only issue GET requests, and
this endpoint needs a JSON body carrying history and settings. So the response
body is read directly off `fetch` instead. That also makes `AbortController`
work, which is what the Stop button uses to actually stop the server generating
rather than merely hiding the output.

### Why React rather than Streamlit or Gradio

React was the requested stack, and it is also the right one for what this UI has
to do. Streamlit would have been perhaps 150 lines for the chat, but the
inspector — a funnel with proportional bars, six switchable stage tables with
per-row highlighting, and a metrics panel — is layout work that Streamlit
actively resists. Token-level streaming with a working Stop button is awkward
there too, because the whole script re-runs on interaction.

Within React: no state library (one screen, one conversation, props reach
everywhere in two hops), no component library (six components), no Tailwind (the
theme is 40 CSS custom properties and dark mode is one media query).

The markdown renderer is hand-written for a specific reason: `react-markdown`
plus rehype is roughly 100 KB to render bold, lists and inline code, and it
renders **half-arrived markdown badly** — an unclosed `**` mid-stream flickers.
The 90-line renderer in
[frontend/src/components/RichText.tsx](frontend/src/components/RichText.tsx)
degrades gracefully on partial text. It gives up tables and links, which the
model does not emit here.

### Why hand-written evaluation, not RAGAS

RAGAS, TruLens and DeepEval all score RAG systems with an LLM judge —
faithfulness, answer relevance, context precision. Those are useful numbers and
this project uses a judge too, but only for **live, unlabelled** questions
(`--diagnose`).

They are the wrong tool for the core loop. Comparing six chunking
configurations means running the question set six times; with an LLM judge that
is six times the API cost, minutes of latency, and — because judges are
stochastic — a difference between two runs that might be the retriever or might
be the judge. **Retrieval evaluation here calls no LLM at all.** It is
deterministic, it runs in about a second per configuration, and a metric change
is attributable to the change that was made.

Two further deliberate choices:

**Ground truth is at page level, not chunk level.** Chunk ids are content
hashes, so they change whenever the chunk size or strategy changes — chunk-level
labels would make the chunking sweep compare nothing. Pages are stable across
every configuration. A retrieved chunk counts as relevant when its page range
overlaps a labelled page.

**Metrics are reported per stage** (`fused`, `reranked`, `final`), so a chunk
that fusion found and the reranker then discarded shows up as `lost_in_rerank`
instead of disappearing into one aggregate.

### Why pypdf, and what it costs

PyMuPDF is faster and better at layout, but is AGPL-licensed. `pdfplumber` is
better at tables and much slower. `unstructured` and LlamaParse produce the best
output and bring either a heavy dependency tree or an API key.

pypdf is pure Python, has no system dependencies, and was already in the project.

The cost is visible in this corpus: extraction of the policy's key/value tables
produces runs like `the information andDBTR10460060578/01` where a value has
been spliced into a sentence, and the "Bike details" table arrives as an
unpunctuated column of labels. That degraded text is a contributing cause of the
one retrieval failure documented below — the cross-encoder was never trained on
text shaped like that. A layout-aware parser is the first thing to change if
this corpus grows.

---

## Measured results

All numbers from `eval/golden_set.json` — 38 questions over the sample policy,
32 answerable with page-level ground truth and 6 deliberately out of scope.
Reproduce with `python evaluate.py …`; raw JSON is in `eval/results/`.

### What each retrieval stage buys — `sweep-retrieval --k 1`

| configuration | hit@1 | recall@1 | MRR | mean ms |
|---|---|---|---|---|
| dense only, no rerank | 0.750 | 0.573 | 0.750 | 304 |
| BM25 only, no rerank | 0.906 | 0.745 | 0.906 | 0 |
| hybrid RRF, no rerank | 0.875 | 0.693 | 0.875 | 40 |
| **hybrid + cross-encoder** | **0.969** | **0.797** | **0.969** | 1070 |
| hybrid + rerank + MMR | 0.969 | 0.797 | 0.969 | 679 |
| hybrid + rerank + query rewriting | 0.781 | 0.646 | 0.781 | 934 |
| hybrid + rerank + HyDE | 0.969 | 0.797 | 0.969 | 724 |

Reported at **k = 1**. At k = 3 every configuration scores 0.969–1.000: with a
16-chunk corpus, three chunks is a fifth of everything indexed, so hit@3
saturates and stops discriminating. k = 1 is the honest measurement on a corpus
this size. Both are in `eval/results/`.

Two findings worth stating plainly:

- **Query rewriting made retrieval worse** (0.969 → 0.781). It paraphrases
  `TN06BJ2206` and "Section II-1(ii)" into generic wording, and BM25 loses the
  exact token it was keying on. It is implemented, it is off by default, and
  the number is why.
- **HyDE changed nothing** here. The corpus is small and the questions are
  mostly literal lookups — the case HyDE is designed for (vague question, long
  discursive corpus) does not arise.

### Before / after — `compare --k 1`

One change: dense-only + no reranking → hybrid RRF + cross-encoder.

| stage | metric | before | after | delta |
|---|---|---|---|---|
| fused | hit_rate@1 | 0.750 | 0.875 | **+0.125** |
| reranked | hit_rate@1 | 0.750 | 0.969 | **+0.219** |
| final | hit_rate@1 | 0.750 | 0.969 | **+0.219** |
| final | recall@1 | 0.573 | 0.797 | +0.224 |
| final | MRR | 0.750 | 0.969 | +0.219 |

- **Fixed (8):** q05, q09, q16, q18, q24, q29, q31, q32
- **Regressed (1):** q27
- **Still failing:** none

The split between the `fused` and `reranked` rows is the point: fusion alone
buys +0.125, and the cross-encoder buys the other +0.094. Two separate changes,
separately attributed.

### What the change did *not* fix

**q27 — "What is the make and model of the insured vehicle?"** is the one
regression, and its trace explains itself:

```
p7  dense#4  bm25#6   rrf=0.0308  rerank=-6.83  "Persons or Class of Persons entitled to drive…"
p7  dense#7  bm25#3   rrf=0.0308  rerank=-6.90  "Terms, Conditions & Exclusions…"
p8  dense#14 bm25#1   rrf=0.0299  rerank=-8.36  "Bike details / Bike number TN06BJ2206 / Make/Model…"   ← the answer
```

The right chunk is **BM25 rank #1** and fusion would have returned it. The
cross-encoder scores it **−8.36**, below the −8.0 relevance floor, and prefers
two irrelevant page-7 passages. The chunk is a bare key/value table with no
sentence structure — the pypdf extraction artifact described above — which is
not what `ms-marco-MiniLM` was trained on.

Lowering the floor to −12 does fix it, and costs exactly what you would expect:

| floor | hit@3 | out-of-scope questions with surviving context |
|---|---|---|
| −8 (default) | 0.969 | **3 / 6** |
| −12 | 1.000 | 6 / 6 |

The floor is what produces "I don't know". Buying back one question by
disabling it would trade a real refusal guarantee for a cosmetic metric, so the
default stays at −8. The genuine fixes are a layout-aware PDF parser or a
reranker that handles tabular text — `RERANKER=bge` is wired up for exactly that
experiment.

### Chunk size and strategy — `sweep-chunking --k 1`

| strategy / size / overlap | chunks | hit@1 | recall@1 | misses |
|---|---|---|---|---|
| fixed / 150 / 30 | 22 | 0.938 | 0.766 | q24, q27 |
| fixed / 300 / 60 | 11 | 0.938 | 0.766 | q24, q27 |
| recursive / 150 / 30 | 22 | **0.969** | 0.797 | q27 |
| **recursive / 220 / 40** (default) | 16 | **0.969** | 0.797 | q27 |
| recursive / 400 / 80 | 9 | 0.844 | 0.682 | q09, q19, q24, q27, q29 |
| sentence / 220 / 40 | 14 | 0.906 | 0.734 | q09, q18, q27 |

Chunk size matters and the failure mode is legible: at 400 tokens a chunk
swallows several unrelated sections, the single relevant sentence is diluted by
everything around it, and five questions break. Structure-aware splitting beats
a flat token window at every size tried.

### End-to-end with failure labels — `answers --k 3`

| label | count | rate |
|---|---|---|
| ok | 31 | 81.6% |
| correct_refusal | 6 | 15.8% |
| retrieval_failure | 1 | 2.6% |
| generation_failure | 0 | 0.0% |
| missed_refusal (hallucination) | 0 | 0.0% |

All six out-of-scope questions were refused. No answer was invented. The single
failure is q27, and it is a **retrieval** failure — a better LLM would not
touch it.

---

## Layout

| Path | Purpose |
|---|---|
| [rag/config.py](rag/config.py) | Every tunable, and the index signature that invalidates the index when one changes |
| [rag/chunking.py](rag/chunking.py) | fixed / recursive / sentence strategies |
| [rag/embeddings.py](rag/embeddings.py) | MiniLM / BGE / E5 registry with per-model query & passage prefixes |
| [rag/indexing.py](rag/indexing.py) | PDF loading, HNSW configuration, index lifecycle |
| [rag/retrieval.py](rag/retrieval.py) | Dense + BM25, RRF, MMR, metadata filters, the trace |
| [rag/rerankers.py](rag/rerankers.py) | ms-marco / BGE / Cohere behind one interface |
| [rag/query.py](rag/query.py) | Condensation, query rewriting, HyDE |
| [rag/generation.py](rag/generation.py) | Grounded prompt, streaming answers |
| [rag/diagnostics.py](rag/diagnostics.py) | Retrieval vs generation failure separation |
| [rag/evaluation.py](rag/evaluation.py) | hit-rate@k, recall@k, precision@k, MRR, sweeps, before/after |
| [rag/engine.py](rag/engine.py) | `RagEngine` — the facade all three front ends use |
| [rag/llm.py](rag/llm.py) | The shared Groq client |
| [server.py](server.py) | FastAPI: health, SSE chat, reindex, golden set, eval results |
| [main.py](main.py) | CLI |
| [evaluate.py](evaluate.py) | Evaluation CLI |
| [eval/golden_set.json](eval/golden_set.json) | 38 labelled questions |
| [frontend/](frontend/) | React + TypeScript chat UI and retrieval inspector |

---

## Setup

```bash
uv sync                      # or: pip install -r requirements.txt
```

`.env` in the project root:

```env
GROQ_API_KEY=your_groq_api_key_here
```

Put your PDFs in `insurance_docs/`. The first run downloads the embedding model
(~130 MB) and the cross-encoder (~90 MB).

---

## Running the chat UI

Build once, then serve everything from one port:

```bash
cd frontend && npm install && npm run build && cd ..
uvicorn server:app --port 8010
```

Open <http://127.0.0.1:8010>.

Development, with hot reload:

```bash
uvicorn server:app --reload --port 8010     # terminal 1
cd frontend && npm run dev                  # terminal 2 → http://localhost:5173
```

Vite proxies `/api` to 8010; override with `VITE_API_TARGET`.

### What the UI does

- **Streamed answers** with per-chunk source cards showing vector rank, BM25
  rank, RRF score and reranker score.
- **Inspector** (the "Inspect" button, or any answer's *Inspect retrieval*):
  the question at every transform stage, a funnel of how many candidates
  entered and left each stage with timings, a switchable table per stage, and
  the answer — the question / retrieved / answer view side by side.
- **Live controls**: retrieval mode, top-k, reranker, MMR (with λ), query
  rewriting, HyDE, and metadata filters by document and page range.
- **Diagnose** toggle: labels each answer as a retrieval failure, a generation
  failure, a correct refusal or fine.
- **Metrics tab**: whatever `evaluate.py` last wrote, so the numbers above are
  visible next to the thing they describe.
- **Suggested questions** come from the golden set, including an out-of-scope
  one, so the refusal path is one click away.

---

## Running the CLI

```bash
python main.py                            # interactive, hybrid retrieval
python main.py --reindex                  # force a rebuild
python main.py --mode sparse              # BM25 only (also: dense, hybrid)
python main.py --reranker none            # see what fusion alone returns
python main.py --mmr --mmr-lambda 0.5     # diversify the candidate pool
python main.py --rewrite --hyde           # query transforms
python main.py --source policy.pdf --page-min 7 --page-max 8   # metadata filter
python main.py --trace --diagnose --question "What is the deductible?"
```

`--trace` prints the funnel and per-stage scores; `--diagnose` runs the LLM
judge and tells you which kind of failure you are looking at.

---

## Running the evaluator

```bash
python evaluate.py retrieval --k 1                  # current configuration
python evaluate.py sweep-retrieval --k 1            # modes, reranker, MMR
python evaluate.py sweep-retrieval --k 1 --with-transforms
python evaluate.py sweep-retrieval --k 1 --with-bge # adds the BGE reranker arm
python evaluate.py sweep-chunking --k 1             # chunk size & strategy
python evaluate.py answers --k 3                    # end-to-end + failure labels
python evaluate.py compare --k 1 \
    --before eval/results/baseline-k1.json \
    --after  eval/results/current-k1.json
```

Retrieval evaluation calls **no LLM**, so iterating on the retriever costs
nothing but CPU. Every command writes JSON to `eval/results/`.

### What each metric answers, per question

| metric | question it answers |
|---|---|
| hit-rate@k | Did the answer reach the prompt at all? |
| recall@k | How much of the answer reached the prompt? |
| precision@k | How much of the prompt was wasted? |
| MRR | How near the top was it? |

`final` metrics are measured after the relevance floor.

---

## Failure separation

Two failures hide inside "it is sometimes wrong", and they have opposite fixes:

| verdict | meaning | where to fix it |
|---|---|---|
| `retrieval_failure` | the answering passage never reached the prompt | chunking, hybrid, reranking, filters |
| `generation_failure` | right passage in the prompt, answer still wrong | prompt or model |
| `missed_refusal` | not in the corpus, answered anyway | the relevance floor and the prompt |
| `correct_refusal` | not in the corpus, said so | nothing |
| `ok` | right passage, right answer | nothing |

Swapping in a smarter LLM cannot fix a `retrieval_failure`. That is the whole
reason for labelling before changing anything.

Two classifiers: `classify_with_ground_truth` for labelled questions
(deterministic, used by `evaluate.py answers`) and `classify_with_judge` for
live questions (an LLM judge, used by `--diagnose` and the UI). The judge is
asked "was the context sufficient?" and "is the answer grounded?" as two
independent questions — conflating them is exactly the confusion this removes.

---

## Configuration

Everything in [rag/config.py](rag/config.py), overridable by environment
variable. Anything that changes what is *in* the index is folded into
`index_signature()`, so changing it forces a rebuild rather than silently
querying a mismatched index.

| Setting | Default | Effect |
|---|---|---|
| `CHUNK_STRATEGY` | `recursive` | `fixed`, `recursive`, `sentence` |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | 220 / 40 | Tokens. Both invalidate the index |
| `EMBEDDING_MODEL` | `bge-small` | `minilm`, `bge-small`, `bge-base`, `e5-small`, `e5-base` |
| `HNSW_SPACE` | `cosine` | Distance metric |
| `HNSW_EF_CONSTRUCTION` | 200 | Build-time beam. Higher = better graph, slower build |
| `HNSW_EF_SEARCH` | 100 | Query-time beam. Higher = better recall, slower query |
| `HNSW_MAX_NEIGHBORS` | 32 | The `M` of the HNSW paper. Higher = more memory, better recall |
| `DENSE_TOP_K` / `SPARSE_TOP_K` | 20 / 20 | Recall per retriever before fusion |
| `RRF_K` | 60 | Fusion damping; lower favours top-ranked hits more sharply |
| `RERANK_CANDIDATES` | 20 | Reranker shortlist — the latency knob |
| `TOP_K` | 3 | Chunks quoted in the prompt |
| `RERANKER` | `ms-marco` | `none`, `ms-marco`, `bge`, `cohere` |
| `MIN_RERANK_SCORE` | per-model | Relevance floor. Raise it to refuse more often |
| `USE_MMR` / `MMR_LAMBDA` | off / 0.7 | Diversity; λ=1 is pure relevance |
| `USE_QUERY_REWRITE` | off | Off because it measured worse — see above |
| `USE_HYDE` | off | Neutral on this corpus |
| `LLM_MODEL` | `llama-3.3-70b-versatile` | Final answer model |
| `UTILITY_MODEL` | `llama-3.1-8b-instant` | Query transforms and the judge |
| `COHERE_API_KEY` | — | Enables `RERANKER=cohere` |

---

## API

| Endpoint | Description |
|---|---|
| `GET /api/health` | Readiness, chunk count, models, sources, page range, defaults |
| `POST /api/chat` | `{question, history, mode, top_k, reranker, use_mmr, use_rewrite, use_hyde, diagnose, filters}` → SSE |
| `POST /api/reindex` | Rebuild the vector and BM25 indexes |
| `GET /api/golden-set` | The evaluation questions, for one-click probes |
| `GET /api/eval-results` | Whatever `evaluate.py` last wrote |

`/api/chat` emits `sources`, then `trace`, then `token`… then optionally
`diagnosis`, then `done` — so citations and the funnel render while the answer
is still being written.

---

## Known limits

- **The corpus is one 8-page PDF.** hit@3 saturates on it; k=1 is reported for
  that reason. On a larger corpus the k=3 numbers would separate again.
- **BM25 is in-memory and rebuilt at startup**, and scoring is linear in corpus
  size. Correct at thousands of chunks, wrong at millions.
- **pypdf mangles table layout** (see the design notes), which is a contributing
  cause of the one remaining retrieval failure.
- **Ground truth is page-level**, so a chunk spanning pages 3–4 counts as
  relevant for either. That is deliberate but coarser than span-level labelling.
- **`answer_contains` anchors are identifiers and figures only.** For questions
  with no such anchor, only a refusal counts as a generation failure, so
  `generation_failure` is undercounted by construction.
- **The LLM judge is a small model.** It is a triage aid for live questions, not
  a substitute for the labelled set.
