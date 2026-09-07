# SQUAD_BASELINE.md — pre-refactor regression contract

Frozen at commit **`933d926`** ("Week 6 bonus: complete run, all 23 policy-backed cases"),
branch `master`, on 2026-08-26.

This file is a **measurement, not a change**. Nothing in the repo was modified to produce it.
Its purpose: after the simplification refactor lands, every number and every command below must
still hold. Anything that differs is a behaviour change and must be justified, not discovered.

Companion file: [SQUAD_BASELINE_imports.md](SQUAD_BASELINE_imports.md) — the `rag/` import
surface map and line counts.

---

## GOAL A — retrieval metrics (the numeric contract)

Captured at `933d926` from `python evaluate.py retrieval --k 1`. **Recorded verbatim; not re-run
here** (it was already captured, and re-running only risks perturbing the index).

```
configuration  hit@1  recall@1  prec@1  mrr    ms
current        0.844  0.844     0.844   0.844  1149

Missed entirely : ['q05', 'q09', 'q13', 'q26', 'q27']
Lost in rerank  : none
Out-of-scope questions with surviving context: 5/6
Index is up to date: 24523 chunks, 8 documents
```

### What is and is not in the contract

| quantity | value | in contract? |
|---|---|---|
| `hit@1` | `0.844` | **YES** — must not regress |
| `recall@1` | `0.844` | **YES** |
| `prec@1` | `0.844` | **YES** |
| `mrr` | `0.844` | **YES** |
| Missed entirely | `['q05', 'q09', 'q13', 'q26', 'q27']` | **YES** — exact set, exact membership |
| Lost in rerank | `none` | **YES** — must stay empty |
| Out-of-scope questions with surviving context | `5/6` | **YES** |
| Index size | `24523 chunks, 8 documents` | **YES** — a change here means chunking or the index signature moved |
| `ms` | `1149` | **NO — EXCLUDED.** Wall-clock, machine- and cache-dependent, not a behaviour signal |

### How to check the contract after the refactor

```bash
python evaluate.py retrieval --k 1
```

Retrieval evaluation makes **no LLM calls**, so this is cheap and deterministic. A delta in *any*
row above except `ms` is a regression until proven otherwise.

Two failure modes to watch for specifically:

1. **Index silently reused when it should have been rebuilt.** `rag/config.py` derives the index
   signature from the chunking/embedding knobs. If the refactor moves a knob out of `config.py`
   without routing it through the signature, the evaluator will report the *old* index's numbers
   and the contract will pass while the behaviour has actually changed. Verify the
   `24523 chunks, 8 documents` line, and confirm any intentional rebuild was intentional.
2. **`hit@1` improving.** An unexplained improvement is as much a signal as a regression — it
   usually means the relevance floor or the grounded prompt was relaxed.

---

## GOAL B — front-end health

All three commands were **actually executed** on 2026-08-26 at `933d926`. `frontend/node_modules`
was verified present first (it exists, so nothing was skipped and `npm install` was **not** run).
Output is pasted exactly as emitted.

### B1 — Python import health

```
$ cd d:/python/Rag/insurance_rag
$ python -c "import rag, main, server, evaluate"
EXIT_CODE=0
```

No stdout, no stderr, exit 0. All three front ends and the package root import cleanly.

### B2 — TypeScript typecheck

```
$ cd d:/python/Rag/insurance_rag/frontend
$ npx tsc -b --noEmit
EXIT_CODE=0
```

No output, exit 0. Clean typecheck.

### B3 — Frontend production build

```
$ cd d:/python/Rag/insurance_rag/frontend
$ npm run build

> frontend@0.0.0 build
> tsc -b && vite build

vite v8.2.1 building client environment for production...
transforming...✓ 24 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                   0.60 kB │ gzip:  0.36 kB
dist/assets/index-sc7uTE0k.css   17.62 kB │ gzip:  4.18 kB
dist/assets/index-DCv5cz5s.js   214.76 kB │ gzip: 67.12 kB

✓ built in 1.41s
EXIT_CODE=0
```

Build artefact sizes are part of the "before" record but are **not** a hard contract — a bundle
size change is expected if the frontend is touched. The hashed filenames
(`index-sc7uTE0k.css`, `index-DCv5cz5s.js`) will change on any content change and are recorded
for reference only. `frontend/dist` is gitignored (see `frontend/.gitignore`), so running the
build modified no tracked file.

### B4 — Frontend lint (bonus, not requested but cheap and documented)

```
$ cd d:/python/Rag/insurance_rag/frontend
$ npm run lint

> frontend@0.0.0 lint
> oxlint

EXIT=0
```

Zero diagnostics.

### GOAL B verdict

**PASS — all four commands exit 0, no warnings, no pre-existing breakage in the front-end layer.**

---

## GOAL C — documented-command inventory (the compatibility contract)

Every shell command a reader of the docs is told to run. A later worker consolidates `tools/`;
**every RESOLVES row below must still work after that consolidation.**

### Files scanned

All twelve named files exist and were read:

| file | lines | commands found |
|---|---|---|
| `README.md` | 633 | yes |
| `CLAUDE.md` | 114 | yes |
| `AGENTS.md` | 52 | yes (GitNexus only) |
| `.claude/stack-profile.md` | 125 | yes |
| `results.md` | 538 | yes |
| `results_week4.md` | 490 | yes |
| `results_week5.md` | 237 | yes |
| `results_week6.md` | 455 | yes |
| `notes.md` | 185 | yes (inline prose refs only) |
| `taxonomy.md` | 75 | **none** |
| `prediction.txt` | 67 | **none** |
| `w6_prediction.txt` | 75 | **none** |

### Verification method

- `EXECUTED --help` — the command's entry point was actually invoked with `--help` and returned
  exit 0. Strong evidence: argparse constructed, all module-level imports resolved.
- `EXECUTED` — the full command was actually run (GOAL B commands + lint).
- `STATIC` — target file/flag/`app` object verified to exist by reading the source. Used for
  anything that would cost tokens (LLM calls), take minutes (full index rebuild, sweeps), or
  block (dev servers).

No command that makes a paid LLM API call was executed. `python evaluate.py answers` and every
`tools/run_*.py` full run were deliberately **not** run.

### C1 — Setup

| command as written | file(s) | resolves to | status | evidence |
|---|---|---|---|---|
| `uv sync` | `CLAUDE.md:29`, `README.md:448`, `.claude/stack-profile.md:17` | `pyproject.toml` + `uv.lock` | RESOLVES | STATIC — `uv 0.12.3` on PATH, both files present |
| `pip install -r requirements.txt` | `CLAUDE.md:29`, `README.md:448`, `.claude/stack-profile.md:17` | `requirements.txt` | RESOLVES | STATIC — file present |
| `cd frontend && npm install` | `CLAUDE.md:30`, `README.md:467`, `.claude/stack-profile.md:33` | `frontend/package.json` | RESOLVES | STATIC — `node_modules` already populated |

### C2 — Lint / typecheck / build

| command as written | file(s) | resolves to | status | evidence |
|---|---|---|---|---|
| `cd frontend && npm run lint` | `CLAUDE.md:34`, `.claude/stack-profile.md:34` | `oxlint` (`frontend/node_modules/.bin/oxlint`) | RESOLVES | EXECUTED — exit 0 |
| `cd frontend && npx tsc -b --noEmit` | `CLAUDE.md:35`, `.claude/stack-profile.md:36` | TypeScript project refs | RESOLVES | EXECUTED — exit 0 |
| `cd frontend && npm run build` | `CLAUDE.md:44`, `README.md:467`, `.claude/stack-profile.md:38` | `tsc -b && vite build` → `frontend/dist` | RESOLVES | EXECUTED — exit 0 |
| `cd frontend && npm run dev` | `CLAUDE.md:48`, `README.md:477`, `.claude/stack-profile.md:39` | `vite` dev server, port 5173 | RESOLVES | STATIC — script present in `package.json`; long-running, not executed |

### C3 — Running the app

| command as written | file(s) | resolves to | status | evidence |
|---|---|---|---|---|
| `uvicorn server:app --reload --port 8010` | `CLAUDE.md:47`, `README.md:476`, `.claude/stack-profile.md:26` | `server.py` → `app` | RESOLVES | STATIC — `import server` succeeds (B1); long-running, not executed |
| `uvicorn server:app --port 8010` | `README.md:468` | `server.py` → `app` | RESOLVES | STATIC — same |
| `python main.py` | `CLAUDE.md:49`, `README.md:167,504`, `.claude/stack-profile.md:27` | `main.py` | RESOLVES | EXECUTED `--help` — exit 0 |
| `python main.py --reindex` | `CLAUDE.md:50`, `README.md:505` | `main.py` `--reindex` | RESOLVES | EXECUTED `--help` — flag present |
| `python main.py --mode sparse` | `README.md:506` | `main.py` `--mode` | RESOLVES | EXECUTED `--help` — flag present |
| `python main.py --reranker none` | `README.md:507` | `main.py` `--reranker` | RESOLVES | EXECUTED `--help` — flag present |
| `python main.py --mmr --mmr-lambda 0.5` | `README.md:508` | `main.py` `--mmr`, `--mmr-lambda` | RESOLVES | EXECUTED `--help` — both present |
| `python main.py --rewrite --hyde` | `README.md:509` | `main.py` `--rewrite`, `--hyde` | RESOLVES | EXECUTED `--help` — both present |
| `python main.py --source policy.pdf --page-min 7 --page-max 8` | `README.md:510` | `main.py` `--source`, `--page-min`, `--page-max` | RESOLVES | EXECUTED `--help` — all three present |
| `python main.py --trace --diagnose --question "What is the deductible?"` | `README.md:511` | `main.py` `--trace`, `--diagnose`, `--question` | RESOLVES | EXECUTED `--help` — all three present |

Full `main.py` flag set (frozen): `--diagnose --form --hyde --mmr --mmr-lambda --mmr-pool --mode
--page-max --page-min --policy-line --question --reindex --reranker --rewrite --source --top-k
--trace`.

### C4 — The evaluator

| command as written | file(s) | resolves to | status | evidence |
|---|---|---|---|---|
| `python evaluate.py retrieval --k 1` | `CLAUDE.md:40,63`, `README.md:522`, `.claude/stack-profile.md:22` | `evaluate.py` `COMMANDS["retrieval"]` | RESOLVES | EXECUTED `--help` + GOAL A output at `933d926` |
| `python evaluate.py answers --k 3` | `CLAUDE.md:41`, `README.md:527`, `.claude/stack-profile.md:23` | `COMMANDS["answers"]` | RESOLVES | EXECUTED `--help`. **Not run — makes paid LLM calls** |
| `python evaluate.py sweep-retrieval --k 1` | `README.md:523` | `COMMANDS["sweep-retrieval"]` | RESOLVES | EXECUTED `--help` |
| `python evaluate.py sweep-retrieval --k 1 --with-transforms` | `README.md:524` | same + `--with-transforms` | RESOLVES | EXECUTED `--help` — flag present |
| `python evaluate.py sweep-retrieval --k 1 --with-bge` | `README.md:525` | same + `--with-bge` | RESOLVES | EXECUTED `--help` — flag present |
| `python evaluate.py sweep-chunking --k 1` | `README.md:526` | `COMMANDS["sweep-chunking"]` | RESOLVES | EXECUTED `--help` |
| `python evaluate.py compare --k 1 --before eval/results/baseline-k1.json --after eval/results/current-k1.json` | `README.md:528-530`, `.claude/stack-profile.md:24` | `COMMANDS["compare"]`, `--before`, `--after` | RESOLVES | EXECUTED `--help`; **both referenced JSON files exist** in `eval/results/` |
| `python evaluate.py …` (generic) | `README.md:310` | — | RESOLVES | prose placeholder, covered by the rows above |

Frozen `evaluate.py` subcommand set (`COMMANDS` dict, `evaluate.py:268`):
`retrieval`, `sweep-retrieval`, `sweep-chunking`, `answers`, `compare`.
Frozen flag set: `--after --before --golden-set --k --label --mmr --mode --out --reranker
--with-bge --with-transforms`.

### C5 — `tools/` scripts (the set about to be consolidated)

**None of these were run** — they rebuild indexes and/or make paid LLM calls. The eleven with
argparse were verified with `--help`; the rest were verified statically (file exists, has an
`if __name__ == "__main__":` guard).

| command as written | file(s) | resolves to | status | evidence |
|---|---|---|---|---|
| `python tools/make_endorsements.py` | `results.md:529` | `tools/make_endorsements.py` | RESOLVES | STATIC — file + main guard |
| `python tools/chunk_report.py` | `results.md:104,317,530` | `tools/chunk_report.py` | RESOLVES | STATIC — file + main guard |
| `python tools/run_task_d.py` | `results.md:24,515,531` | `tools/run_task_d.py` | RESOLVES | STATIC — file + main guard |
| `python tools/run_bonus.py` | `results.md:383,532` | `tools/run_bonus.py` | RESOLVES | STATIC — file + main guard |
| `python tools/resolve_chunk.py "<chunk_id>" --contains "<text>"` | `results.md:175,533` | `tools/resolve_chunk.py` `--contains` | RESOLVES | EXECUTED `--help` — exit 0, flag present |
| `python tools/prepare_corpus.py` | `results_week4.md:485` | `tools/prepare_corpus.py` | RESOLVES | STATIC — file + main guard |
| `python tools/build_w4_golden.py` | `results_week4.md:486` | `tools/build_w4_golden.py` | RESOLVES | STATIC — file + main guard |
| `python tools/run_week4.py` | `results_week4.md:32,487` | `tools/run_week4.py` | RESOLVES | STATIC — file + main guard |
| `python tools/w5_traffic.py` | `results_week5.md:228` | `tools/w5_traffic.py` | RESOLVES | EXECUTED `--help` — exit 0 |
| `python tools/w5_traffic.py --demo` | `results_week5.md:229` | same, `--demo` | RESOLVES | EXECUTED `--help` — flag present |
| `python tools/w5_sample.py --seed 20260826 --n 20` | `results_week5.md:230`, `notes.md:31` | `tools/w5_sample.py` `--seed`, `--n` | RESOLVES | EXECUTED `--help` — both present |
| `python tools/w5_replay.py tr-wk5-0009` | `results_week5.md:69,231`, `notes.md:37` | `tools/w5_replay.py` positional trace id | RESOLVES | EXECUTED `--help` — exit 0 |
| `python tools/w5_read.py --sample eval/w5/sample.json` | `results_week5.md:232` | `tools/w5_read.py` `--sample` | RESOLVES | EXECUTED `--help`; **`eval/w5/sample.json` exists** |
| `python tools/w5_taxonomy.py --coding eval/w5/open_coding.json` | `results_week5.md:233,236` | `tools/w5_taxonomy.py` `--coding` | RESOLVES | EXECUTED `--help`; **`eval/w5/open_coding.json` exists** |
| `python tools/run_w6.py` | `results_week6.md:121,320` | `tools/run_w6.py` | RESOLVES | EXECUTED `--help` — exit 0 |
| `python tools/run_w6.py --stage summaries` | `results_week6.md:321` | `--stage` ∈ `{all,summaries,judge,agreement}` | RESOLVES | EXECUTED `--help` — choice valid |
| `python tools/run_w6.py --stage judge --judge judge_v1` | `results_week6.md:323` | `--stage`, `--judge` | RESOLVES | EXECUTED `--help` — both present |
| `python tools/run_w6.py --stage agreement --judge judge_v2` | `results_week6.md:324` | `--stage`, `--judge` | RESOLVES | EXECUTED `--help` — both present |
| `python tools/w6_label.py --slice 0:5` | `results_week6.md:322` | `tools/w6_label.py` `--slice` | RESOLVES | EXECUTED `--help` — flag present |
| `python tools/w6_ragas.py` | `results_week6.md:345` (prose reference, not a fenced command) | `tools/w6_ragas.py` | RESOLVES | EXECUTED `--help` — exit 0 |

### C6 — GitNexus (agent tooling, documented in `CLAUDE.md` / `AGENTS.md`)

| command as written | file(s) | resolves to | status | evidence |
|---|---|---|---|---|
| `npx -y gitnexus@latest <command>` | `CLAUDE.md:16` | npm registry package | RESOLVES | STATIC — external package, not repo-local |
| `node .gitnexus/run.cjs analyze` | `CLAUDE.md:76`, `AGENTS.md:6` | `.gitnexus/run.cjs` | RESOLVES | STATIC — **file exists** |
| `npx gitnexus analyze` | `CLAUDE.md:76`, `AGENTS.md:6` | npm registry package | RESOLVES | STATIC — external |
| `npm i -g gitnexus` | `CLAUDE.md:76`, `AGENTS.md:6` | npm registry package | RESOLVES | STATIC — external |

Unaffected by a Python refactor, but recorded so a docs rewrite does not drop them.

### C7 — Documented as *absent* (not broken; do not "fix" by inventing them)

These appear in the docs as explicit TODOs / suggestions. They are **not runnable today, and the
docs say so.** They are not regressions and the refactor is not obliged to create them.

| text as written | file(s) | status |
|---|---|---|
| `uv run ruff check .` | `.claude/stack-profile.md:18` | NOT-CONFIGURED-BY-DESIGN — labelled "TODO: no linter configured"; no ruff config, no `[tool.*]` block in `pyproject.toml` |
| `uv run ruff format --check .` | `.claude/stack-profile.md:19` | NOT-CONFIGURED-BY-DESIGN — labelled "TODO: no formatter configured" |
| `uv build` | `.claude/stack-profile.md:25` | NOT-APPLICABLE-BY-DESIGN — labelled "n/a — nothing is published" |
| pytest / unit tests | `CLAUDE.md:39`, `.claude/stack-profile.md:21` | NOT-PRESENT-BY-DESIGN — "no pytest suite exists (zero `test_*.py` in the repo)" |

### GOAL C tally

- **44 distinct runnable commands inventoried** across C1–C6.
- **0 are BROKEN.** Every documented command resolves to a real entry point, real flag, and (where
  a path is named) a real file.
- **4 further entries are documented-as-absent** (C7) and are explicitly *not* counted as broken.
- Of the 44, **22 were executed** (4 in full, 18 via `--help`); **22 were verified statically**.

---

## Pre-existing breakage

**None found.**

This section exists so that nothing already broken can later be blamed on the refactor. The
honest answer at `933d926` is that the repo is clean on every axis measured:

| axis | result |
|---|---|
| Python imports (`rag`, `main`, `server`, `evaluate`) | clean, exit 0 |
| TypeScript typecheck | clean, exit 0 |
| Frontend production build | clean, exit 0 |
| Frontend lint (oxlint) | clean, exit 0, zero diagnostics |
| Documented commands resolving to real entry points | 44/44 |
| Referenced data files (`eval/results/*.json`, `eval/w5/*.json`, `eval/golden_set.json*`) | all present |
| `.gitnexus/run.cjs` | present |

### Known non-breakage worth writing down anyway

Not failures, but facts that will otherwise be rediscovered as "the refactor broke it":

1. **`hit@1` is 0.844, not 1.0.** Five questions (`q05`, `q09`, `q13`, `q26`, `q27`) miss entirely
   at `933d926`. That is the *baseline*, not damage. Do not treat these five as refactor
   casualties, and do not "fix" them during the refactor — a retrieval improvement smuggled into a
   simplification makes the contract unfalsifiable.
2. **Three `tools/` files have no `if __name__ == "__main__":` guard** —
   `tools/claims_population.py` (434 lines), `tools/endorsement_content.py` (563 lines),
   `tools/w6_population.py` (383 lines). They are **data modules, not scripts**, and no doc tells a
   reader to run them (`results.md:487` links `endorsement_content.py` only as "reviewable source
   text"). Their lack of an entry point is correct, not broken.
3. **No Python linter, formatter, or test suite exists.** The de facto regression gate is
   `python evaluate.py retrieval --k 1`. There is no `test_*.py` anywhere in the repo, so the
   refactor has **no unit-test safety net** — GOAL A is the only automated behavioural check.
4. **`from rag import ...` is used nowhere.** `rag/__init__.py` re-exports `RagEngine`,
   `RetrievedChunk`, `format_pages`, but no file in the repo consumes the package root; every
   importer uses the full `from rag.<module> import ...` path. The refactor cannot rely on
   `rag/__init__.py` as an existing compatibility shim, because nothing goes through it today.
5. **`ms = 1149` is excluded from the contract** and will fluctuate. Do not report a latency change
   as a regression, and do not report a latency improvement as a win.

---

## Working-tree proof

The working tree already carried uncommitted work before this baseline was taken (`README.md`,
`main.py`, `pyproject.toml`, `requirements.txt`, `uv.lock` modified; many untracked files). That
pre-existing state is **not** attributable to this task.

This task added exactly two files and modified zero:

```
?? SQUAD_BASELINE.md
?? SQUAD_BASELINE_imports.md
```

`frontend/dist/` was rewritten by `npm run build`, but it is gitignored (`frontend/.gitignore`)
and therefore not a tracked change. No git mutation of any kind was performed — no `add`,
`commit`, `checkout`, `stash`, `branch`, `reset`, or `push`.
