"""The one mitigation: a hard step limit on the top failure mode from
eval/w8d/baseline_summary.json - step_overrun, 8 of 10 baseline claims (every
claim but c08 and c09), all of the same shape: the agent had already found
what it needed and spent one more search_policy call confirming it anyway.

Deliberately the smallest possible diff against the failure mode actually
observed, per Task Set D's own common-mistakes warning against shipping two
mitigations at once: this changes exactly one number,
`Budget.max_iterations`, passed into the unmodified run_agent loop from
w7d_agent.py. No prompt change, no new tool, no argument validation - if the
top mode drops, this before/after is the reason, not a co-factor.

    python weeks.py w8d-eval --stage mitigate

MITIGATED_MAX_ITERATIONS = 5 is exactly the lap budget the shortest correct
path needs for a covered claim (get_claim, 2 searches, compute_payout, final
answer = 5 laps when every lap makes exactly one tool call) and one lap
short of what the observed c04 baseline trajectory used (6 laps: get_claim +
3 searches + compute_payout + final answer) - tight enough to remove the
slack that step_overrun was spent on, and deliberately left tight enough
that c04's extra search leg has a real chance of being the price paid, not
a hypothetical one.
"""

import csv
import json
from dataclasses import replace
from pathlib import Path

from data.w7d_claims import CLAIMS
from w7d_agent import run_agent
from w7d_common import DEFAULT_BUDGET
from w8d_trajectory import headline_numbers, mode_counts, per_claim_report

OUT_DIR = Path("eval/w8d")
MITIGATED_MAX_ITERATIONS = 5
MITIGATED_BUDGET = replace(DEFAULT_BUDGET, max_iterations=MITIGATED_MAX_ITERATIONS)


def _run_mitigated():

    reports = []

    for claim in CLAIMS:
        claim_id = claim["claim_id"]
        result = run_agent(claim_id, budget=MITIGATED_BUDGET)
        report = per_claim_report(claim_id, result)

        print(
            f"  {claim_id}  outcome={'PASS' if report['outcome_pass'] else 'FAIL':4}  "
            f"trajectory={'PASS' if report['trajectory_pass'] else 'FAIL':4}  "
            f"steps={report['steps_taken']}/{report['steps_needed']}  "
            f"outcome={result.outcome}  modes={report['failure_modes'] or '-'}"
        )

        reports.append(report)

    return reports


def _write_csv(path, reports):

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "claim_id", "dependency", "sequence", "outcome_pass", "trajectory_pass",
            "failure_modes", "steps_taken", "steps_needed", "cost_usd", "total_tokens", "wall_clock_s",
        ])
        for r in reports:
            writer.writerow([
                r["claim_id"], r["dependency"], " ".join(r["sequence"]), r["outcome_pass"],
                r["trajectory_pass"], " ".join(r["failure_modes"]), r["steps_taken"], r["steps_needed"],
                f"{r['cost_usd']:.6f}", r["total_tokens"], f"{r['wall_clock_s']:.3f}",
            ])


def mitigate():

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    baseline_path = OUT_DIR / "baseline_summary.json"
    if not baseline_path.exists():
        raise SystemExit("run --stage baseline first: mitigate() diffs against eval/w8d/baseline_summary.json")

    baseline_data = json.loads(baseline_path.read_text(encoding="utf-8"))
    baseline_reports = baseline_data["reports"]
    baseline_numbers = baseline_data["numbers"]
    baseline_counts = baseline_data["mode_counts"]

    print(f"Re-running 10 claims with max_iterations={MITIGATED_MAX_ITERATIONS} (was {DEFAULT_BUDGET.max_iterations})...")
    reports = _run_mitigated()

    numbers = headline_numbers(reports)
    counts = mode_counts(reports)

    _write_csv(OUT_DIR / "mitigated.csv", reports)
    (OUT_DIR / "mitigated_summary.json").write_text(
        json.dumps({"numbers": numbers, "mode_counts": counts, "reports": reports}, indent=2),
        encoding="utf-8",
    )

    top_mode = max(baseline_counts, key=baseline_counts.get)
    before_top, after_top = baseline_counts.get(top_mode, 0), counts.get(top_mode, 0)

    cost_before = sum(r["cost_usd"] for r in baseline_reports)
    cost_after = sum(r["cost_usd"] for r in reports)
    tokens_before = sum(r["total_tokens"] for r in baseline_reports)
    tokens_after = sum(r["total_tokens"] for r in reports)
    latency_before = sum(r["wall_clock_s"] for r in baseline_reports)
    latency_after = sum(r["wall_clock_s"] for r in reports)

    newly_budget_exceeded = [
        r["claim_id"] for r in reports
        if "budget_exceeded" in r["failure_modes"] and "budget_exceeded" not in next(
            b["failure_modes"] for b in baseline_reports if b["claim_id"] == r["claim_id"]
        )
    ]

    all_modes = sorted(set(baseline_counts) | set(counts))
    regression_rows = []
    for mode in all_modes:
        b, a = baseline_counts.get(mode, 0), counts.get(mode, 0)
        flag = "WORSE" if a > b else ("new" if b == 0 and a > 0 else ("better" if a < b else "unchanged"))
        regression_rows.append((mode, b, a, flag))

    outcome_flips = [
        (r["claim_id"], b["outcome_pass"], r["outcome_pass"])
        for r, b in zip(reports, baseline_reports)
        if b["outcome_pass"] != r["outcome_pass"]
    ]

    lines = [
        "# Week 8 Task Set D: mitigation before -> after",
        "",
        f"Mitigation: `Budget.max_iterations` {DEFAULT_BUDGET.max_iterations} -> {MITIGATED_MAX_ITERATIONS}. "
        "Nothing else changed - same prompt, same tools, same three tool schemas, same model.",
        "",
        f"## Top failure mode: `{top_mode}` ({before_top} of 10 claims at baseline)",
        "",
        f"**{before_top} -> {after_top}**",
        "",
        "## Price paid",
        "",
        "| | before | after | delta |",
        "|---|---:|---:|---:|",
        f"| outcome pass rate | {baseline_numbers['outcome_pass_rate']:.3f} | {numbers['outcome_pass_rate']:.3f} | {numbers['outcome_pass_rate'] - baseline_numbers['outcome_pass_rate']:+.3f} |",
        f"| trajectory pass rate | {baseline_numbers['trajectory_pass_rate']:.3f} | {numbers['trajectory_pass_rate']:.3f} | {numbers['trajectory_pass_rate'] - baseline_numbers['trajectory_pass_rate']:+.3f} |",
        f"| step efficiency | {baseline_numbers['step_efficiency']:.3f} | {numbers['step_efficiency']:.3f} | {numbers['step_efficiency'] - baseline_numbers['step_efficiency']:+.3f} |",
        f"| total cost, 10 claims (USD) | {cost_before:.5f} | {cost_after:.5f} | {cost_after - cost_before:+.5f} |",
        f"| total tokens, 10 claims | {tokens_before} | {tokens_after} | {tokens_after - tokens_before:+d} |",
        f"| total wall clock, 10 claims (s) | {latency_before:.1f} | {latency_after:.1f} | {latency_after - latency_before:+.1f} |",
        "",
    ]

    if outcome_flips:
        lines.append("Outcome flips (a claim that passed/failed the outcome eval changed sides):")
        for claim_id, was, now in outcome_flips:
            lines.append(f"- `{claim_id}`: {'PASS' if was else 'FAIL'} -> {'PASS' if now else 'FAIL'}")
        lines.append("")

    if newly_budget_exceeded:
        lines.append(
            f"**Budget now fires where it did not before, on: {newly_budget_exceeded}** - the direct price of "
            "the tighter cap: a claim that needed its extra lap (the redirect leg or a deductible search) no "
            "longer gets it, and stops early instead of finishing late."
        )
        lines.append("")
    else:
        lines.append(
            "No claim newly tripped the budget - the tighter cap removed slack without removing a lap any "
            "claim actually needed to finish, in this run."
        )
        lines.append("")

    lines += [
        "## Regression check: every mode, before -> after",
        "",
        "| mode | before | after | |",
        "|---|---:|---:|---|",
    ]
    for mode, b, a, flag in regression_rows:
        lines.append(f"| {mode} | {b} | {a} | {flag} |")

    worse_or_new = [row for row in regression_rows if row[3] in ("WORSE", "new")]
    lines.append("")
    if worse_or_new:
        lines.append("Modes that got worse or newly appeared: " + ", ".join(f"`{row[0]}`" for row in worse_or_new))
    else:
        lines.append("No mode got worse and no new mode appeared - every mode checked above either improved or was unchanged.")

    report_path = OUT_DIR / "mitigation_report.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print()
    print(f"top mode {top_mode}: {before_top} -> {after_top}")
    print(f"cost: ${cost_before:.5f} -> ${cost_after:.5f}   tokens: {tokens_before} -> {tokens_after}   wall_clock: {latency_before:.1f}s -> {latency_after:.1f}s")
    print(f"outcome pass rate: {baseline_numbers['outcome_pass_rate']:.3f} -> {numbers['outcome_pass_rate']:.3f}")
    print(f"wrote {OUT_DIR / 'mitigated.csv'}")
    print(f"wrote {OUT_DIR / 'mitigated_summary.json'}")
    print(f"wrote {report_path}")
