# Claims Triage & Coverage Assistant (Week 12 capstone, Variant D)

Triages a motor or household FNOL, checks the policy was in force **on the loss date**, retrieves the wording in
force **on the loss date** (not the newest wording), cites clause **and edition**, reports deductible, sub-limit and
policy limit as three separate numbers, and **refers the claim to an adjuster instead of deciding it**. One entry
point (`python weeks.py w12 ...`), one trace id from FNOL in to referral out.

Synthetic corpus and claims: six short wordings (two editions each of the household flood and motor water forms,
so the 2025 rewrite is real), nine policies, 31 FNOLs with planted PII. Not the brief's 60-page wordings or 500
claim files.

## Run it

```bash
uv sync                                   # or: pip install -r requirements.txt
uv pip install reportlab                  # renders the wordings to PDF; used by tools/ since Week 3 but never declared
echo GROQ_API_KEY=... > .env              # the only thing that leaves the machine is the model call

python weeks.py make-w12-corpus           # once: writes insurance_docs_w12/*.pdf  (first run also builds chroma_db_w12/)
python weeks.py w12 triage --claim CLM-2026-80003      # live demo: FNOL in, tool trail, referral out
python weeks.py w12 all                   # the integrated eval and every audit (spends LLM tokens, ~1 h on the free tier)
```

First start is slow: the policy-wording MCP server loads the embedder and reranker and answers a warm-up query
before it will speak (30 s warm, ~2-3 min cold). That is deliberate - a cold first search is ~75 s on this machine.

Stages individually (everything not marked LLM is free and runs in a couple of minutes):

| command | what it does | LLM |
|---|---|---|
| `w12 triage --claim C [--question Q] [--no-date-filter]` | one request, with its tool trail and cost | yes |
| `w12 run --label main [--cases w01,w02]` | the eval suite; resumable; `--no-date-filter` = the "before" arm | yes |
| `w12 score / taxonomy / trajectory --label main` | assertions, error taxonomy, tool-choice accuracy | no |
| `w12 retrieval` | hit-rate@3 and wrong-edition rate, date filter off vs on | no |
| `w12 groundability --label main` | the closed loop: replay the model's own queries under retrieval before/after the fix | no |
| `w12 pii` | probes every MCP tool for every claim, scans logs, tests the wire guard | no |
| `w12 trace --label main` | one trace id across both hops, per request | no |
| `w12 replay --label main --trace ID` | re-runs a logged request's retrieval and compares by hash | no |
| `w12 judge / agreement --label main --judge-version v1|v2 --judge-reasoning none|low` | LLM judge (qwen) and its agreement with `eval/w12/labels_main.json` | judge |
| `w12 reports --label main` | cost per claim by stage, hailstorm-week arithmetic | no |

## The model, and why the free tier shapes everything

The capstone runs on `openai/gpt-oss-120b` (`LLM_MODEL` overrides it); Weeks 7-11 ran on `gpt-oss-20b`. The free tier
caps each model at **200,000 tokens/day** (a refilling bucket, ~2.3 tokens/s) and **8,000 tokens/minute**, and one
triage costs ~11,000 tokens, so a day's allowance is ~18 claims. `run` therefore saves every finished case and
skips it on re-run, never records a run that merely waited on the limit, and the write-ups say how many cases
actually ran. See `eval/w12/cost_and_10x.md`.

## Where things are

| | |
|---|---|
| `tools/w12_agent.py` | the agent loop; discovers MCP tools at start-up; mints and propagates the trace id |
| `tools/w12_policy_server.py`, `w12_claims_server.py` | our two MCP servers (policy wording scoped by product and date; claims records, redacted) |
| `tools/w12_retrieval.py` | the date filter, enforced in code, over the real Week 3-4 `RagEngine` |
| `tools/w12_guard.py` | the output guard: no decision language leaves the process |
| `tools/w12_pii.py` | redaction and the audit that does not trust it |
| `tools/w12_inforce.py` | which edition, which policy range, which limits - plain code, no model |
| `tools/w12_eval.py`, `w12_audit.py`, `w12_reports.py` | the eval, the audits, the cost report |
| `tools/w12_external_client.py` | a stand-alone MCP client (stdlib only) for the policy-wording server |
| `ARCHITECTURE_W12.md` | the one-page sketch: boxes, arrows, model calls, money |
| `eval/w12/EVAL_REPORT.md` | results, the re-scored taxonomy, what the suite does not cover |
| `SEAMS_W12.md`, `WEAKNESSES_W12.md`, `DEMO_W12.md`, `FRESH_EYES_W12.md` | the process documents |

The Week 11 work (the drill, the failure-to-test loop on the Week 7 agent) is `results_week11d.md` and `eval/w11d/`.
