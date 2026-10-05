"""The integrated eval: 31 claims through the one entry point, scored by code.

    python weeks.py w12 run     --label main [--cases w01,w02] [--no-date-filter]
    python weeks.py w12 score   --label main
    python weeks.py w12 report  --label main      # taxonomy + trajectory + per-boundary

Assertions only. Every check below is deterministic over the referral the
system emitted and the answer key in data/w12_claims.py, so a failure is a
number and a trace id, not an opinion. The judge (w12_audit.py) is a second
instrument for the one property assertions cannot see - whether the prose is
faithful to the wording - and is reported separately with its agreement
against hand labels.

`run` is resumable: each finished case is written to disk immediately and a
re-run skips it, because a run is ~an hour on the rate-limited free tier
and losing 25 finished cases to a crash on the 26th is how evals stop being
re-run.
"""

import argparse
import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from data.w12_claims import CLAIMS, CLAIMS_BY_CASE
from data.w12_wordings import POLICIES
from w12_guard import scan_prose, referral_prose
from w12_inforce import edition_in_force, editions_for_product, limits_for

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "eval" / "w12"

EXPECTED_REASON = {"lapsed": "policy_not_in_force", "no_edition": "no_wording_in_force"}


def run_path(label):
    return OUT_DIR / f"run_{label}.json"


# ============================================================
# RUN
# ============================================================

def stage_run(args):

    from w7d_common import Budget
    from w11_obs import RequestSink
    from w12_agent import TriageSession

    if args.no_date_filter:
        os.environ["W12_DATE_FILTER"] = "0"

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    path = run_path(args.label)
    done = json.loads(path.read_text()) if path.exists() and not args.fresh else {}

    log_path = REPO_ROOT / "traces" / f"w12_requests_{args.label}.jsonl"

    if args.fresh:
        log_path.unlink(missing_ok=True)

    sink = RequestSink(log_path)
    wanted = args.cases.split(",") if args.cases else [c["case_id"] for c in CLAIMS]

    print(f"starting MCP servers (the policy server warms its engine first)...", flush=True)
    started = time.perf_counter()
    session = TriageSession(sink=sink)
    boot_s = round(time.perf_counter() - started, 1)
    print(f"discovered at runtime: {session.discovered()}  (boot {boot_s}s)", flush=True)

    retrieval_version = "hybrid-nofilter" if args.no_date_filter else "hybrid-datefilter-v2"

    try:
        for case_id in wanted:

            if case_id in done:
                print(f"  {case_id}: already done, skipping", flush=True)
                continue

            claim = CLAIMS_BY_CASE[case_id]
            began = time.perf_counter()

            # Rate-limit waits of minutes are normal on the free tier and must
            # not be scored as a failed case: lift the wall-clock cap (the
            # lap, token and cost caps stay) and refuse to record a run that
            # still hit it. Same decision, same reason as Week 11's suite.
            trace, referral = session.run(
                claim["claim_number"], question=claim["question"],
                user_id="eval", case_id=case_id, retrieval_version=retrieval_version,
                registry_claim=claim,
                budget=Budget(max_iterations=10, max_tokens=24000, max_cost_usd=0.05,
                              max_wall_clock_s=6 * 3600),
            )

            if trace.outcome == "budget_exceeded:wall_clock":
                raise SystemExit(f"{case_id}: wall-clock budget hit; not recording it as a result")

            totals = trace.totals()

            done[case_id] = {
                "case_id": case_id,
                "trace_id": trace.trace_id,
                "outcome": trace.outcome,
                "referral": referral,
                "tool_calls": trace.tool_calls,
                "server_spans": trace.server_spans,
                "context_ids": trace.context_ids,
                "totals": totals,
                "wall_s": round(time.perf_counter() - began, 1),
                "boot_s": boot_s,
                "retrieval_version": retrieval_version,
            }

            path.write_text(json.dumps(done, indent=2, default=str), encoding="utf-8")

            verdict = score_case(claim, done[case_id])
            failed = [k for k, v in verdict.items() if not v]
            print(f"  {case_id}: {trace.outcome:<10} {'PASS' if not failed else 'FAIL ' + ','.join(failed)} "
                  f"{trace.trace_id} {done[case_id]['wall_s']}s ${totals['cost_usd']:.5f}", flush=True)

    finally:
        session.close()

    stage_score(args)


# ============================================================
# SCORING
# ============================================================

def _norm(clause):
    return str(clause or "").strip().upper()


def score_case(claim, run):
    """{assertion_name: bool} for one case. All must be True to pass."""

    truth = claim["truth"]
    referral = run.get("referral")
    names = [call["name"] for call in run["tool_calls"]]

    checks = {"referral_made": bool(referral and referral.get("route") == "adjuster")}

    if not referral:
        return checks

    product = POLICIES[claim["policy_number"]]["product"]
    citations = referral.get("citations") or []

    checks["no_decision_language"] = not any(scan_prose(t) for _, t in referral_prose(referral))
    checks["in_force_correct"] = referral.get("in_force") == truth["in_force"]
    checks["reason_code_correct"] = (
        referral.get("reason_code") == EXPECTED_REASON.get(truth["boundary"], "wording_relevant")
    )

    check_at = names.index("check_coverage_in_force") if "check_coverage_in_force" in names else None
    search_at = names.index("search_policy_wording") if "search_policy_wording" in names else None

    checks["in_force_checked_first"] = check_at is not None and (search_at is None or check_at < search_at)

    if truth["boundary"] == "lapsed":
        checks["no_wording_cited"] = not citations
        return checks

    if truth["boundary"] == "no_edition":
        checks["no_stale_wording_cited"] = not any(c["form_number"] == "HO-0850" for c in citations)
        checks["no_figures_invented"] = referral.get("figures") is None
        return checks

    in_force_editions = editions_for_product(product, claim["loss_date"])

    checks["no_stale_edition"] = bool(citations) and all(
        c["edition_date"] == in_force_editions.get(c["form_number"]) for c in citations
    )
    checks["edition_correct"] = all(
        any(c["form_number"] == f and c["edition_date"] == e for c in citations)
        for f, e, _ in truth["expected_cites"]
    )
    checks["clause_cited"] = all(
        any(c["form_number"] == f and c["edition_date"] == e and _norm(c["clause"]) == _norm(cl)
            for c in citations)
        for f, e, cl in truth["expected_cites"]
    )
    checks["loss_date_on_citations"] = bool(citations) and all(
        c.get("loss_date_resolved") == claim["loss_date"] for c in citations
    )
    checks["citations_grounded"] = bool(citations) and all(c.get("grounded") for c in citations)

    expected = limits_for(claim["policy_number"], claim["loss_date"], truth["peril_class"])
    figures = referral.get("figures") or {}

    checks["figures_correct"] = (
        "error" not in expected
        and all(figures.get(k) == expected[k] for k in ("deductible", "sub_limit", "policy_limit"))
    )

    return checks


def load_run(label):
    path = run_path(label)

    if not path.exists():
        sys.exit(f"{path} not found - `run` first")

    return json.loads(path.read_text())


def stage_score(args):

    run = load_run(args.label)
    rows = []

    for case_id, result in run.items():
        claim = CLAIMS_BY_CASE[case_id]
        verdict = score_case(claim, result)
        rows.append((case_id, claim["truth"]["boundary"], verdict, result))

    passed = sum(1 for _, _, v, _ in rows if all(v.values()))

    lines = [f"INTEGRATED SUITE  label={args.label}  n={len(rows)}  "
             f"retrieval={next(iter(run.values()))['retrieval_version']}", ""]

    for case_id, boundary, verdict, result in rows:
        failed = [k for k, v in verdict.items() if not v]
        lines.append(f"{case_id}  {boundary:<10} {'PASS' if not failed else 'FAIL'}  "
                     f"{','.join(failed)}  {result['trace_id']}")

    lines += ["", f"PASS {passed}/{len(rows)}", "", "pass rate by boundary class (the number the brief asks for):"]

    by = defaultdict(list)

    for _, boundary, verdict, _ in rows:
        by[boundary].append(all(verdict.values()))

    for boundary, results in sorted(by.items()):
        lines.append(f"  {boundary:<10} {sum(results)}/{len(results)}")

    lines += ["", "pass rate by assertion:"]

    per = defaultdict(list)

    for _, _, verdict, _ in rows:
        for name, ok in verdict.items():
            per[name].append(ok)

    for name, results in sorted(per.items()):
        lines.append(f"  {name:<26} {sum(results)}/{len(results)}")

    text = "\n".join(lines)
    print("\n" + text)
    (OUT_DIR / f"suite_{args.label}.txt").write_text(text + "\n", encoding="utf-8")

    return rows


# ============================================================
# TAXONOMY
# ============================================================

# assertion -> (mode name, severity, origin)
MODES = {
    "referral_made": ("no_referral_produced", "high", "inherited"),
    "no_decision_language": ("decision_language_in_output", "critical", "inherited"),
    "no_stale_edition": ("wrong_edition_cited", "critical", "inherited"),
    "edition_correct": ("expected_edition_not_cited", "high", "inherited"),
    "clause_cited": ("right_edition_wrong_or_missing_clause", "medium", "inherited"),
    "in_force_correct": ("in_force_misjudged", "high", "inherited"),
    "reason_code_correct": ("wrong_referral_reason", "medium", "inherited"),
    "figures_correct": ("limits_figures_wrong", "high", "inherited"),
    "citations_grounded": ("ungrounded_citation", "high", "inherited"),
    "loss_date_on_citations": ("loss_date_not_carried_to_citation", "medium", "integration"),
    "in_force_checked_first": ("search_before_in_force_check", "medium", "integration"),
    "no_wording_cited": ("wording_cited_for_lapsed_policy", "high", "inherited"),
    "no_stale_wording_cited": ("wording_cited_where_none_in_force", "critical", "inherited"),
    "no_figures_invented": ("figures_invented_without_edition", "high", "inherited"),
}


def integration_signals(run):
    """
    Failure shapes that exist only because the parts were joined.

    These are not assertion failures: a request can pass every assertion
    and still show one. They are mined from the tool-call log, because that
    is where a seam shows - a recoverable server error the model hit and
    fixed (cost: a lap), a guard that had to rewrite the model's prose, a
    span whose trace id did not come back across the hop.
    """

    signals = defaultdict(list)

    for case_id, result in run.items():

        for call in result["tool_calls"]:
            if not call["ok"] and call["name"] == "search_policy_wording" \
                    and not call["args"].get("loss_date"):
                signals["loss_date_dropped_at_mcp_hop"].append((case_id, result["trace_id"]))
            elif not call["ok"]:
                signals["mcp_call_rejected"].append((case_id, result["trace_id"]))

        seen = set()

        for call in result["tool_calls"]:
            key = (call["name"], json.dumps(call["args"], sort_keys=True))
            if key in seen:
                signals["redundant_tool_call_absorbed" if call.get("cached")
                        else "redundant_tool_call"].append((case_id, result["trace_id"]))
                break
            seen.add(key)

        if result["outcome"].startswith("error:"):
            signals["provider_rejected_model_tool_call"].append((case_id, result["trace_id"]))

        referral = result.get("referral") or {}

        if (referral.get("guard") or {}).get("triggered"):
            signals["guard_rewrote_decision_language"].append((case_id, result["trace_id"]))

        if len(result["server_spans"]) != sum(
                1 for c in result["tool_calls"] if c["server"] and not c.get("cached")):
            signals["server_span_missing_after_hop"].append((case_id, result["trace_id"]))

        if any(s.get("trace_id") != result["trace_id"] for s in result["server_spans"]):
            signals["trace_id_lost_across_hop"].append((case_id, result["trace_id"]))

        sigs = [c["args"].get("peril_class") for c in result["tool_calls"] if c["name"] == "get_limits"]
        claim = CLAIMS_BY_CASE[case_id]

        if sigs and claim["truth"]["in_force"] and sigs[-1] != claim["truth"]["peril_class"]:
            signals["peril_misclassified_before_limits_lookup"].append((case_id, result["trace_id"]))

    return signals


def stage_taxonomy(args):

    run = load_run(args.label)
    rows = stage_score_quiet(run)
    n = len(rows)

    counts = defaultdict(list)

    for case_id, _, verdict, result in rows:
        for name, ok in verdict.items():
            if not ok:
                counts[name].append((case_id, result["trace_id"]))

    signals = integration_signals(run)

    lines = [f"# Error taxonomy - integrated system, n={n} requests (label `{args.label}`)", "",
             "Frequency is the share of the n requests exhibiting the mode; one request can exhibit several. "
             "Modes marked **integration** only exist because the parts were joined.", "",
             "| # | mode | origin | severity | freq | n | example trace id |",
             "|---|---|---|---|---|---|---|"]

    entries = []

    for name, hits in counts.items():
        mode, severity, origin = MODES[name]
        entries.append((mode, origin, severity, len(hits), hits[0][1]))

    sig_meta = {
        "loss_date_dropped_at_mcp_hop": "high",
        "mcp_call_rejected": "low",
        "guard_rewrote_decision_language": "high",
        "server_span_missing_after_hop": "medium",
        "trace_id_lost_across_hop": "high",
        "peril_misclassified_before_limits_lookup": "high",
        "redundant_tool_call": "low",
        "redundant_tool_call_absorbed": "low",
        "provider_rejected_model_tool_call": "high",
    }

    for name, hits in signals.items():
        entries.append((name, "integration", sig_meta[name], len(hits), hits[0][1]))

    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    entries.sort(key=lambda e: (order[e[2]], -e[3]))

    for i, (mode, origin, severity, count, trace_id) in enumerate(entries, 1):
        lines.append(f"| {i} | {mode} | **{origin}** | {severity} | {count / n:.0%} | {count}/{n} | `{trace_id}` |")

    if not entries:
        lines.append("| - | none observed | - | - | 0% | 0 | - |")

    text = "\n".join(lines)
    print(text)
    (OUT_DIR / f"taxonomy_{args.label}.md").write_text(text + "\n", encoding="utf-8")


def stage_score_quiet(run):
    rows = []

    for case_id, result in run.items():
        claim = CLAIMS_BY_CASE[case_id]
        rows.append((case_id, claim["truth"]["boundary"], score_case(claim, result), result))

    return rows


# ============================================================
# TRAJECTORY
# ============================================================

def trajectory_of(claim, run):
    """
    Grade the path, not the answer: was each tool call the right call.

    A call is *correct* when it is a sensible call at that point with the
    right arguments: the loss date and policy number it passes are the
    claim's own, the product is the policy's, and wording is not searched
    for a policy already shown not to be in force. Required calls missing
    from the path fail the trajectory outright.
    """

    truth = claim["truth"]
    product = POLICIES[claim["policy_number"]]["product"]
    calls = run["tool_calls"]
    graded = []
    seen_check = False
    in_force_known = None

    for call in calls:

        # Intake is the harness's step, not a choice the model made, so it
        # is not part of tool-choice accuracy - counting a call the model
        # never chose would flatter the number.
        if call.get("actor") == "harness":
            continue

        name, args, ok = call["name"], call["args"], True
        why = ""

        if name == "get_fnol":
            ok = args.get("claim_number") == claim["claim_number"]
            why = "wrong claim number" if not ok else ""

        elif name == "check_coverage_in_force":
            ok = (args.get("policy_number") == claim["policy_number"]
                  and args.get("loss_date") == claim["loss_date"])
            why = "wrong policy/loss date" if not ok else ""
            seen_check = True
            in_force_known = truth["in_force"]

        elif name == "lookup_policy":
            ok = args.get("policy_number") == claim["policy_number"]

        elif name == "search_policy_wording":
            ok = (seen_check and in_force_known is not False
                  and args.get("loss_date") == claim["loss_date"]
                  and args.get("product") == product)
            why = ("searched before the in-force check" if not seen_check
                   else "searched a policy that was not in force" if in_force_known is False
                   else "wrong loss date/product")
            why = "" if ok else why

        elif name == "get_limits":
            ok = (seen_check and in_force_known is not False
                  and args.get("policy_number") == claim["policy_number"]
                  and args.get("loss_date") == claim["loss_date"]
                  and args.get("peril_class") == truth["peril_class"])
            why = "" if ok else "wrong peril/date/policy, or policy not in force"

        elif name == "refer_to_adjuster":
            ok = True

        graded.append({"name": name, "correct": ok, "why": why})

    names = [c["name"] for c in calls]
    required = ["get_fnol", "check_coverage_in_force", "refer_to_adjuster"]

    if truth["in_force"] and truth["boundary"] != "no_edition":
        required += ["search_policy_wording", "get_limits"]
    elif truth["boundary"] == "no_edition":
        required += ["search_policy_wording"]

    missing = [r for r in required if r not in names]
    path_ok = all(g["correct"] for g in graded) and not missing

    return {"graded": graded, "missing": missing, "path_ok": path_ok}


def stage_trajectory(args):

    run = load_run(args.label)
    rows = stage_score_quiet(run)

    pooled_ok = pooled_total = 0
    outcome_pass = trajectory_pass = both = right_outcome_wrong_path = right_path_wrong_outcome = 0
    per_case = []

    for case_id, _, verdict, result in rows:

        traj = trajectory_of(CLAIMS_BY_CASE[case_id], result)
        outcome_ok = all(verdict.values())

        pooled_ok += sum(g["correct"] for g in traj["graded"])
        pooled_total += len(traj["graded"])
        outcome_pass += outcome_ok
        trajectory_pass += traj["path_ok"]
        both += outcome_ok and traj["path_ok"]
        right_outcome_wrong_path += outcome_ok and not traj["path_ok"]
        right_path_wrong_outcome += traj["path_ok"] and not outcome_ok

        per_case.append((case_id, outcome_ok, traj["path_ok"], traj["missing"],
                         [g["why"] for g in traj["graded"] if not g["correct"]], result["trace_id"]))

    n = len(rows)
    gap = outcome_pass / n - trajectory_pass / n

    lines = [f"# Trajectory eval - integrated agent, n={n} cases (label `{args.label}`)", "",
             f"- **tool-choice accuracy:** {pooled_ok}/{pooled_total} = {pooled_ok / max(pooled_total, 1):.1%} of tool calls correct",
             f"- **outcome pass:** {outcome_pass}/{n} = {outcome_pass / n:.1%}",
             f"- **trajectory pass** (every call right, no required call missing): {trajectory_pass}/{n} = {trajectory_pass / n:.1%}",
             f"- **outcome-vs-trajectory gap:** {gap * 100:+.1f} points (outcome minus trajectory)",
             f"- right outcome by the wrong path: {right_outcome_wrong_path}; "
             f"right path to the wrong outcome: {right_path_wrong_outcome}; both right: {both}", "",
             "| case | outcome | path | missing | wrong calls | trace id |", "|---|---|---|---|---|---|"]

    for case_id, outcome_ok, path_ok, missing, wrong, trace_id in per_case:
        lines.append(f"| {case_id} | {'pass' if outcome_ok else 'FAIL'} | {'ok' if path_ok else 'FAIL'} | "
                     f"{', '.join(missing) or '-'} | {'; '.join(wrong) or '-'} | `{trace_id}` |")

    text = "\n".join(lines)
    print(text)
    (OUT_DIR / f"trajectory_{args.label}.md").write_text(text + "\n", encoding="utf-8")


# ============================================================

def main():

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["run", "score", "taxonomy", "trajectory"])
    parser.add_argument("--label", default="main")
    parser.add_argument("--cases", default=None)
    parser.add_argument("--no-date-filter", action="store_true")
    parser.add_argument("--fresh", action="store_true")
    args = parser.parse_args()

    {"run": stage_run, "score": stage_score,
     "taxonomy": stage_taxonomy, "trajectory": stage_trajectory}[args.stage](args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
