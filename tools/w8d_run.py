"""Week 8 Task Set D: score the claims agent's path, not just its answer.

    python weeks.py w8d-eval --stage baseline    # trajectory eval, no mitigation
    python weeks.py w8d-eval --stage mitigate    # apply the one mitigation, re-run, before/after
    python weeks.py w8d-eval --stage injection   # bonus: indirect prompt injection, then guardrail
    python weeks.py w8d-eval --stage all         # all three, in order

`baseline` runs tools/w7d_agent.py's run_agent over the same 10 claims as
Week 7 (data/w7d_claims.py), grades each trajectory against
data/w8d_expected_trajectories.py, and writes:
  eval/w8d/baseline.csv            one row per claim
  eval/w8d/baseline_summary.json   the four trajectory numbers + the gap
  eval/w8d/gap_case.md             one named right-answer-wrong-path claim

`mitigate` re-runs the same 10 claims through the mitigated agent
(w8d_mitigation.py), diffs the top failure mode's count and the price paid
against the baseline, and writes:
  eval/w8d/mitigated.csv
  eval/w8d/mitigation_report.md    before -> after, price paid, regression table

`injection` plants an instruction inside a claim's adjuster notes, runs it
unguarded then guarded, and writes:
  eval/w8d/injection_report.md
"""

import argparse
import csv
import json
from pathlib import Path

from data.w7d_claims import CLAIMS
from w7d_agent import run_agent
from w8d_trajectory import headline_numbers, mode_counts, per_claim_report

OUT_DIR = Path("eval/w8d")


def _run_all(run_fn):

    reports, results = [], {}

    for claim in CLAIMS:
        claim_id = claim["claim_id"]
        result = run_fn(claim_id)
        report = per_claim_report(claim_id, result)
        results[claim_id] = result

        print(
            f"  {claim_id}  outcome={'PASS' if report['outcome_pass'] else 'FAIL':4}  "
            f"trajectory={'PASS' if report['trajectory_pass'] else 'FAIL':4}  "
            f"steps={report['steps_taken']}/{report['steps_needed']}  "
            f"modes={report['failure_modes'] or '-'}"
        )

        reports.append(report)

    return reports, results


def _write_csv(path, reports):

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "claim_id", "dependency", "sequence", "outcome_pass", "trajectory_pass",
            "failure_modes", "tool_choice_correct", "tool_choice_total",
            "argument_valid", "argument_total", "steps_taken", "steps_needed",
            "cost_usd", "total_tokens", "wall_clock_s",
        ])
        for r in reports:
            writer.writerow([
                r["claim_id"], r["dependency"], " ".join(r["sequence"]), r["outcome_pass"],
                r["trajectory_pass"], " ".join(r["failure_modes"]), r["tool_choice_correct"],
                r["tool_choice_total"], r["argument_valid"], r["argument_total"],
                r["steps_taken"], r["steps_needed"], f"{r['cost_usd']:.6f}",
                r["total_tokens"], f"{r['wall_clock_s']:.3f}",
            ])


def baseline():

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Running the baseline agent over 10 claims...")
    reports, results = _run_all(run_agent)

    numbers = headline_numbers(reports)
    counts = mode_counts(reports)

    _write_csv(OUT_DIR / "baseline.csv", reports)
    (OUT_DIR / "baseline_summary.json").write_text(
        json.dumps({"numbers": numbers, "mode_counts": counts, "reports": reports}, indent=2),
        encoding="utf-8",
    )

    print()
    print(f"tool-choice accuracy   {numbers['tool_choice_accuracy']:.3f}  ({numbers['tool_choice_correct']}/{numbers['tool_choice_total']})")
    print(f"argument validity      {numbers['argument_validity_rate']:.3f}  ({numbers['argument_valid']}/{numbers['argument_total']})")
    print(f"step efficiency        {numbers['step_efficiency']:.3f}")
    print(f"cost per claim  p50    ${numbers['cost_p50_usd']:.5f}   max  ${numbers['cost_max_usd']:.5f}")
    print(f"outcome pass rate      {numbers['outcome_pass_rate']:.3f}")
    print(f"trajectory pass rate   {numbers['trajectory_pass_rate']:.3f}")
    print(f"gap (outcome - traj.)  {numbers['gap']:+.3f}")
    print(f"failure modes          {counts}")

    # Prefer a grounding failure (a real citation of something no tool result
    # ever returned) over a mere step-count violation - both are legitimate
    # outcome-pass/trajectory-fail cases, but "fluent fiction" is the sharper
    # illustration of why the two evals are asked to disagree at all.
    gap_cases = [r for r in reports if r["outcome_pass"] and not r["trajectory_pass"]]
    gap_cases.sort(key=lambda r: "hallucinated_argument" not in r["failure_modes"])
    if gap_cases:
        case = gap_cases[0]
        lines = [
            f"# Right answer, wrong path: {case['claim_id']}",
            "",
            f"Outcome eval: **PASS** ({case['outcome_note']})",
            f"Trajectory eval: **FAIL** ({case['trajectory_note']})",
            "",
            f"Tool sequence actually taken: `{' -> '.join(case['sequence'])}`",
            f"Failure modes: {case['failure_modes']}",
        ]
        (OUT_DIR / "gap_case.md").write_text("\n".join(lines), encoding="utf-8")
        print()
        print(f"wrote {OUT_DIR / 'gap_case.md'} ({case['claim_id']})")
    else:
        print()
        print("no right-answer-wrong-path claim in this run - every outcome pass also passed trajectory")

    print(f"wrote {OUT_DIR / 'baseline.csv'}")
    print(f"wrote {OUT_DIR / 'baseline_summary.json'}")

    return reports, numbers, counts


def main():

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["baseline", "mitigate", "injection", "all"], default="baseline")
    args = parser.parse_args()

    if args.stage in ("baseline", "all"):
        baseline()

    if args.stage in ("mitigate", "all"):
        from w8d_mitigation import mitigate
        mitigate()

    if args.stage in ("injection", "all"):
        from w8d_injection import injection_demo
        injection_demo()


if __name__ == "__main__":
    main()
