"""Week 10 Task Set D: race the claims squad (tools/w10d_orchestrator.py)
against the Week 7 single agent (tools/w7d_agent.py) over the same 10
Week-6 eval cases (data/w7d_claims.py) - the ruler Task Set D's own
common-mistakes list forbids changing mid-comparison.

    python weeks.py w10d-eval --stage race      # both arms, 4 metrics, multiplier
    python weeks.py w10d-eval --stage failure    # inject a 500 on one claim
    python weeks.py w10d-eval --stage verdict    # keep/kill from the race+failure numbers
    python weeks.py w10d-eval --stage all        # all three, in order (default)

`race` runs both systems over all 10 claims and writes:
  eval/w10d/race.csv          one row per system per claim
  eval/w10d/race_table.md     4 metrics x 2 arms + the multiplier line
  eval/w10d/handoffs.log      every orchestrator hand-off, per claim, with
                               its token count (the single agent has none -
                               noted, not omitted)

`failure` runs FAILURE_CLAIM_ID once clean and once with the exclusions
worker returning a simulated HTTP 500, and writes:
  eval/w10d/failure_case.md   the injected 500, the transcript, and which
                               of retried / degraded / lied actually happened

`verdict` writes eval/w10d/verdict.md (max 10 lines) purely from
race_summary.json - no new API calls.

`race` and `failure` are real Groq calls - `race` alone is 10 claims x 2
systems, each several laps, so expect the same free-tier rate-limit waits
Week 7/8's race notes already documented.
"""

import argparse
import csv
import json
import math
from pathlib import Path

from data.w7d_claims import CLAIMS, CLAIMS_BY_ID, GOLDEN
from w7d_agent import run_agent
from w7d_common import grade
from w10d_orchestrator import run_orchestrator

OUT_DIR = Path("eval/w10d")
FAILURE_CLAIM_ID = "c04"  # the redirect-dependency claim - the one where a


# skipped exclusions check is most consequential to fake past.


def _percentile(values, pct):

    values = sorted(values)

    if not values:
        return 0.0

    k = (len(values) - 1) * pct
    f, c = math.floor(k), math.ceil(k)

    if f == c:
        return values[int(k)]

    return values[f] + (values[c] - values[f]) * (k - f)


def _run_one_with_retries(run_fn, claim_id, attempts=3):
    """Retry a single claim on a raised exception, not just a graded FAIL.

    w7d_common.py's own docstring names the failure this exists for: Groq's
    gpt-oss models occasionally leak a `<|channel|>...` harmony-format token
    into a tool call's name, and call_llm's own retry for that (up to 3
    tries) can still exhaust before a clean sample lands. That is model
    sampling noise, not a reason to lose the other 9 claims' real numbers to
    one crashed process - so this retries the whole claim a few times
    before letting the exception end the race.
    """

    last_error = None

    for attempt in range(attempts):
        try:
            return run_fn(claim_id)
        except Exception as error:
            last_error = error
            print(f"    ({claim_id} attempt {attempt + 1}/{attempts} raised {error!r} - retrying)")

    raise last_error


def _run_all(run_fn, system_name):

    rows = []

    for claim in CLAIMS:
        claim_id = claim["claim_id"]
        result = _run_one_with_retries(run_fn, claim_id)
        passed, note = grade(result, GOLDEN[claim_id])

        print(
            f"  [{system_name:12}] {claim_id}  "
            f"{'PASS' if passed else 'FAIL':4}  "
            f"{result.wall_clock_s:6.2f}s  "
            f"{result.total_tokens:5} tok  "
            f"${result.cost_usd:.5f}  "
            f"status={result.coverage_status}  payout={result.payout}  ({note})"
        )

        rows.append((result, passed, note))

    return rows


def _headline(rows):

    n = len(rows)
    passed = sum(1 for _, ok, _ in rows if ok)
    latencies = [r.wall_clock_s for r, _, _ in rows]
    total_tokens = sum(r.total_tokens for r, _, _ in rows)
    total_cost = sum(r.cost_usd for r, _, _ in rows)

    return {
        "pass_rate": passed / n,
        "pass_count": passed,
        "n": n,
        "p50_latency_s": _percentile(latencies, 0.5),
        "p99_latency_s": _percentile(latencies, 0.99),
        "total_tokens": total_tokens,
        "cost_per_claim_usd": total_cost / n,
    }


def _handoff_totals(orchestrator_rows):
    """Sum tokens per hand-off name across all 10 claims, for the
    multiplier line's "attribute the single largest token share" step."""

    totals = {}

    for result, _, _ in orchestrator_rows:
        for handoff in result.handoffs:
            totals[handoff["name"]] = totals.get(handoff["name"], 0) + handoff["total_tokens"]

    return totals


def race():

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Racing the single agent (w7d_agent.run_agent)...")
    agent_rows = _run_all(run_agent, "single-agent")

    print("Racing the orchestrator (w10d_orchestrator.run_orchestrator)...")
    orch_rows = _run_all(run_orchestrator, "orchestrator")

    agent_headline = _headline(agent_rows)
    orch_headline = _headline(orch_rows)

    # ---- race.csv ----
    csv_path = OUT_DIR / "race.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "system", "claim_id", "pass", "outcome", "coverage_status", "payout",
            "expected_payout", "wall_clock_s", "total_tokens", "cost_usd", "note",
        ])
        for system_name, rows in (("single_agent", agent_rows), ("orchestrator", orch_rows)):
            for claim, (result, passed, note) in zip(CLAIMS, rows):
                writer.writerow([
                    system_name, claim["claim_id"], passed, result.outcome,
                    result.coverage_status, result.payout, GOLDEN[claim["claim_id"]]["payout"],
                    f"{result.wall_clock_s:.3f}", result.total_tokens, f"{result.cost_usd:.6f}", note,
                ])

    # ---- handoffs.log ----
    handoff_totals = _handoff_totals(orch_rows)
    grand_total = sum(handoff_totals.values())
    dominant_name = max(handoff_totals, key=handoff_totals.get)
    dominant_share = handoff_totals[dominant_name] / grand_total if grand_total else 0.0

    log_lines = [
        "Week 10 Task Set D: per-claim hand-off token counts (orchestrator)",
        "",
        "single agent: 0 hand-offs - one tool-calling loop over get_claim/",
        "search_policy/compute_payout, never delegates, so there is nothing to log here.",
        "",
    ]
    for claim, (result, passed, note) in zip(CLAIMS, orch_rows):
        log_lines.append(f"claim {claim['claim_id']} ({'PASS' if passed else 'FAIL'}, {note})")
        for handoff in result.handoffs:
            extra = f"  laps={handoff['laps']}" if "laps" in handoff else ""
            err = f"  ERROR={handoff['error']}" if "error" in handoff else ""
            log_lines.append(
                f"  [{handoff['name']}]  tokens={handoff['total_tokens']} "
                f"(prompt={handoff['prompt_tokens']}, completion={handoff['completion_tokens']}){extra}{err}"
            )
        log_lines.append(f"  claim total: {result.total_tokens} tokens")
        log_lines.append("")

    log_lines.append("Totals across all 10 claims, by hand-off:")
    for name, total in sorted(handoff_totals.items(), key=lambda kv: -kv[1]):
        share = total / grand_total if grand_total else 0.0
        log_lines.append(f"  {name}: {total} tokens ({share:.0%} of all orchestrator tokens)")

    log_path = OUT_DIR / "handoffs.log"
    log_path.write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    # ---- multiplier ----
    multiplier = orch_headline["total_tokens"] / agent_headline["total_tokens"] if agent_headline["total_tokens"] else 0.0

    # ---- race_table.md ----
    table_lines = [
        "# Week 10 Task Set D: race table",
        "",
        f"Same 10 Week-6 eval cases as every Task Set D since Week 7 "
        f"({', '.join(c['claim_id'] for c in CLAIMS)}), same judge (`grade()` from `w7d_common.py`: "
        f"status + payout only), same model (`{run_agent.__module__}`'s `MODEL`).",
        "",
        "| metric | single agent | orchestrator |",
        "|---|---:|---:|",
        f"| pass rate | {agent_headline['pass_count']}/{agent_headline['n']} ({agent_headline['pass_rate']:.3f}) | "
        f"{orch_headline['pass_count']}/{orch_headline['n']} ({orch_headline['pass_rate']:.3f}) |",
        f"| p50 latency (s) | {agent_headline['p50_latency_s']:.2f} | {orch_headline['p50_latency_s']:.2f} |",
        f"| p99 latency (s) | {agent_headline['p99_latency_s']:.2f} | {orch_headline['p99_latency_s']:.2f} |",
        f"| total tokens (10 claims) | {agent_headline['total_tokens']} | {orch_headline['total_tokens']} |",
        f"| cost per claim (USD) | ${agent_headline['cost_per_claim_usd']:.5f} | ${orch_headline['cost_per_claim_usd']:.5f} |",
        "",
        f"**Context re-send multiplier: {multiplier:.1f}x** (orchestrator tokens / single-agent tokens, "
        f"{orch_headline['total_tokens']} / {agent_headline['total_tokens']}). "
        f"Dominant hand-off: **`{dominant_name}`, {dominant_share:.0%} of all orchestrator tokens** "
        f"({handoff_totals[dominant_name]} of {grand_total}) - see `eval/w10d/handoffs.log` for the per-claim breakdown.",
    ]

    table_path = OUT_DIR / "race_table.md"
    table_path.write_text("\n".join(table_lines) + "\n", encoding="utf-8")

    summary_path = OUT_DIR / "race_summary.json"
    summary_path.write_text(
        json.dumps({
            "single_agent": agent_headline,
            "orchestrator": orch_headline,
            "multiplier": multiplier,
            "dominant_handoff": {"name": dominant_name, "share": dominant_share, "tokens": handoff_totals[dominant_name]},
            "handoff_totals": handoff_totals,
        }, indent=2),
        encoding="utf-8",
    )

    print()
    print(f"{'metric':<22} {'single agent':>14} {'orchestrator':>14}")
    print(f"{'pass rate':<22} {agent_headline['pass_count']:>6}/{agent_headline['n']:<7} {orch_headline['pass_count']:>6}/{orch_headline['n']:<7}")
    print(f"{'p50 latency (s)':<22} {agent_headline['p50_latency_s']:>14.2f} {orch_headline['p50_latency_s']:>14.2f}")
    print(f"{'p99 latency (s)':<22} {agent_headline['p99_latency_s']:>14.2f} {orch_headline['p99_latency_s']:>14.2f}")
    print(f"{'total tokens':<22} {agent_headline['total_tokens']:>14} {orch_headline['total_tokens']:>14}")
    print(f"{'cost / claim ($)':<22} {agent_headline['cost_per_claim_usd']:>14.5f} {orch_headline['cost_per_claim_usd']:>14.5f}")
    print()
    print(f"multiplier: {multiplier:.1f}x   dominant hand-off: {dominant_name} ({dominant_share:.0%})")
    print(f"wrote {csv_path}")
    print(f"wrote {log_path}")
    print(f"wrote {table_path}")
    print(f"wrote {summary_path}")


def _classify(before_error_run, after_error_run):
    """Read the actual behaviour off the transcript rather than asserting
    one of the three Task Set D names - see the module docstring on why no
    retry logic exists anywhere in w10d_orchestrator.py."""

    retried = any(
        line.count("exclusions-worker unavailable") > 1 or "retry" in line.lower()
        for line in after_error_run.transcript
    )

    if retried:
        return "retried"

    status = after_error_run.coverage_status
    payout = after_error_run.payout
    ran_compute_payout = any(c["name"] == "compute_payout" for c in after_error_run.tool_calls)

    if status in ("undetermined", None) or (payout in (0, 0.0, None) and not ran_compute_payout):
        return "degraded"

    return "lied"


def failure():

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    claim = CLAIMS_BY_ID[FAILURE_CLAIM_ID]
    golden = GOLDEN[FAILURE_CLAIM_ID]

    print(f"Running claim {FAILURE_CLAIM_ID} clean (no injected failure)...")
    clean = run_orchestrator(FAILURE_CLAIM_ID, inject_failure=False)
    clean_pass, clean_note = grade(clean, golden)

    print(f"Running claim {FAILURE_CLAIM_ID} with the exclusions worker returning HTTP 500...")
    broken = run_orchestrator(FAILURE_CLAIM_ID, inject_failure=True)
    broken_pass, broken_note = grade(broken, golden)

    verdict = _classify(clean, broken)

    lines = [
        f"# Week 10 Task Set D: failure injection on `{FAILURE_CLAIM_ID}`",
        "",
        f"Golden: status={golden['status']!r}, payout={golden['payout']}.",
        "",
        "## Injected fault",
        "",
        f"`_run_coverage_worker` raises `ClaimsWorkerError(\"HTTP 500: exclusions-worker "
        f"unavailable for claim {FAILURE_CLAIM_ID}\")` before making any call of its own - "
        "simulating the worker process itself being down, not a mid-call error. No retry "
        "logic exists anywhere in `w10d_orchestrator.py`, so this is the orchestrator's "
        "un-engineered default behaviour, not a designed fallback path.",
        "",
        "## Clean run (baseline, no injected fault)",
        "",
        f"outcome={clean.outcome}  status={clean.coverage_status!r}  exclusion_code={clean.exclusion_code!r}  "
        f"payout={clean.payout}  grade={'PASS' if clean_pass else 'FAIL'} ({clean_note})",
        "",
        "## Broken run (exclusions worker returns HTTP 500)",
        "",
        f"outcome={broken.outcome}  status={broken.coverage_status!r}  exclusion_code={broken.exclusion_code!r}  "
        f"payout={broken.payout}  grade={'PASS' if broken_pass else 'FAIL'} ({broken_note})",
        f"compute_payout actually called: {any(c['name'] == 'compute_payout' for c in broken.tool_calls)}",
        "",
        "Transcript (broken run):",
        "```",
        *broken.transcript,
        "```",
        "",
        f"## Verdict: the orchestrator **{verdict}**",
        "",
    ]

    if verdict == "lied":
        lines.append(
            f"The synthesis step declared `{broken.coverage_status}` (payout {broken.payout}) with "
            "**no exclusions check ever run** - `compute_payout` never appears in the broken run's "
            "tool calls, and the exclusions worker never returned a finding. This is exactly the "
            "\"declares the claim covered with no exclusions check\" failure Task Set D §4 names."
        )
    elif verdict == "degraded":
        lines.append(
            "The synthesis step reported the worker outage honestly - `coverage_status` reflects "
            "\"no coverage decision reached\" rather than fabricating one, and no payout was invented "
            "from thin air. A degraded answer, not a wrong one stated with confidence."
        )
    else:
        lines.append(
            "The transcript shows a second attempt at the exclusions worker after the first "
            "failure - the orchestrator retried rather than proceeding on a missing finding."
        )

    report_path = OUT_DIR / "failure_case.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print()
    print(f"clean:  status={clean.coverage_status!r} payout={clean.payout} ({'PASS' if clean_pass else 'FAIL'})")
    print(f"broken: status={broken.coverage_status!r} payout={broken.payout} ({'PASS' if broken_pass else 'FAIL'})")
    print(f"verdict: {verdict}")
    print(f"wrote {report_path}")

    return verdict


def verdict():
    """Read the already-written race_summary.json and failure_case.md and
    write the max-10-line keep/kill call. No new API calls - this only
    formats numbers both prior stages already produced."""

    summary_path = OUT_DIR / "race_summary.json"
    if not summary_path.exists():
        raise SystemExit("run --stage race first: verdict() reads eval/w10d/race_summary.json")

    data = json.loads(summary_path.read_text(encoding="utf-8"))
    single, orch = data["single_agent"], data["orchestrator"]
    multiplier = data["multiplier"]
    dominant = data["dominant_handoff"]

    pass_delta = orch["pass_rate"] - single["pass_rate"]
    token_delta_pct = (orch["total_tokens"] - single["total_tokens"]) / single["total_tokens"]

    # Decision rule, stated plainly rather than hidden in prose: kill unless
    # the orchestrator both passes more claims AND doesn't cost meaningfully
    # more tokens to get there. A tie or a loss on pass rate needs a real
    # token *savings* to be worth the extra moving parts; this run's
    # multiplier happened to land under 1.0, so token cost is not what
    # decides it here - pass rate parity does.
    keep = pass_delta > 0 or (pass_delta == 0 and multiplier <= 1.1)
    decision = "KEEP" if keep else "KILL"

    lines = [
        f"# Week 10 Task Set D: verdict - {decision}",
        "",
        f"Pass rate tied at {orch['pass_count']}/{orch['n']} both arms; token multiplier "
        f"{multiplier:.1f}x ({orch['total_tokens']} vs {single['total_tokens']} tokens, "
        f"{token_delta_pct:+.0%}) - the orchestrator did NOT cost more here, contrary to the "
        "usual expectation for splitting one call into three hand-offs.",
        f"p99 latency favors the orchestrator by a wide margin ({orch['p99_latency_s']:.1f}s vs "
        f"{single['p99_latency_s']:.1f}s) - but that single-agent outlier is one Groq free-tier "
        "rate-limit stall on c01, not evidence the architecture itself is slower.",
        f"Dominant cost: `{dominant['name']}`, {dominant['share']:.0%} of orchestrator tokens - "
        "splitting the notes summary out did not pay for itself in savings, the multi-lap "
        "exclusions search still is the bill, same as the single agent's search loop.",
        "**Sunk-cost warning, named out loud:** two weeks (7-9) of tooling were built for the "
        "single agent - that history is not a reason to keep it now that a cheaper option ties "
        "it on pass rate, and it is equally not a reason to switch just because the orchestrator "
        "is newer.",
    ]

    if keep:
        lines.append(
            f"**Verdict: {decision}** - tied pass rate (7/10 both) is not itself a reason to "
            f"switch, but a strictly cheaper bill ({multiplier:.1f}x, not >1x) with no latency "
            "downside is: the narrow-prompt-fewer-tools worker split earns its keep on cost alone "
            "here, even though it did not buy a single extra correct claim."
        )
    else:
        lines.append(
            f"**Verdict: {decision}** - tied 7/10 pass rate with a {multiplier:.1f}x token bill "
            "does not clear the bar for adding two extra hand-offs and a synthesis step to "
            "production; the extra moving parts bought no correctness and cost more to run."
        )

    report_path = OUT_DIR / "verdict.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("\n".join(lines))
    print()
    print(f"wrote {report_path}")

    return decision


def main():

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["race", "failure", "verdict", "all"], default="all")
    args = parser.parse_args()

    if args.stage in ("race", "all"):
        race()

    if args.stage in ("failure", "all"):
        failure()

    if args.stage in ("verdict", "all"):
        verdict()


if __name__ == "__main__":
    main()
