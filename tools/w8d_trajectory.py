"""Trajectory grading for the Week 8 claims-agent eval: did the run take a
path that actually earns its answer, not just reach the right number.

Reuses tools/w7d_agent.py's run_agent, tools/w7d_claims_tools.py's tools and
tools/w7d_common.py's outcome grade() unchanged - Task Set D is a new lens
on the Week 7 agent, not a new agent. The one new piece of data is
tools/data/w8d_expected_trajectories.py's EXPECTED, which says what a
correct path looks like per claim; everything here checks a real RunResult
against that spec.

A failure mode taxonomy (the "Week-8 zoo", scoped to what this agent can
actually do wrong with three tools):

  premature_termination  compute_payout ran before every required_forms
                          entry had been covered by an earlier search - the
                          "reached the payout without ever opening the
                          exclusions" failure Task Set D §1 names.
  missing_required_form   at least one search ran, but never scoped to (or
                          covered by a null/global search over) a form the
                          golden answer's clause actually lives on.
  self_correction         more than one compute_payout call for the same
                          claim - the agent re-decided mid-trajectory.
  redundant_call          an exact duplicate tool call (same name, same
                          arguments) - wasted, not wrong.
  hallucinated_argument   a tool call or the final answer referenced a
                          claim, form or exclusion code that no tool result
                          in this trajectory actually returned.
  step_overrun            more tool calls than the shortest accepted shape
                          needed - not necessarily wrong, but not free.
  budget_exceeded         one of the four Task Set D budgets fired.
  error_outcome           the run did not produce a parseable final answer.
"""

import json
import re
import statistics

from data.w7d_claims import CLAIMS_BY_ID, GOLDEN
from data.w8d_expected_trajectories import EXPECTED
from w7d_common import grade
from w7d_policy_corpus import FORM_NUMBERS

# Same shape as w7d_policy_corpus.AMOUNT_RE - kept as an independent copy
# because this module grades what the *agent* was shown, and re-deriving it
# from the tool's own return values (not importing the corpus's internal
# flag) is what proves the grounding check is reading the same evidence the
# model had, not a shortcut into the corpus's private index.
AMOUNT_RE = re.compile(r"\$[\d,]+|\b\d+\s*percent\b|\(\d+%\)")


def tool_sequence(result):
    return tuple(call["name"] for call in result.tool_calls)


def _search_calls(result):
    return [call for call in result.tool_calls if call["name"] == "search_policy"]


def _compute_calls(result):
    return [call for call in result.tool_calls if call["name"] == "compute_payout"]


def covered_forms(result):
    """Form numbers actually opened by a search in this trajectory.

    A null/global search_policy call (form_number omitted or None) covers
    every form - it is a legitimate way to reach a required form, just a
    less targeted one, so it counts here rather than being treated as
    covering nothing.
    """

    forms = set()

    for call in _search_calls(result):
        scope = call["arguments"].get("form_number")
        if scope is None:
            return set(FORM_NUMBERS)
        forms.add(scope)

    return forms


def _all_evidence_text(result, upto_index=None):
    """Every match's clause label + text seen in tool results so far.

    upto_index limits this to calls strictly before a given tool call, for
    checking whether a later call (or the final answer) is grounded in
    something already returned, not in something that arrives afterwards.
    """

    calls = result.tool_calls if upto_index is None else result.tool_calls[:upto_index]
    chunks = []

    for call in calls:
        if call["name"] != "search_policy":
            continue
        for match in call["result"].get("matches", []):
            chunks.append(f"{match.get('clause', '')} {match.get('text', '')}")

    return "\n".join(chunks)


def classify_calls(claim_id, result):
    """Per-call tool-choice correctness, in trajectory order.

    Returns a list of {index, name, arguments, correct, reason}. Pooled
    across all 10 claims this is the tool-choice accuracy numerator/
    denominator - see headline_numbers().
    """

    spec = EXPECTED[claim_id]
    calls = result.tool_calls
    classified = []
    seen_signatures = set()
    forms_covered_so_far = set()
    compute_seen = False

    for i, call in enumerate(calls):
        name, args, tool_result = call["name"], call["arguments"], call["result"]
        signature = (name, json.dumps(args, sort_keys=True))
        correct, reason = True, "ok"

        if "error" in tool_result:
            correct, reason = False, f"tool rejected the call: {tool_result['error']}"

        elif name == "get_claim":
            if i != 0:
                correct, reason = False, "get_claim called after lap 1 - the claim was already on file"
            elif args.get("claim_id") != claim_id:
                correct, reason = False, f"fetched claim {args.get('claim_id')!r}, not {claim_id!r}"

        elif name == "search_policy":
            if signature in seen_signatures:
                correct, reason = False, "exact duplicate search (same query, same form)"
            else:
                scope = args.get("form_number")
                forms_covered_so_far |= set(FORM_NUMBERS) if scope is None else {scope}

        elif name == "compute_payout":
            if compute_seen:
                correct, reason = False, "second compute_payout call for the same claim (self-correction)"
            elif not (spec["required_forms"] <= forms_covered_so_far):
                missing = spec["required_forms"] - forms_covered_so_far
                correct, reason = False, f"computed payout before searching {sorted(missing)}"
            compute_seen = True

        seen_signatures.add(signature)
        classified.append({"index": i, "name": name, "arguments": args, "correct": correct, "reason": reason})

    return classified


def argument_checks(claim_id, result):
    """Per-call argument validity, plus one pseudo-check on the final
    answer's exclusion_code - fluent fiction if no search result in the
    trajectory ever returned it.

    Returns a list of {name, valid, reason}.
    """

    claim = CLAIMS_BY_ID[claim_id]
    checks = []

    for i, call in enumerate(result.tool_calls):
        name, args, tool_result = call["name"], call["arguments"], call["result"]

        if "error" in tool_result:
            checks.append({"name": name, "valid": False, "reason": tool_result["error"]})
            continue

        if name == "get_claim":
            checks.append({"name": name, "valid": args.get("claim_id") == claim_id, "reason": "claim_id"})

        elif name == "search_policy":
            scope = args.get("form_number")
            checks.append({"name": name, "valid": scope is None or scope in FORM_NUMBERS, "reason": "form_number"})

        elif name == "compute_payout":
            valid = args.get("claim_id") == claim_id
            reason = "claim_id"

            if valid and args.get("claim_status") == "covered":
                loss_ok = args.get("loss_amount") == claim["reported_loss_amount"]
                deductible_ok = (
                    not EXPECTED[claim_id]["needs_deductible_grounding"]
                    or bool(AMOUNT_RE.search(_all_evidence_text(result, upto_index=i)))
                )
                valid, reason = loss_ok and deductible_ok, "loss_amount/deductible grounding"

            checks.append({"name": name, "valid": valid, "reason": reason})

    exclusion_code = (result.raw_final or {}).get("exclusion_code")
    if exclusion_code:
        grounded = exclusion_code in _all_evidence_text(result)
        checks.append({"name": "final_answer.exclusion_code", "valid": grounded, "reason": exclusion_code})

    return checks


def failure_modes(claim_id, result):

    modes = set()

    if result.outcome == "budget_exceeded":
        modes.add("budget_exceeded")
        return modes

    if result.outcome != "completed":
        modes.add("error_outcome")
        return modes

    spec = EXPECTED[claim_id]
    sequence = tool_sequence(result)
    classified = classify_calls(claim_id, result)
    checks = argument_checks(claim_id, result)

    if _compute_calls(result) and not any(c["name"] == "search_policy" for c in result.tool_calls):
        modes.add("premature_termination")
    elif not (spec["required_forms"] <= covered_forms(result)):
        modes.add("missing_required_form")
    elif any(not c["correct"] and "computed payout before searching" in c["reason"] for c in classified):
        modes.add("premature_termination")

    if len(_compute_calls(result)) > 1:
        modes.add("self_correction")

    if any(not c["correct"] and "duplicate" in c["reason"] for c in classified):
        modes.add("redundant_call")

    if any(not c["valid"] for c in checks):
        modes.add("hallucinated_argument")

    if len(sequence) > spec["min_steps"]:
        modes.add("step_overrun")

    return modes


def shape_ok(claim_id, result):
    return tool_sequence(result) in EXPECTED[claim_id]["accepted_shapes"]


def trajectory_pass(claim_id, result):
    """Strict pass: right shape, right forms opened, nothing hallucinated.

    Deliberately independent of grade() (the outcome check) - see
    headline_numbers()'s gap and run_report()'s named right-answer-wrong-
    path case for why the two are asked to disagree on purpose.
    """

    if result.outcome != "completed":
        return False, "did not complete"

    if not shape_ok(claim_id, result):
        return False, f"tool sequence {tool_sequence(result)} not an accepted shape"

    if not (EXPECTED[claim_id]["required_forms"] <= covered_forms(result)):
        missing = EXPECTED[claim_id]["required_forms"] - covered_forms(result)
        return False, f"never searched {sorted(missing)}"

    bad_checks = [c for c in argument_checks(claim_id, result) if not c["valid"]]
    if bad_checks:
        return False, f"ungrounded: {bad_checks[0]['name']} ({bad_checks[0]['reason']})"

    return True, "ok"


def per_claim_report(claim_id, result):

    outcome_passed, outcome_note = grade(result, GOLDEN[claim_id])
    trajectory_passed, trajectory_note = trajectory_pass(claim_id, result)
    classified = classify_calls(claim_id, result)
    checks = argument_checks(claim_id, result)

    return {
        "claim_id": claim_id,
        "dependency": CLAIMS_BY_ID[claim_id]["dependency"],
        "sequence": list(tool_sequence(result)),
        "outcome_pass": outcome_passed,
        "outcome_note": outcome_note,
        "trajectory_pass": trajectory_passed,
        "trajectory_note": trajectory_note,
        "failure_modes": sorted(failure_modes(claim_id, result)),
        "tool_choice_correct": sum(c["correct"] for c in classified),
        "tool_choice_total": len(classified),
        "argument_valid": sum(c["valid"] for c in checks),
        "argument_total": len(checks),
        "steps_taken": len(result.tool_calls),
        "steps_needed": EXPECTED[claim_id]["min_steps"],
        "cost_usd": result.cost_usd,
        "total_tokens": result.total_tokens,
        "wall_clock_s": result.wall_clock_s,
    }


def headline_numbers(reports):

    n = len(reports)
    tc_correct = sum(r["tool_choice_correct"] for r in reports)
    tc_total = sum(r["tool_choice_total"] for r in reports)
    arg_valid = sum(r["argument_valid"] for r in reports)
    arg_total = sum(r["argument_total"] for r in reports)
    costs = sorted(r["cost_usd"] for r in reports)
    outcome_pass_rate = sum(r["outcome_pass"] for r in reports) / n
    trajectory_pass_rate = sum(r["trajectory_pass"] for r in reports) / n

    return {
        "n": n,
        "tool_choice_accuracy": tc_correct / tc_total if tc_total else None,
        "tool_choice_correct": tc_correct,
        "tool_choice_total": tc_total,
        "argument_validity_rate": arg_valid / arg_total if arg_total else None,
        "argument_valid": arg_valid,
        "argument_total": arg_total,
        "step_efficiency": sum(r["steps_taken"] for r in reports) / sum(r["steps_needed"] for r in reports),
        "cost_p50_usd": statistics.median(costs),
        "cost_max_usd": max(costs),
        "outcome_pass_rate": outcome_pass_rate,
        "trajectory_pass_rate": trajectory_pass_rate,
        "gap": outcome_pass_rate - trajectory_pass_rate,
    }


def mode_counts(reports):

    counts = {}
    for r in reports:
        for mode in r["failure_modes"]:
            counts[mode] = counts.get(mode, 0) + 1
    return counts
