# The AI Engineering League — 120 Review Questions (10 per week)

Source syllabus: https://pugazhendhi-ss.github.io/ai-syllabus (12 weeks, 6 modules, 6 gates). Week titles, topics and key
terms below are taken from that page. Questions marked **[Project]** are about *this* repo (insurance-claims RAG →
claims agent → MCP → production → capstone) and have answers you can check against the code and write-ups.
Each question has a short *Look for* line: what a good answer must contain.

| Module | Weeks | Theme |
|---|---|---|
| M1 Foundations | 1–2 | How models work; prompting, structured output, tool calling |
| M2 Retrieval & RAG | 3–4 | RAG from parts; debugging retrieval |
| M3 Evals & Error Analysis (the core) | 5–6 | Reading traces; measuring change |
| M4 Agents | 7–8 | Agent loops; failure modes, trajectory evals |
| M5 MCP, Multi-agent & A2A | 9–10 | MCP; multi-agent with evidence |
| M6 Production & Capstone | 11–12 | Observability, cost, failure→test loop; ship and defend |

---

## Week 1 — How a Language Model Actually Works

**1.** In one plain sentence, what does a language model do — and why is that the *only* thing it does, whether it is summarising a claim, translating, or writing code?
*Look for:* next-token prediction repeated; no per-task sub-model or router.

**2.** Why is "a token is a word" wrong? Give two kinds of text where the gap is large and say what it does to cost.
*Look for:* sub-word chunks; code/JSON/non-English use more tokens per meaning; you pay per token.

**3.** Write the cost formula for one request and explain why output tokens usually dominate the bill. **[Project]** Our triage agent used ~7,500 input+output tokens per claim at $0.075/$0.30 per million — roughly what does one claim cost?
*Look for:* (in×$in + out×$out)/1e6; output 3–5× pricier; ≈ $0.0006.

**4.** What does temperature change, and why does temperature 0 still *not* guarantee identical outputs?
*Look for:* rescales distribution before sampling; greedy ≠ deterministic (batching, hardware, model updates).

**5.** Explain greedy decoding vs sampling (top-p, top-k). Which would you pick for extracting a claim number from a note, and which for drafting an adjuster email?
*Look for:* extraction/classification → low/0; drafting → moderate.

**6.** What is an embedding, and why can a computer compare "dimpled shingles" with "cosmetic roof damage" using it when keyword matching cannot?
*Look for:* text → vector; closeness = similarity of meaning; keyword match needs shared words.

**7.** Static embeddings (Word2Vec/GloVe) vs contextual embeddings: what is the difference, and why does it matter for the word "claim"?
*Look for:* one vector per word vs vector depends on surrounding words; polysemy.

**8.** Decoder-only vs encoder models: which generates text and which is typically used to embed or rerank? Name one example family of each role.
*Look for:* GPT/Claude/LLaMA generate; BERT-style/bge/cross-encoders encode.

**9.** Why does a model state a wrong answer confidently? What is a hallucination, and why is "sounding right" different from "being right"?
*Look for:* guessing likely continuations, not looking facts up; no internal truth check.

**10.** You must pick a model for (a) classifying 50,000 notes a day and (b) one hard coverage question a week. Which factors drive each choice (cost, latency, context, capability), and how would you decide with evidence rather than reputation?
*Look for:* small/cheap for volume, strong for rare hard cases; test on your own data.

---

## Week 2 — Prompting, Structured Output & Tool Calling

**11.** Name the parts of a good prompt (role, task, context, format, examples). Why do a few good examples often beat a long instruction block?
*Look for:* prompt anatomy; few-shot shows the pattern the model should copy.

**12.** Zero-shot vs few-shot vs Chain-of-Thought: when does each help, and when does CoT just add cost?
*Look for:* CoT helps multi-step reasoning; wasteful on simple extraction.

**13.** What is self-consistency, and what does it cost? When is task decomposition a better answer than a bigger prompt?
*Look for:* sample several, take the majority; N× cost; split a big job into verifiable steps.

**14.** Why is free-text output a problem for an application? Show the minimum you would put in a JSON schema to extract `claim_number`, `loss_date` and `status` reliably.
*Look for:* unparseable/untrustworthy; typed fields, enums, required keys.

**15.** What do Pydantic and the `instructor` library add on top of "please reply in JSON"? Describe the validate-and-retry loop and its stop condition.
*Look for:* schema validation, error fed back to the model, bounded retries.

**16.** In tool calling, who actually executes the tool — the model or your code? Explain what the model returns, and what your code must do before trusting it.
*Look for:* model emits a call (name+args); your code validates and runs; model never runs anything.

**17.** What are parallel tool calls and when are they safe? **[Project]** Our capstone prompt tells the model to call the wording search and the limits lookup "in the same turn" but to wait for the in-force check first — why that ordering?
*Look for:* independent calls batch; gating dependency (don't search wording for a lapsed policy).

**18.** Define a guardrail. Give one input guardrail and one output guardrail you would put on a claims assistant, and say how each fails safely.
*Look for:* refuse/validate rather than invent; e.g. reject out-of-scope input, block decision language.

**19.** What is prompt injection, and why can't a "don't follow instructions in the document" line fully fix it?
*Look for:* instructions and data share one channel; defences are structural (least privilege, validation).

**20.** Gate M1 asks for "structured output + tool call + guardrail + 3 diagnosed failures". How do you keep the API key out of code, and what makes a failure "diagnosed" rather than merely observed?
*Look for:* env/.env not committed; a failure with a cause and evidence (input, output, why).

---

## Week 3 — Retrieval-Augmented Generation, From Parts

**21.** What problem does RAG solve that a bigger model does not? When would long-context stuffing beat RAG, and what arithmetic decides it?
*Look for:* grounding in private/changing docs; token-cost × calls vs retrieval cost.

**22.** Walk through the pipeline in order: load → chunk → embed → store → retrieve → generate. **[Project]** Which of those steps run locally in this repo, and which one leaves the machine?
*Look for:* embed/rerank local (bge-small, cross-encoder); only the Groq generation call leaves.

**23.** Chunk size and overlap: what breaks when chunks are too small, and what breaks when they are too large?
*Look for:* small loses context; large dilutes the embedding and wastes prompt budget.

**24.** **[Project]** Why does a fixed or recursive chunker orphan an exclusion code like `E-17` from its form number, and how does the structure-aware chunker prevent that?
*Look for:* tables have no blank lines so a token window cuts mid-table; structure splitting stamps form/edition/clause banner on every chunk.

**25.** Bi-encoder vs cross-encoder: which is used to retrieve, which to rerank, and why not use the cross-encoder on the whole corpus?
*Look for:* independent vectors, fast, ANN-searchable vs joint scoring, accurate but O(N).

**26.** What does HNSW do, and what is the trade-off in its recall knobs? **[Project]** Why does changing `HNSW_EF_SEARCH` on an existing index change nothing until you rebuild?
*Look for:* graph-based ANN, speed vs recall; those params are set at collection creation, not in the index signature.

**27.** What is metadata filtering, and why is *pre*-filtering inside each retriever better than post-filtering the top-K?
*Look for:* post-filter can leave you with fewer than K with no signal; pre-filter fills slots from allowed docs.

**28.** What is the "asymmetric embedding" trap with `bge`/`e5` models? What silently happens if you skip the query instruction or prefix?
*Look for:* queries need prefix/instruction, passages don't (or `query:`/`passage:`); no error, just worse vectors.

**29.** How do you make an answer *cited or refused*? Describe what must be true of a citation for it to be checkable, and what the app must do when nothing relevant is retrieved.
*Look for:* citation resolves to one stored chunk by id; relevance floor → "I don't know".

**30.** **[Project]** The relevance floor is −8.0. Lowering it fixes one retrieval miss but lets junk through for out-of-scope questions. Explain why the default stays, and why a `correct_refusal` counts as a pass.
*Look for:* the floor is what produces "I don't know"; trade measured (3 vs 6 junk survivors); refusing out-of-scope is correct behaviour.

---

## Week 4 — Debugging Retrieval: Hybrid, Reranking & Failure Separation

**31.** State the R/G rule: how do you tell a retrieval failure from a generation failure for one wrong answer, and why do they need different fixes?
*Look for:* right chunk absent from context → retrieval; present but misused → generation.

**32.** **[Project]** Why can a retrieval failure *never* be fixed by a better prompt or model? Use the Week 11 `c11` case as the example.
*Look for:* model can't use what it was never shown; E-34/E-36 absent from context.

**33.** What is BM25 and what does it catch that dense retrieval misses? Give an insurance example.
*Look for:* exact tokens — codes (`E-17`), IDs, names, form numbers.

**34.** Explain Reciprocal Rank Fusion: the formula's shape, why it needs no score normalisation, and what `RRF_K` does.
*Look for:* Σ 1/(k+rank); ranks not scores; k dampens top-rank dominance.

**35.** Why rerank with a cross-encoder after fusion? What does it cost in latency, and what does `RERANK_CANDIDATES` trade?
*Look for:* joint query-passage scoring is more accurate; cost grows with candidates.

**36.** What problem does MMR solve, and why is it off by default here? **[Project]** What did query rewriting do to hit@1 (0.969 → 0.781) and why?
*Look for:* diversity vs relevance; rewriting paraphrased exact tokens (`TN06BJ2206`) and BM25 lost the key.

**37.** What is HyDE and when might it help? **[Project]** It changed nothing on this corpus — what does that teach about "obvious improvements"?
*Look for:* hypothetical answer as query; measure before enabling.

**38.** Define hit-rate@k, recall@k and MRR. Which would you report for "did the right chunk show up in the top 3?"
*Look for:* hit@k = any relevant in top k; recall = fraction found; MRR = 1/rank of first.

**39.** Why must you change *one thing* at a time and report a before/after number? **[Project]** Which command gives that number without calling an LLM?
*Look for:* attribution; `python evaluate.py retrieval --k 1` / `compare`.

**40.** Gate M2 wants "1 retrieval + 1 generation failure, each with evidence". What is the evidence for each, and what should you also report about what your change did **not** fix?
*Look for:* inspection view showing question/retrieved/answer; honest residual failures.

---

## Week 5 — Error Analysis: Reading Traces Like a Professional

**41.** What makes a trace "complete" enough to replay an answer 18 months later? List the fields.
*Look for:* prompt version, model + params, retrieved chunk ids and scores, raw output, citations.

**42.** Why is random sampling required, and what bias does cherry-picking introduce? How big a sample does the syllabus ask for?
*Look for:* representative failure rates; 30+ traces read.

**43.** What is open coding? Why write the one-sentence failure note *before* choosing categories?
*Look for:* categories emerge from evidence, not pre-imposed.

**44.** How do you turn notes into an error taxonomy that a stranger could apply? What makes a mode name good?
*Look for:* 4–7 named modes, defined, mutually distinguishable.

**45.** Rank modes by frequency × severity. Why can a rare mode outrank a common one? **[Project]** Which insurance failure is "rare but critical"?
*Look for:* severity weighting; citing the wrong edition / stating a decision.

**46.** What is the difference between a public benchmark (MMLU, HumanEval) and an eval of *your* app? Why doesn't a high benchmark score tell you your app works?
*Look for:* different distribution and failure modes; your users' questions.

**47.** Why write a prediction before attacking the top mode? **[Project]** What was the Week 5 prediction and how was it checked in Week 7?
*Look for:* falsifiable expectation; `prediction.txt`, `w7_retrieval_delta`.

**48.** **[Project]** The first traffic run produced 82 traces of which 65 were "Error code: 429". What does this teach about trace corpora, and what changed in `rag/llm.py`?
*Look for:* outage looks like bad answers; retry honouring the stated wait; raise instead of returning an error as content.

**49.** Redaction: why "redact on write, not later"? Explain how `TraceWriter` enforces it and why claim numbers are pseudonymised rather than blanked.
*Look for:* identifier already on disk otherwise; verify-or-refuse; shape-preserving HMAC surrogate keeps linkability and format assertions.

**50.** How does a trace make "retrieval vs generation" checkable for a specific failure, and how do you pick the fix target and record the expected effect?
*Look for:* per-stage scores/ids; target = highest frequency × severity with written expected change.

---

## Week 6 — Evals: Measuring Whether a Change Actually Helped

**51.** What is a regression test built from a failure, and why must a new failure become a test *before* the fix?
*Look for:* "a test that has only ever been green has not been tested".

**52.** "Assert before you judge": what can a rule check for free, and what is left for an LLM judge? Give three assertions for a claim summary.
*Look for:* source present, claim number format, exclusion code present, refusal when expected.

**53.** Why is a binary judge better than a 1–10 score? **[Project]** What single criterion does the Week 6 judge decide?
*Look for:* models/humans can't separate 6 from 7; `coverage_faithful`.

**54.** What is judge agreement and why must it be measured against labels written *before* the judge runs? **[Project]** What agreement did the Week 6 judge get, and does it clear the 85% bar?
*Look for:* otherwise it's a number generator; 80% (20/25) — it does not.

**55.** **[Project]** In the Week 12 integration the judge scored 76% first, then 84% with reasoning off, then 68% after "improving" it. What is wrong with quoting 84%, and what does it teach about tuning on the test set?
*Look for:* chosen after seeing all variants on the same 25 labels; report first measurement and spread.

**56.** Explain RAGAS faithfulness, answer relevancy, context precision and context recall in one line each. Which two are retrieval metrics?
*Look for:* faithfulness = answer supported by context; relevancy = answers the question; precision/recall = retrieval quality.

**57.** What is G-Eval, and what failure modes does an LLM judge have (verbosity, self-preference, leniency/strictness)?
*Look for:* rubric-based scoring; judge bias and position effects.

**58.** What is a before/after delta *per problem type*, and why does an overall average hide regressions? **[Project]** Which numbers does the capstone say the panel will ask for?
*Look for:* per-mode pass rate; exclusion cases specifically.

**59.** **[Project]** Why does the eval suite require *all* trials of a case to pass? What would "best of N" hide?
*Look for:* sampled model can pass once by luck; pass^N exposes flakiness.

**60.** Gate M3 requires "validated taxonomy + validated eval set + measured delta". What does *validated* mean for each of the three?
*Look for:* taxonomy applied consistently by someone else; eval cases labelled and judge agreement checked; delta with n and judge agreement.

---

## Week 7 — Agent Loops — and When Not to Use Them

**61.** Describe the agent loop (plan → act → observe → repeat). What does ReAct add, and where does your code, not the model, stay in control?
*Look for:* reasoning interleaved with actions; code executes tools and enforces limits.

**62.** **[Project]** Name the three tools of the Week 7 claims agent and the one-job-each rule for tool descriptions. Why did the first draft of `compute_payout` fail?
*Look for:* `get_claim`, `search_policy`, `compute_payout`; it did two jobs, free-string status, overlapped other tools.

**63.** List the four budgets enforced before the next model call and explain why they are stop conditions, not errors.
*Look for:* iterations, tokens, cost, wall-clock; return `budget_exceeded` outcome.

**64.** What is a workflow and when does it beat an agent? Give the decision rule you would apply to a claims task.
*Look for:* fixed, known steps → workflow (cheaper, faster, predictable); open-ended branching → agent.

**65.** **[Project]** In the Week 7 race the workflow was ~5× cheaper. Name one claim where the agent won and one where the workflow won, and say why.
*Look for:* c04 (redirect between forms) needs a read-then-decide dependency; c03/c07 fixed rules.

**66.** What is a "dependency" claim (c04, c06, c08)? Why can a hard-coded branch not cover it?
*Look for:* step 3 depends on the specific result of step 2.

**67.** Short-term vs long-term agent memory: summarisation vs vector memory (mem0). When is memory the wrong answer?
*Look for:* context compression vs retrieval of past facts; adds cost and staleness.

**68.** **[Project]** The final payout number comes from `compute_payout`, not the model's JSON. Why is that authoritative, and what bug class does it remove?
*Look for:* arithmetic by code; model free-hand numbers drift.

**69.** Why does the agent need every step logged, and what would you look for in a transcript of a bad run?
*Look for:* wrong tool, repeated calls, missing required step.

**70.** Which would you ship — agent or workflow — for a 10-claim day, and what numbers (pass rate, p50/p99 latency, tokens, cost) would you cite?
*Look for:* evidence-based verdict, including p99 not just p50.

---

## Week 8 — Agent Failure Modes & Trajectory Evals

**71.** Name five agent failure modes (loops, wrong tool, invented arguments, quiet give-up, …) and how each shows in a trace.
*Look for:* concrete signatures per mode.

**72.** What is trajectory evaluation and what is tool-choice accuracy? How do you define an "expected" path?
*Look for:* judge the path, not just the answer; per-call correctness vs expected tool sequence.

**73.** Define the outcome-vs-trajectory gap. **[Project]** In Week 12 outcome pass was 80% and trajectory pass 96% — what does a gap in that direction mean?
*Look for:* right path, wrong answer — trajectory alone would overstate quality.

**74.** Why is "right answer via wrong path" a time bomb? Give a claims example (decided from notes without searching the policy).
*Look for:* works by luck; breaks when the shortcut stops working.

**75.** **[Project]** Name the Week 8 trajectory modes `premature_termination`, `missing_required_form`, `hallucinated_argument`, `redundant_call`. Which are wrong and which are merely wasteful?
*Look for:* first three wrong; redundant is cost, not correctness.

**76.** Why report cost per task as mean *and* p99? **[Project]** What caused the 4,577 s p99 in Week 10?
*Look for:* tail stalls; a rate-limit wait, not architecture.

**77.** Direct vs indirect prompt injection: define both and give an insurance example of the indirect kind.
*Look for:* instruction hidden in an adjuster note/PDF the agent reads.

**78.** What is least privilege per tool and why does it matter more than a "don't obey documents" instruction? **[Project]** How did the Week 9 claims server's description of adjuster notes ("nothing sanitizes them") raise the risk?
*Look for:* limit what a hijacked agent can do; unsanitised free text is an injection channel.

**79.** Why validate tool *outputs* and arguments, and what does OWASP LLM Top 10 add as a checklist?
*Look for:* both directions untrusted; known risk catalogue.

**80.** Gate M4: "measured failure reduction". What makes a before/after on your *worst* failure convincing, and what do you say can still get through?
*Look for:* same cases before/after with n; honest residual risk.

---

## Week 9 — MCP: the Standard Way Agents Reach Tools & Data

**81.** What is MCP, and what integration problem does it solve compared with hard-wiring tools into your agent?
*Look for:* standard socket; write a tool once, any client uses it.

**82.** Define host, client and server. **[Project]** Where does the model actually run, and does an MCP server ever call a model?
*Look for:* model runs in the host/agent loop; servers never import an LLM client.

**83.** Tools vs resources vs prompts: who decides when each is used? **[Project]** Why was the exclusions schedule exposed as a resource rather than a tool?
*Look for:* model-invoked vs app-attached context vs user templates; context shouldn't cost a turn.

**84.** Compare stdio and HTTP transports. **[Project]** What breaks if a stdio server prints to stdout during a handler?
*Look for:* stdout is the JSON-RPC channel; stray prints corrupt the stream.

**85.** Walk through `initialize` → `tools/list` → `tools/call`. What does `tools/list` return and why does discovery matter?
*Look for:* names, descriptions, input schemas; agent has no hard-coded tool.

**86.** **[Project]** How was the claims-system server bolted on "by config alone"? What did the diff of the agent file show?
*Look for:* only the MCP config changed; zero diff in agent code.

**87.** What is a recoverable error and why is a tool description "a prompt"? Show a before/after for an unknown form number.
*Look for:* error names valid values; description says when to call it.

**88.** **[Project]** In the capstone the `loss_date` argument is required with no default. Why is a missing date an error rather than a "latest wording" fallback?
*Look for:* silent default reproduces the 2024-loss-vs-2025-wording failure.

**89.** MCP security: access control, remote auth, and vetting a third-party server. What would you check before trusting someone else's tool?
*Look for:* scopes, least privilege, tool descriptions as injection surface, what it returns.

**90.** **[Project]** Propagating a trace id over the MCP hop: why `params._meta` rather than a tool argument? What did the server write and what must it never log?
*Look for:* out-of-band metadata, hidden from the model; trace id, tool, latency — not arguments or results (PII).

---

## Week 10 — Multi-Agent & A2A — With Evidence, Not Fashion

**91.** Describe orchestrator–worker. What is a specialist agent and why should its tool set be narrow?
*Look for:* manager splits and delegates; focused job, fewer tools, less confusion.

**92.** What is the context re-send multiplier? Why can multi-agent cost more than a single agent for the same task?
*Look for:* every hand-off re-sends context; tokens × hops.

**93.** **[Project]** The Week 10 orchestrator cost 0.9× the single agent, not more. What design choice avoided the usual tax, and which hand-off still dominated (84%)?
*Look for:* worker gets distilled notes, not raw notes; the multi-lap search loop is the real cost.

**94.** How do you race a team against a single agent *fairly*? List what must be identical.
*Look for:* same test set, judge, model, budgets; same metrics.

**95.** The four comparison metrics are quality, latency, tokens and cost. Why report all four, and what verdict rule do you apply when quality ties?
*Look for:* tie → cheaper/faster wins; avoid quality-only.

**96.** **[Project]** Pass rate tied 7/10 but on *different* claims. What does a disjoint-failure tie tell you about each system?
*Look for:* complementary weaknesses; not interchangeable.

**97.** When is multi-agent genuinely worth it, and when is it fashion? Name conditions (parallelisable subtasks, context isolation, different permissions).
*Look for:* evidence-based criteria.

**98.** What is A2A? Describe the AgentCard and the task lifecycle states.
*Look for:* agent-to-agent standard; capability card; submitted → working → completed/failed.

**99.** MCP vs A2A: one line each on what they connect, and an example where you would need both.
*Look for:* MCP = agent↔tools/data; A2A = agent↔agent.

**100.** **[Project]** The notes-summary worker never gives the exclusions worker the raw adjuster notes. Why is that both a cost control and a privacy/safety control?
*Look for:* fewer tokens, less PII, smaller injection surface.

---

## Week 11 — Production: Observability, Cost & the Failure→Test Loop

**101.** What must be logged per request so any answer can be found and replayed? **[Project]** Which fields did the Week 11 request log add?
*Look for:* trace id, ts, user, prompt version/hash, retrieval version, spans, context ids, output.

**102.** Trace vs span: define both and say why spans carry stage, latency, tokens and cost. Name a tool that implements this (LangSmith/Phoenix/OpenTelemetry).
*Look for:* one request = trace, steps = spans; per-step attribution.

**103.** The support drill: you get "something was covered that the policy excludes, sometime yesterday". List the slices you would try and in what order.
*Look for:* time, user, prompt version, input type, cost outlier, output text.

**104.** **[Project]** The drill was found in 01:47 by time × output text. Which logged field made it quick, and what was honestly wrong with how that time was obtained?
*Look for:* indexed `coverage_status` + context ids; same agent planted and found; not squadmate-timed.

**105.** **[Project]** Why do you log the retrieved context ids? What question does it turn from a two-day mystery into one hop?
*Look for:* retrieval missed vs model ignored.

**106.** Why store a hash and length of the adjuster note instead of the note? Where does PII redaction belong, and why not "clean it later"?
*Look for:* cheapest control is not having the field; redact on write, verify.

**107.** **[Project]** Cost-by-stage: why did "retrieval costs $0" mislead, and how does attributing tokens to the stage that caused them change what you optimise?
*Look for:* results re-sent every lap; ~29% attributable to retrieval; fixed prompt re-sent per lap is largest.

**108.** Compare prompt caching, semantic caching, model routing/fallbacks. Which is usually the first, cheapest lever and why?
*Look for:* prompt caching: one config line; semantic cache risks stale/wrong hits.

**109.** **[Project]** At 10× volume what breaks first, and what number proves it? Explain why free-tier rate limits and p99 latency are the same problem.
*Look for:* TPD 200k ≈ 26 claims/day vs 600; 429 waits show up as latency.

**110.** **[Project]** `c11` went 0/5 → 1/1 only after *two* fixes (retrieval then prompt). Why did the first fix leave the case red, and why isn't 1/1 yet a closed loop? Write the two-line canary and rollback plan.
*Look for:* second, generation cause exposed; rest of suite unrun; canary % + metric alarms; version flag rollback.

---

## Week 12 — Capstone: Ship It and Defend It

**111.** What does "one entry point, one command, one trace id" require of the integration? **[Project]** Where is the trace id minted and how does it survive both hops?
*Look for:* `TriageSession.run`; `_meta.trace_id` to MCP; server spans returned and logged.

**112.** **[Project]** Why is the date filter enforced in code (form + edition pair, post-checked) instead of in the prompt? What does the post-check catch?
*Look for:* retrieval ranks relevance not edition; independent filter sets can leak pairs.

**113.** **[Project]** Explain the half-open edition ranges `[from, to)`. Which loss date belongs to which edition for HO-0850 around 1 April 2025?
*Look for:* 31 Mar → 07-23; 1 Apr → 04-25.

**114.** **[Project]** The system must never state a coverage decision. Why is a prompt instruction insufficient, how does the guard enforce it, and what are its two known failure modes?
*Look for:* code check on model-authored prose; 76% rewrite rate and false positives; missed hedged outcomes ("may apply").

**115.** **[Project]** Deductible, sub-limit and policy limit are three numbers. Where does each come from in this system and why must the model never read them from wording text?
*Look for:* limits lookup by edition; policy limit from the policy; model copy errors / confusion.

**116.** **[Project]** The pre-2025 (straddle) cases scored 5/9 while no request cited a stale edition. What failed, and what logged evidence separates retrieval from model blame in `w02` vs `w12`?
*Look for:* ungrounded clause 2.1 (coverage-basis chunk crowded out) vs E-65 retrieved but not cited.

**117.** **[Project]** Which error-taxonomy mode did integration *create* (not inherit), and how was it fixed generically?
*Look for:* redundant FNOL re-fetch 25/25; cache identical (tool, args) calls.

**118.** **[Project]** What does `replay` prove and what does it explicitly not prove? How do you answer a regulator asking about a decision 18 months ago?
*Look for:* same editions/chunk ids/text hash/prompt hash/model id; not the same sentences; logged output is the record.

**119.** **[Project]** The date filter cost 0.0 points of hit-rate@3 on non-straddle cases. Why is that a statement about the corpus rather than evidence the filter is free, and what does the suite *not* measure?
*Look for:* 36 chunks, answers in in-force editions by construction; no load, no variance, no real wordings, PII only for known literals.

**120.** Prepare your 10-minute four-part demo for this project: what is the real run, the real failure, the number that moved, and what's next — and answer the hostile question "it said covered and we paid out; show me the assertion, not the prompt".
*Look for:* Part 1–4 per brief; `no_decision_language` + guard code, honest rewrite stats.

---

### Notes on this file
- Syllabus coverage per week follows the site's topics and key terms (Week 1 tokens/temperature/embeddings/hallucination … Week 12 integration, fresh-eyes test, four-part demo).
- [Project] questions reference artifacts in this repo: `results_week*.md`, `eval/w*/`, `README_W12.md`, `tools/w*`.
