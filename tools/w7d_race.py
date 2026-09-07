"""Race the agent (w7d_agent.py) against the workflow (w7d_workflow.py)
over the same 10 claims, and report the four numbers Task Set D asks for.

    python tools/w7d_race.py                  # full race, both systems
    python tools/w7d_race.py --stage race
    python tools/w7d_race.py --stage budget-demo
    python tools/w7d_race.py --stage tool-diff

`race` writes eval/w7d/race.csv (one row per system per claim) and
eval/w7d/race_summary.json (the two systems' four headline numbers plus
the per-claim pass/fail), and prints the comparison table.

`budget-demo` runs one claim through the agent with max_iterations
deliberately set to 1, so it cannot finish - get_claim alone takes lap 1 -
and writes the full transcript to eval/w7d/budget_termination.log. That is
the log Task Set D §2.4 asks for: proof the budget check fires and the
run exits cleanly, not proof that a claim organically spins one wall-clock
minute a day. The four checks it exercises are the same four checked on
every lap of a real run; see w7d_agent.py's run_agent loop.

`tool-diff` writes eval/w7d/tool_description_diff.md, showing the naive
first draft of compute_payout against the version actually wired into
TOOLS in w7d_claims_tools.py.
"""

import argparse
import csv
import json
import statistics
from pathlib import Path

from data.w7d_claims import CLAIMS, GOLDEN
from w7d_agent import run_agent
from w7d_claims_tools import COMPUTE_PAYOUT_TOOL, COMPUTE_PAYOUT_TOOL_DRAFT
from w7d_common import Budget, grade
from w7d_workflow import run_workflow

OUT_DIR = Path("eval/w7d")


def _run_all(run_fn, system_name):

    rows = []

    for claim in CLAIMS:
        claim_id = claim["claim_id"]
        result = run_fn(claim_id)
        passed, note = grade(result, GOLDEN[claim_id])

        print(
            f"  [{system_name:8}] {claim_id}  "
            f"{'PASS' if passed else 'FAIL':4}  "
            f"{result.wall_clock_s:5.2f}s  "
            f"{result.total_tokens:5} tok  "
            f"${result.cost_usd:.5f}  "
            f"status={result.coverage_status}  payout={result.payout}  ({note})"
        )

        rows.append((result, passed, note))

    return rows


def _headline(rows):

    n = len(rows)
    passed = sum(1 for _, ok, _ in rows if ok)
    latencies = sorted(r.wall_clock_s for r, _, _ in rows)
    total_tokens = sum(r.total_tokens for r, _, _ in rows)
    total_cost = sum(r.cost_usd for r, _, _ in rows)

    return {
        "pass_rate": passed / n,
        "pass_count": passed,
        "n": n,
        "p50_latency_s": statistics.median(latencies),
        "total_tokens": total_tokens,
        "cost_per_claim_usd": total_cost / n,
    }


def race():

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Racing the agent...")
    agent_rows = _run_all(run_agent, "agent")

    print("Racing the workflow...")
    workflow_rows = _run_all(run_workflow, "workflow")

    agent_headline = _headline(agent_rows)
    workflow_headline = _headline(workflow_rows)

    csv_path = OUT_DIR / "race.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "system", "claim_id", "dependency", "pass", "outcome",
            "coverage_status", "payout", "expected_payout",
            "wall_clock_s", "total_tokens", "cost_usd", "note",
        ])
        for system_name, rows in (("agent", agent_rows), ("workflow", workflow_rows)):
            for claim, (result, passed, note) in zip(CLAIMS, rows):
                writer.writerow([
                    system_name, claim["claim_id"], claim["dependency"], passed,
                    result.outcome, result.coverage_status, result.payout,
                    GOLDEN[claim["claim_id"]]["payout"], f"{result.wall_clock_s:.3f}",
                    result.total_tokens, f"{result.cost_usd:.6f}", note,
                ])

    summary_path = OUT_DIR / "race_summary.json"
    summary_path.write_text(
        json.dumps({"agent": agent_headline, "workflow": workflow_headline}, indent=2),
        encoding="utf-8",
    )

    print()
    print(f"{'metric':<18} {'agent':>12} {'workflow':>12}")
    print(f"{'pass rate':<18} {agent_headline['pass_count']:>6}/{agent_headline['n']:<5} {workflow_headline['pass_count']:>6}/{workflow_headline['n']:<5}")
    print(f"{'p50 latency (s)':<18} {agent_headline['p50_latency_s']:>12.2f} {workflow_headline['p50_latency_s']:>12.2f}")
    print(f"{'total tokens':<18} {agent_headline['total_tokens']:>12} {workflow_headline['total_tokens']:>12}")
    print(f"{'cost / claim ($)':<18} {agent_headline['cost_per_claim_usd']:>12.5f} {workflow_headline['cost_per_claim_usd']:>12.5f}")
    print()
    print(f"wrote {csv_path}")
    print(f"wrote {summary_path}")


def budget_demo():

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    claim_id = "c04"  # the deepest claim: get_claim, 2x search_policy, compute_payout
    tiny_budget = Budget(max_iterations=1, max_tokens=12000, max_cost_usd=0.02, max_wall_clock_s=45.0)

    result = run_agent(claim_id, budget=tiny_budget)

    log_path = OUT_DIR / "budget_termination.log"
    lines = [
        f"budget-termination demo: claim {claim_id}, max_iterations={tiny_budget.max_iterations}",
        "",
        *result.transcript,
        "",
        f"outcome: {result.outcome}",
        f"budget_reason: {result.budget_reason}",
        f"iterations used: {result.iterations}",
        f"wall_clock_s: {result.wall_clock_s:.3f}",
    ]
    log_path.write_text("\n".join(lines), encoding="utf-8")

    print("\n".join(lines))
    print()
    print(f"wrote {log_path}")

    assert result.outcome == "budget_exceeded", (
        "expected the tiny budget to trip - if this fails, the loop is not "
        "checking the budget before its first real lap"
    )


def tool_diff():

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    diff_path = OUT_DIR / "tool_description_diff.md"
    diff_path.write_text(
        "# compute_payout: draft vs final\n\n"
        "## Draft (rejected)\n\n"
        "```json\n" + json.dumps(COMPUTE_PAYOUT_TOOL_DRAFT, indent=2) + "\n```\n\n"
        "Problems: does two jobs (\"decide *and* compute\"), `status` is a free string\n"
        "instead of an enum, and \"handles the claim\" overlaps both `get_claim` (which\n"
        "also \"handles\" the claim file) and `search_policy` (deciding coverage is what\n"
        "reading the policy wording is for).\n\n"
        "## Final (wired into TOOLS)\n\n"
        "```json\n" + json.dumps(COMPUTE_PAYOUT_TOOL, indent=2) + "\n```\n",
        encoding="utf-8",
    )

    print(f"wrote {diff_path}")


def main():

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["race", "budget-demo", "tool-diff", "all"], default="race")
    args = parser.parse_args()

    if args.stage in ("tool-diff", "all"):
        tool_diff()

    if args.stage in ("budget-demo", "all"):
        budget_demo()

    if args.stage in ("race", "all"):
        race()


if __name__ == "__main__":
    main()
