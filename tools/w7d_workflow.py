"""The fixed workflow: four hard-coded steps, no loop, racing the agent
in w7d_agent.py on the identical task.

Same tools (get_claim, search_policy, compute_payout - called directly as
Python functions here instead of through LLM tool-calling, but they are
the exact same functions in w7d_claims_tools.py), same model (MODEL from
w7d_common), same output contract (RunResult, graded by the same grade()).
The one thing this file does not have is a loop: control flow is a fixed
sequence of four steps, with a single hard-coded `if` to follow a
same-turn form redirect (step 2b) - not a loop that could run an unbounded
number of times, and not an LLM deciding what happens next.

Step 2b is the answer to Task Set D's dependency requirement (§2.3): the
claim class that needs it is named in tools/data/w7d_claims.py's
docstring (c04, c06, c08). A fixed workflow *can* hard-code a branch for
"the exclusion row I found names another form" - the question the race
numbers answer is whether three such branches were enough for these 10
claims, or whether a fourth claim would need a fourth branch nobody wrote
yet. That is the whole decision rule.
"""

import re
import time

from w7d_claims_tools import (
    compute_payout_impl,
    get_claim_impl,
    search_policy_impl,
)
from w7d_common import (
    DEFAULT_BUDGET,
    MODEL,
    REASONING_EFFORT,
    RunResult,
    call_llm,
    extract_json_obj,
)

REDIRECT_RE = re.compile(r"see Form (HO-\d{4}|DP-\d{4})")

DEDUCTIBLE_LEG_QUERY = (
    "deductible excess amount payable in respect of each loss, limits of "
    "liability, Coverage A limit, percent of Coverage A"
)

DECISION_PROMPT = """You are a claims triage assistant. Below is one claim file and the policy wording
retrieved for it. Using ONLY that wording - never outside knowledge of how insurance usually
works - decide the coverage position and the amount payable.

If coverage_status is "covered", you MUST set "deductible" to a dollar figure - search the
RETRIEVED POLICY WORDING below for the clause that states a deductible in dollars or as a
percentage, not a clause that only mentions "the deductible" in passing. If the clause states a
percentage (e.g. "two percent (2%) of the Coverage A limit"), multiply that percentage by the
claim file's Coverage A limit to get the dollar figure; if no Coverage A limit is given, use the
flat dollar deductible from whichever other clause states one. Leave "deductible" null only if
coverage_status is not "covered", or if no deductible clause was retrieved at all.

Answer with ONLY a fenced JSON object, in exactly this shape:

```json
{{"claim_id": "...", "coverage_status": "covered" | "excluded" | "undetermined",
 "exclusion_code": "E-.." or null, "deductible": <number or null>, "payout": <number>,
 "rationale": "<one or two sentences citing the form and clause>"}}
```

CLAIM FILE
{claim_block}

COVERAGE AND EXCLUSION WORDING (retrieved against the adjuster's notes)
{coverage_block}

DEDUCTIBLE WORDING (retrieved separately, against a deductible-specific query - the clause
stating the actual dollar or percentage figure is in here, not above)
{deductible_block}
"""


def _format_claim(claim):
    return (
        f"Claim ID: {claim['claim_id']}\n"
        f"Claim number: {claim['claim_number']}\n"
        f"Date of loss: {claim['date_of_loss']}\n"
        f"Policy line: {claim['policy_line']}\n"
        f"Form on file: {claim['form_number']}\n"
        f"Coverage A limit: {claim['coverage_a_limit']}\n"
        f"Reported loss amount: {claim['reported_loss_amount']}\n"
        f"Adjuster notes: {claim['notes']}"
    )


def _format_wording(matches):
    if not matches:
        return "(no matching clauses found)"

    return "\n\n".join(
        f"[{m['form_number']} | {m['clause']}]\n{m['text']}" for m in matches
    )


def _dedupe(matches):
    """Drop repeats across the two legs, by chunk id - not by clause label.

    Several distinct clauses share one heading as their "clause" label
    (5.1, 5.2 and 5.3 are all "5. LIMITS, SUBLIMITS AND DEDUCTIBLE"), so
    deduping on the label would collapse them into one and silently drop
    the very deductible clause the second leg exists to find.
    """

    seen, deduped = set(), []

    for m in matches:
        if m["id"] not in seen:
            seen.add(m["id"])
            deduped.append(m)

    return deduped


def run_workflow(claim_id, budget=None):

    budget = budget or DEFAULT_BUDGET

    result = RunResult(system="workflow", claim_id=claim_id, outcome="error")
    start = time.perf_counter()

    # Step 1: pull the claim. Direct call, no LLM, no tokens.
    claim = get_claim_impl(claim_id)
    result.transcript.append(f"[step 1] get_claim({claim_id!r}) -> form={claim.get('form_number')}")

    if "error" in claim:
        result.outcome, result.budget_reason = "error", claim["error"]
        result.wall_clock_s = time.perf_counter() - start
        return result

    # Step 2: search the form on file for the clauses the notes engage.
    # Two legs, not one - a single query built from the notes spends every
    # slot on the coverage/exclusion clauses the notes are mostly about,
    # and the deductible clause never makes the cut. rag/claims.py hit
    # exactly this failure in Week 5 and fixed it the same way: a second,
    # separate retrieval in the vocabulary of the clause rather than the
    # notes. See DEDUCTIBLE_QUERY there; DEDUCTIBLE_LEG_QUERY below is
    # this workflow's equivalent.
    query = claim["notes"]
    search = search_policy_impl(query, form_number=claim["form_number"], top_k=4)
    coverage_matches = list(search.get("matches", []))
    result.transcript.append(f"[step 2] search_policy(form={claim['form_number']!r}) -> {len(coverage_matches)} matches")

    deductible_search = search_policy_impl(DEDUCTIBLE_LEG_QUERY, form_number=claim["form_number"], top_k=2)
    deductible_matches = list(deductible_search.get("matches", []))
    result.transcript.append(f"[step 2 deductible leg] search_policy(form={claim['form_number']!r}) -> {len(deductible_matches)} matches")

    # Step 2b: a hard-coded branch, not a loop. If what step 2 found
    # redirects to another form, search that form too (both legs) -
    # exactly once, because no exclusion in this corpus redirects twice.
    all_matches_so_far = coverage_matches + deductible_matches
    redirect_forms = {m for text in (m["text"] for m in all_matches_so_far) for m in REDIRECT_RE.findall(text)}

    for redirect_form in redirect_forms:
        redirected = search_policy_impl(query, form_number=redirect_form, top_k=4)
        redirected_deductible = search_policy_impl(DEDUCTIBLE_LEG_QUERY, form_number=redirect_form, top_k=2)
        coverage_matches.extend(redirected.get("matches", []))
        deductible_matches.extend(redirected_deductible.get("matches", []))
        result.transcript.append(
            f"[step 2b] exclusion redirected to {redirect_form}, searched it -> "
            f"{len(redirected.get('matches', []))} + {len(redirected_deductible.get('matches', []))} more matches"
        )

    coverage_matches = _dedupe(coverage_matches)
    deductible_matches = _dedupe(deductible_matches)

    result.wall_clock_s = time.perf_counter() - start

    if result.wall_clock_s > budget.max_wall_clock_s:
        result.outcome, result.budget_reason = "budget_exceeded", "wall_clock"
        return result

    # Step 3: one LLM call to reach the coverage decision. Same model,
    # same output contract as the agent - see w7d_agent.py's SYSTEM_PROMPT.
    prompt = DECISION_PROMPT.format(
        claim_block=_format_claim(claim),
        coverage_block=_format_wording(coverage_matches),
        deductible_block=_format_wording(deductible_matches),
    )

    result.iterations = 1
    response = call_llm(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        reasoning_effort=REASONING_EFFORT,
    )

    usage = response.usage
    result.prompt_tokens += usage.prompt_tokens
    result.completion_tokens += usage.completion_tokens
    result.wall_clock_s = time.perf_counter() - start

    content = response.choices[0].message.content
    result.transcript.append(f"[step 3] decision call -> {content!r}")

    parsed = extract_json_obj(content)

    if parsed is None:
        result.outcome, result.budget_reason = "error", "decision call was not valid JSON"
        return result

    for budget_check, reason in (
        (result.total_tokens > budget.max_tokens, "max_tokens"),
        (result.cost_usd > budget.max_cost_usd, "max_cost"),
        (result.wall_clock_s > budget.max_wall_clock_s, "wall_clock"),
    ):
        if budget_check:
            result.outcome, result.budget_reason = "budget_exceeded", reason
            return result

    # Step 4: compute the payout. Direct call to the same tool the agent
    # calls, so the number reported for both systems is produced by
    # identical arithmetic and the race measures orchestration, not two
    # different payout formulas.
    payout_result = compute_payout_impl(
        claim_id,
        parsed.get("coverage_status"),
        claim["reported_loss_amount"],
        parsed.get("deductible"),
    )
    result.tool_calls.append({"name": "compute_payout", "arguments": parsed, "result": payout_result})
    result.transcript.append(f"[step 4] compute_payout(...) -> {payout_result}")

    result.wall_clock_s = time.perf_counter() - start
    result.outcome = "completed"
    result.raw_final = parsed
    result.coverage_status = parsed.get("coverage_status")
    result.exclusion_code = parsed.get("exclusion_code")
    result.deductible = parsed.get("deductible")
    result.payout = payout_result.get("payout") if "error" not in payout_result else None

    return result
