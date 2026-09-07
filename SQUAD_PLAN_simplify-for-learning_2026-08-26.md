# SQUAD PLAN
**Task:** Make the application as simple as possible for learning, without losing any W3–W6 syllabus topic. Everywhere something is used, comment why we chose it over the alternative; for every number in config, explain why that number.
**Date:** 2026-08-26
**Status:** AWAITING APPROVAL
**Mode:** MIXED (sequential spine, one parallel pair)
**Base Commit:** 933d926

---

## Strategic Direction

Six weeks of coursework accreted into 13,622 lines of Python: `rag/` is 18 modules
(`retrieval.py` alone is 1,005 lines), `tools/` is 19 single-use week scripts that each
re-implement the same load-engine / loop / report shape. Every syllabus concept is present
and correct — the problem is that it is unreadable as a teaching artifact. We compress
*volume* while keeping every *concept* citable at file:line, and annotate each decision with
the alternative it beat. The binding constraint is that no graded number may move:
`evaluate.py retrieval --k 1` is the contract, captured before any edit.

---

## GOAL (this squad is goal-shaped)

```
A.  python evaluate.py retrieval --k 1
    Frozen baseline at 933d926:
      hit@1 0.844   recall@1 0.844   prec@1 0.844   mrr 0.844
      Missed entirely : ['q05','q09','q13','q26','q27']
      Lost in rerank  : none
      Out-of-scope questions with surviving context: 5/6
      Index: 24523 chunks, 8 documents
    PASS = all of the above identical after the refactor.
    The `ms` column is wall-clock and is EXCLUDED from the identity check.

B.  python -c "import rag, main, server, evaluate"
    cd frontend && npx tsc -b --noEmit && npm run build
    PASS = clean import of all three front ends; zero new TS errors; build succeeds.

C.  Every command cited in README.md, CLAUDE.md, AGENTS.md, results.md,
    results_week4.md, results_week5.md, results_week6.md, notes.md and taxonomy.md
    resolves to an entry point that exists.
    PASS = zero commands referencing a deleted/moved file or function.

D.  Syllabus Coverage Audit workflow reports 0 LOST topics.
    PASS = every W3-W6 requirement citable at file:line in the new tree.

Stop and escalate with partial delivery after 8 total agent loops.
The Verifier re-runs A, B and C itself. Worker claims never satisfy the GOAL.
```

---

## Execution Overview
| Field | Value |
|-------|-------|
| Total Workers | 6 (Workers 4a/4b run as one parallel pair = one loop) |
| Global Loop Cap | 8 total agent loops max before escalation |
| Est. Handoff Size per Worker | ~1,000–2,000 tokens |
| Irreversible Actions Present | NO |
| Untrusted External Content | NO |

**Hard no-touch list** (violating any of these fails the lane outright):
- `eval/labels_25.json`, `eval/judge_v0/v1/v2.txt`, `prediction.txt`, `w6_prediction.txt`
  — W6 scores 25 points on these provably predating the judge run. No move, no rewrite,
  no reformat. Git history is the evidence.
- `traces/claims_traces.jsonl`, `eval/w5/`, `eval/w6/` — the sampled population behind
  the W5 taxonomy frequencies and the W6 agreement numbers.
- `results.md`, `results_week4.md`, `results_week5.md`, `results_week6.md`, `notes.md`,
  `taxonomy.md` — graded write-ups. Read-only to every worker except Worker 5, which may
  only APPEND a path-change note if a command in them moved.
- `eval/golden_set.json`, `eval/golden_set.jsonl`, `eval/endorsements_golden.json`,
  `eval/w6_cases.json` — the regression corpora. Editing a label to move a number is the
  single worst outcome available here.
- No git mutations by any worker. Delivery ends at a report; branch/commit is the user's.

---

## Worker Breakdown

### Worker 1 — Baseline & Contract Freeze
| Field | Detail |
|-------|--------|
| Persona | Release engineer establishing a regression contract |
| Scope | Capture GOAL A/B/C on the untouched tree; inventory every documented command and every public symbol crossing a module boundary |
| Tools | bash, read, write |
| Agent Type | general-purpose |
| Depends On | none |
| Execution | SEQUENTIAL (blocks all others) |
| Reversible | YES — writes only new files |
| Touches Untrusted Content | NO |

GOAL A is already captured (see above). This worker captures B and C, and produces the
**import surface map**: for each `rag/` module, which symbols are imported by which other
module / front end / tools script. Workers 2 and 3 refactor against this map; anything not
on it is internal and free to move.

**Definition of Done:**
- [ ] `SQUAD_BASELINE.md` records GOAL A verbatim, GOAL B output, and the GOAL C command inventory as a table (command → file it resolves to → cited in which doc)
- [ ] Import surface map saved as `SQUAD_BASELINE_imports.md`: every cross-module symbol, with its importers
- [ ] GOAL B run and its exact output pasted, not summarised
- [ ] Zero files modified outside the two new `SQUAD_BASELINE*` files

**Output Contract:**
- Delivers: baseline file paths + the count of documented commands + the list of `rag/` symbols with 2+ external importers (the "cannot move without updating N call sites" set)
- Format: two markdown files + a ≤40-line summary
- Next worker needs: the import surface map path and the frozen GOAL A numbers

---

### Worker 2 — rag/ decomposition (pure moves, zero logic change)
| Field | Detail |
|-------|--------|
| Persona | Senior Python engineer doing a mechanical, provable refactor |
| Scope | Split the oversized `rag/` modules along their existing seams. Move code; do not rewrite it. |
| Tools | read, edit, write, bash |
| Agent Type | general-purpose |
| Depends On | Worker 1 |
| Execution | SEQUENTIAL |
| Reversible | YES |
| Touches Untrusted Content | NO |

Target seams, taken from the actual file outline rather than invented:

- `rag/retrieval.py` (1,005 lines) splits into:
  - `rag/fusion.py` — `mmr_order` + the RRF fusion block (the W4 "one change" and the W4
    bonus live here; keeping them in one small file is the point)
  - `rag/filters.py` — `build_where`, `matches_filters` (the W3 metadata-filter requirement)
  - `rag/chunk_types.py` — `RetrievedChunk`, `_Record`, `format_pages`, `provenance_of`, `tokenize`
  - `rag/trace_record.py` — `RetrievalTrace`
  - `rag/retrieval.py` keeps only `HybridRetriever` and re-exports the moved names so no
    existing import breaks.
- `rag/chunking.py` (708) and `rag/indexing.py` (694): split **only if a clean seam exists**;
  a forced split is worse than a long file. Report the decision either way.

**Rules that make this provable rather than hopeful:**
- Not one arithmetic expression, threshold, sort key or comparison operator changes. A diff
  hunk that is not a pure move must be justified line by line in the handoff.
- `rag/retrieval.py` re-exports every symbol it lost, so Worker 3 and the front ends keep working.
- GOAL A is re-run by this worker and must be identical on the four metrics, the five
  missed ids, the rerank line, the out-of-scope count and the 24,523 chunk count.

**Definition of Done:**
- [ ] GOAL A re-run, output pasted, identical to the frozen baseline on every field except `ms`
- [ ] GOAL B re-run, clean
- [ ] `git diff --stat` shows moves, and the handoff justifies every non-move hunk individually
- [ ] No file in the hard no-touch list is modified (`git status` pasted as proof)
- [ ] No new file exceeds ~350 lines

**Output Contract:**
- Delivers: new module list with line counts, before/after GOAL A, any seam declined and why
- Format: file list + pasted eval output
- Next worker needs: the new `rag/` module map and the re-export list

---

### Worker 3 — tools/ consolidation behind one dispatcher
| Field | Detail |
|-------|--------|
| Persona | Developer-experience engineer collapsing 19 one-off scripts |
| Scope | One `weeks.py` entry point; shared scaffolding extracted; every existing week command still reachable |
| Tools | read, edit, write, bash |
| Agent Type | general-purpose |
| Depends On | Worker 2 |
| Execution | SEQUENTIAL |
| Reversible | YES |
| Touches Untrusted Content | NO |

The 19 scripts fall into four honest groups, and only the first is really duplicated:

- **runners** (`run_task_d`, `run_week4`, `run_w6`, `run_bonus`) — all do load-engine /
  iterate cases / write JSON under `eval/results/` / print a table. Extract that scaffold once.
- **week tooling** (`w5_sample`, `w5_read`, `w5_replay`, `w5_taxonomy`, `w5_traffic`,
  `w6_label`, `w6_ragas`) — genuinely different jobs. Do NOT merge their logic; only route
  them through the dispatcher.
- **data modules** (`endorsement_content`, `claims_population`, `w6_population`) — these are
  source data, not scripts. Leave the content alone; move under `tools/data/` at most.
- **utilities** (`make_endorsements`, `prepare_corpus`, `resolve_chunk`, `chunk_report`,
  `build_w4_golden`) — keep, route through the dispatcher.

Compatibility is non-negotiable: `python tools/run_w6.py --stage judge --judge judge_v2`
is pasted in a graded write-up. Every old invocation keeps working, via a thin shim that
prints the new equivalent. Shims are listed in the handoff so Worker 5 can document them.

**Definition of Done:**
- [ ] `python weeks.py --help` lists every week command with a one-line description
- [ ] Every command in Worker 1's GOAL C inventory still runs (`--help`/dry-run where a full run costs tokens; state which were which)
- [ ] Shared runner scaffold extracted once and used by all four runners
- [ ] No week script's *measurement logic* altered — only its plumbing
- [ ] GOAL A re-run, still identical
- [ ] `git status` proves the no-touch list is untouched

**Output Contract:**
- Delivers: dispatcher command table, shim list (old → new), LOC before/after for `tools/`
- Format: table + pasted `--help`
- Next worker needs: the command table and the final file layout

---

### Worker 4a — Comment sweep: rag/ core
| Field | Detail |
|-------|--------|
| Persona | Technical author who writes for a learner, embedded in the code |
| Scope | `rag/` modules whose comment density is below the `config.py` bar, plus `config.py` gap-fill |
| Tools | read, edit, bash |
| Agent Type | general-purpose |
| Depends On | Worker 2, Worker 3 |
| Execution | PARALLEL with 4b, worktree isolation |
| Reversible | YES |
| Touches Untrusted Content | NO |

`rag/config.py` is already the standard: 112 comment lines in 263, and it explains *why*
`RRF_K=60`, why `CHUNK_SIZE=220`, why the judge is a different model family. The gap is
measured, not guessed:

| File | Lines | `#` comments | Priority |
|---|---|---|---|
| `rag/embeddings.py` | 168 | 2 | HIGH |
| `rag/rerankers.py` | 226 | 5 | HIGH |
| `rag/llm.py` | 129 | 6 | HIGH |
| `rag/engine.py` | 287 | 7 | HIGH |
| `rag/judge.py` | 189 | 7 | HIGH |
| `rag/claims.py` | 388 | 17 | MED |
| `rag/query.py` | 193 | 18 | MED |
| `rag/evaluation.py` | 607 | 23 | MED |
| `rag/generation.py` | 326 | 26 | MED |

Two comment kinds are required, and nothing else:

1. **"why this, not that"** — at each real choice point, name the alternative and why it
   lost. bge-small vs a larger encoder; cross-encoder vs Cohere vs none; RRF over ranks vs
   score averaging (the W4 brief calls score-averaging out explicitly as a mistake); a
   different-family judge vs a bigger sibling.
2. **number rationale** — every literal that is a tuning decision gets its reason. Anything
   in `config.py` still lacking one gets one.

Also required by the Phase 0 answer: the non-syllabus knobs (`USE_HYDE`,
`USE_QUERY_REWRITE`, Cohere reranker, the extra `EMBEDDING_MODELS` entries, the `fixed` and
`sentence` chunk strategies) stay working and each gets an explicit marker: *not required by
W3–W6, kept to show the alternative we rejected and why*.

**Definition of Done:**
- [ ] Every HIGH file reaches a comment density comparable to `config.py`'s ratio, without padding
- [ ] Every tuning literal in `config.py` and the HIGH files has a stated reason
- [ ] Every non-syllabus knob carries the "kept as a rejected alternative" marker
- [ ] **Zero executable lines changed.** `git diff -w --ignore-blank-lines` on the lane shows comment/docstring hunks only
- [ ] GOAL A re-run after merge, identical
- [ ] No claim in a comment is asserted without reading the code it describes

**Output Contract:**
- Delivers: per-file comment counts before/after, list of numbers explained, list of rejected-alternative markers added
- Format: table
- Next worker needs: the list of documented decisions, for the WEEKS.md index

---

### Worker 4b — Comment sweep: front ends & dispatcher
| Field | Detail |
|-------|--------|
| Persona | Same as 4a, different files |
| Scope | `main.py` (407 lines, **0** `#` comments), `server.py` (398/16), `evaluate.py` (343/11), the new `weeks.py`, `rag/__init__.py` |
| Tools | read, edit, bash |
| Agent Type | general-purpose |
| Depends On | Worker 2, Worker 3 |
| Execution | PARALLEL with 4a, worktree isolation |
| Reversible | YES |
| Touches Untrusted Content | NO |

`main.py` has zero `#` comments across 407 lines and is the file a learner opens first.
Same two comment kinds as 4a, plus: why three front ends over one, and why the CLI, the
server and the evaluator must all go through `RagEngine` rather than each holding its own
retrieval path.

**Definition of Done:**
- [ ] `main.py`, `server.py`, `evaluate.py` each carry a header explaining what the front end is for and why it exists separately
- [ ] SSE/streaming choices in `server.py` justified against the alternative (polling / plain JSON)
- [ ] Zero executable lines changed; `git diff -w` shows comment hunks only
- [ ] GOAL B re-run after merge, clean
- [ ] All three front ends actually launched once and confirmed to start

**Output Contract:**
- Delivers: per-file comment counts before/after, launch evidence
- Format: table
- Next worker needs: nothing beyond the file list

**MERGE STEP after 4a/4b:** orchestrator merges both worktrees, re-runs GOAL A and GOAL B on
the merged tree before Worker 5 starts. A merge conflict is resolved in favour of keeping
both comments, never by dropping one.

---

### Worker 5 — WEEKS.md syllabus index + docs refresh
| Field | Detail |
|-------|--------|
| Persona | Curriculum-minded documentation engineer |
| Scope | The map from each W3–W6 requirement to the code that implements it and the command that reproduces it; repair path references in README/CLAUDE/AGENTS; author the Phase 4.5 audit workflow |
| Tools | read, edit, write, bash |
| Agent Type | general-purpose |
| Depends On | Worker 3, Worker 4a, Worker 4b |
| Execution | SEQUENTIAL |
| Reversible | YES |
| Touches Untrusted Content | NO |

`WEEKS.md` is the deliverable that makes "simple" true without deleting anything: one screen
per week, each row = requirement → file:line → reproduce command → the artifact it
produced. It is also what Phase 4.5's coverage audit grades against.

Rows must cover, at minimum: two chunking strategies and the hit-in-top-5 comparison; metadata
filter changing top-1; citations resolving to real chunk_ids; forced refusal; hit-rate@3
before/after with exactly one variable; R/G/Not-In-Corpus labelling; p50 latency; RRF k=60;
cross-encoder rerank; MMR lambda; seeded random trace sample; replay-from-trace-alone;
redact-before-write; open coding; the 4–7 mode taxonomy; the dated prediction; blind
`labels_25.json` and its ordering evidence; agreement before → after; judge_v1 vs judge_v2
with the two disagreements; assertions-vs-judged-criteria counts; pass rate by mode; RAGAS
faithfulness and context precision.

**Definition of Done:**
- [ ] `WEEKS.md` exists, one section per week, every row has a real file:line and a real command
- [ ] Every file:line cited was opened and verified to contain what the row claims
- [ ] README.md / CLAUDE.md / AGENTS.md / `.claude/stack-profile.md` updated for any moved path or renamed command
- [ ] Graded write-ups edited only by APPENDING a path-change note, never by altering a reported number or claim
- [ ] `.claude/workflows/syllabus-coverage-audit.mjs` authored, ready for Phase 4.5
- [ ] GOAL C re-run: every documented command resolves

**Output Contract:**
- Delivers: `WEEKS.md`, docs changed, count of rows, any requirement it could NOT find code for
- Format: file + a flagged list of unfound requirements
- Next worker needs: the unfound list, which becomes the coverage audit's prior

---

## Execution Trace

| Worker | Status | Loop # | Notes |
|--------|--------|--------|-------|
| Worker 1 — Baseline & Contract Freeze | DONE | 1 | 96%. GOAL B all clean. 44 cmds, 0 broken. 51 symbols w/ 2+ importers. Traps: UNSPECIFIED pass-through, dead __init__ re-exports |
| Worker 2 — rag/ decomposition | DONE | 2 | 93%. retrieval.py 1005->577 + 4 modules. GOAL A identical, 24523 chunks. RRF/chunking/indexing splits DECLINED with reasons |
| Worker 3 — tools/ consolidation | DONE | 3 | 88%. weeks.py dispatcher + tools/_runner.py + tools/data/. 44/44 cmds live. LOC +48 (honest). W6 numbers reproduce |
| Worker 4a — Comments: rag/ core | IN PROGRESS | 4 | disjoint-file parallel, NOT worktree (W2/W3 changes uncommitted) |
| Worker 4b — Comments: front ends | IN PROGRESS | 4 | disjoint-file parallel |
| Worker 5 — WEEKS.md + docs | PENDING | - | - |

Loop budget: 5 loops for the spine, 3 held for re-delegation and Phase 4.5 fixes.

---

## Risk Flags

| # | Risk | Decision Made |
|---|------|---------------|
| 1 | "Simplest possible" vs "lose no topic" genuinely conflict — the syllabus itself mandates 4 chunkers, 3 retrieval modes, MMR, 2 rerankers, judge, assertions, tracing, diagnostics, RAGAS | Optimise for **legibility, not line count**. Report both LOC delta and per-file max length; never let LOC reduction justify deleting a concept |
| 2 | Chunk ids are derived from chunk text; any perturbation of chunking silently shifts every `chunk_id` in the golden set and moves hit-rate@3 without raising an error | Worker 2 forbidden from touching chunking logic; GOAL A re-run and diffed after every lane, including the 24,523 chunk count |
| 3 | `eval/labels_25.json` ordering evidence is worth 25 W6 marks and lives in git history | Hard no-touch list; no worker may run any git mutation; delivery stops at a report |
| 4 | Comment sweep produces confidently-wrong explanations — a plausible "why" that misdescribes the code is worse than silence | 4a/4b DoD requires reading the code before asserting; any comment the author is unsure of must be omitted and listed in the handoff instead. Critic and Code Reviewer both check comment truthfulness |
| 5 | Old week commands are pasted verbatim in graded write-ups; consolidation breaks them | Shims for every old invocation; GOAL C re-run by the Verifier independently |
| 6 | Parallel 4a/4b both edit Python files | Worktree isolation + explicit merge step with GOAL A/B re-run before Worker 5 |
| 7 | `ms` column in GOAL A varies run to run and could be read as a regression | Explicitly excluded from the identity check, stated in the GOAL |
| 8 | Worker 2 "declines a seam" and quietly does nothing | DoD requires reporting the decision either way, with the reason |

---

## Validation Workflows

| Workflow | Existing / To author | Validates on THIS task | Est. agents |
|----------|----------------------|------------------------|-------------|
| Syllabus Coverage Audit | To author — `.claude/workflows/syllabus-coverage-audit.mjs`, written in Worker 5's lane | One agent per task set (W3, W4, W5, W6, the W3/W4 bonuses, the W6 bonus), each independently hunting the simplified tree for its own requirements. Adversarial default: a topic is **LOST** unless the agent cites file:line proving it survives. Cross-checked against `WEEKS.md` so the index cannot grade itself. | ~6 |

Runs in Phase 4.5 **before** `squad-code-reviewer`; its confirmed findings feed the reviewer.

---

## Approval

**Approve:** `yes` or `go`
**Adjust a worker:** `adjust worker [N]: [feedback]`
**Add a worker:** `add worker: [description]`
**Remove a worker:** `remove worker [N]`
**Restart plan:** `replan`

> No workers spin up until you explicitly approve.
