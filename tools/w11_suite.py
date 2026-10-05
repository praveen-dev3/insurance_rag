"""The Week 11 regression suite: the Week 6/7 claim set plus every claim a
production failure has since added, run through the instrumented app.

A case passes only if *every* trial passes. The agent is a sampled model,
so a single green run of a case proves little - c11 failed on the first
trial of its first probe and might well have passed on the second. Counting
a case as passing on its best trial would let a flaky fix go green by luck,
which is exactly the "a test that has only ever been green is a test you
have not tested" failure the brief warns about; requiring all trials turns
luck into a failing case.

Assertions only, no judge: the grade is the one tools/w7d_common.py has
used since Week 7 (coverage status and payout against a hand-computed
golden). It is deterministic, so a RED here is a number and not an opinion.

The run is resumable. The free Groq tier caps gpt-oss-20b at 200,000
tokens a day, refilled continuously (about 2.3 tokens/s), and one triage
costs 7-9k tokens - so a 12-case suite does not fit in one day's allowance
and a run that cannot resume loses everything it paid for. Every finished
trial is written to disk before the next one starts, a re-run skips what is
already there, and `format_summary` says plainly which cases have not been
run rather than counting them as passes.
"""

import json
import time
from pathlib import Path
from types import SimpleNamespace

from data.w7d_claims import GOLDEN
from w7d_common import Budget, grade
from w11_app import run_request
from w11_obs import RequestSink

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "eval" / "w11d"

# Case ids in suite order. c01-c10 are the Week 7 claims, c11/c12 were added
# in Week 11 (data/w11d_cases.py).
SUITE = ["c01", "c02", "c03", "c04", "c05", "c06", "c07", "c08", "c09", "c10",
         "c11", "c12"]


def _as_result(final, trace):
    """Adapt a run to the shape w7d_common.grade() reads."""

    completed = trace.outcome == "completed"

    return SimpleNamespace(
        outcome="completed" if completed else "error",
        budget_reason=trace.outcome,
        coverage_status=final.get("coverage_status"),
        payout=final.get("payout"),
    )


def _path(label):
    return OUT_DIR / f"suite_{label}.json"


def run_suite(prompt_version, retrieval_version, trials=2, label="run",
              cases=None, log=print):

    cases = cases or SUITE
    log_path = REPO_ROOT / "traces" / f"w11d_suite_{label}.jsonl"
    sink = RequestSink(log_path)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    state = json.loads(_path(label).read_text()) if _path(label).exists() else {}
    done = state.get("done", {})
    started = time.perf_counter()

    for claim_id in cases:

        trials_out = done.setdefault(claim_id, [])

        for trial in range(len(trials_out) + 1, trials + 1):
            # The default 90 s wall-clock budget is a runaway-agent guard, and
            # on a rate-limited key a 429 wait of minutes trips it on a run
            # that was never slow, scoring an infrastructure stall as a
            # failed case. The suite lifts the wall-clock cap (the iteration,
            # token and cost caps stay) and refuses to record a run that
            # still hit it.
            trace, final = run_request(
                claim_id, user_id="suite", prompt_version=prompt_version,
                retrieval_version=retrieval_version, sink=sink,
                budget=Budget(max_wall_clock_s=6 * 3600),
            )

            if trace.outcome == "budget_exceeded:wall_clock":
                raise SystemExit(f"{claim_id}: wall-clock budget hit; not recording it as a result")

            ok, why = grade(_as_result(final, trace), GOLDEN[claim_id])
            trials_out.append({
                "trial": trial, "pass": ok, "why": why,
                "trace_id": trace.trace_id,
                "status": final.get("coverage_status"),
                "payout": final.get("payout"),
                "context_ids": list(trace.context_ids),
                "tokens": trace.totals()["tokens_in"] + trace.totals()["tokens_out"],
                "cost_usd": trace.totals()["cost_usd"],
            })
            log(f"  {claim_id} trial {trial}: {'PASS' if ok else 'FAIL'} "
                f"({why}) {trace.trace_id}")

            _path(label).write_text(json.dumps({
                "label": label, "prompt_version": prompt_version,
                "retrieval_version": retrieval_version,
                "trials_per_case": trials, "order": cases, "done": done,
            }, indent=2), encoding="utf-8")

    return summarise(label, time.perf_counter() - started)


def summarise(label, wall_s=0.0):
    """Counts over what has actually been run. Unrun cases are not passes."""

    state = json.loads(_path(label).read_text())
    trials = state["trials_per_case"]
    rows = []

    for claim_id in state["order"]:
        ran = state["done"].get(claim_id, [])
        rows.append({
            "claim_id": claim_id,
            "complete": len(ran) >= trials,
            "pass": len(ran) >= trials and all(t["pass"] for t in ran),
            "trials": ran,
        })

    complete = [r for r in rows if r["complete"]]

    summary = {
        "label": label,
        "prompt_version": state["prompt_version"],
        "retrieval_version": state["retrieval_version"],
        "trials_per_case": trials,
        "cases_passed": sum(1 for r in complete if r["pass"]),
        "cases_run": len(complete),
        "cases_total": len(rows),
        "trials_passed": sum(t["pass"] for r in rows for t in r["trials"]),
        "trials_run": sum(len(r["trials"]) for r in rows),
        "wall_clock_s": round(wall_s, 1),
        "failing_cases": [r["claim_id"] for r in complete if not r["pass"]],
        "not_yet_run": [r["claim_id"] for r in rows if not r["complete"]],
        "rows": rows,
    }

    return summary


def format_summary(summary):

    lines = [
        f"SUITE {summary['label'].upper()}  prompt={summary['prompt_version']}  "
        f"retrieval={summary['retrieval_version']}  trials/case={summary['trials_per_case']}",
        "",
        f"{'case':<5} {'result':<8} trials",
    ]

    for row in summary["rows"]:
        marks = " ".join("P" if t["pass"] else "F" for t in row["trials"]) or "-"
        result = ("PASS" if row["pass"] else "FAIL") if row["complete"] else "not run"
        lines.append(f"{row['claim_id']:<5} {result:<8} {marks}")

    lines += [
        "",
        f"CASES  {summary['cases_passed']}/{summary['cases_run']} pass of the cases run "
        f"({summary['cases_run']} of {summary['cases_total']} run; a case passes only if all "
        f"{summary['trials_per_case']} trials pass)",
        f"TRIALS {summary['trials_passed']}/{summary['trials_run']} pass",
        f"FAILING: {', '.join(summary['failing_cases']) or 'none'}",
        f"NOT YET RUN: {', '.join(summary['not_yet_run']) or 'none'}",
    ]

    return "\n".join(lines)
