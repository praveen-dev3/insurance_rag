"""The orchestrator: decomposes one claim into two worker hand-offs and a
synthesis step, racing tools/w7d_agent.py's single agent on the identical
10 claims (data/w7d_claims.py, the same "Week 6 eval cases" every Task Set
D since Week 7 has used).

Three LLM hand-offs per claim, not one loop:

    orchestrator (direct get_claim_impl, no tokens)
      -> [handoff 1] notes-summary-worker      (1 call, no tools)
      -> [handoff 2] exclusions-worker         (tool-calling loop over
                                                 search_policy + compute_payout
                                                 only - never sees get_claim,
                                                 never sees the raw notes,
                                                 only the handoff-1 summary)
      -> [handoff 3] synthesis                 (1 call, no tools, combines
                                                 the summary + the worker's
                                                 finding into the final answer)

The narrow-prompt-fewer-tools constraint the Task Set D common-mistakes
list warns against deleting is enforced structurally: WORKER_TOOLS is a
two-item list, not TOOLS from w7d_claims_tools.py, so the exclusions
worker cannot call get_claim even if it wanted to.

The context strategy is deliberate, not accidental: handoff 2 receives the
handoff-1 *summary* (a short JSON object), not the raw adjuster notes -
the common mistake this file does not make is re-sending the full note
history to every worker on every hop. See results_week10d.md for what
handoff 2 costs anyway (the answer: still the dominant share of the token
bill, because it is the one hand-off that runs a multi-lap tool loop).

inject_failure=True on run_orchestrator() simulates the exclusions worker
returning a transport-level HTTP 500 before it makes any call of its own -
no retry logic exists anywhere in this file, so whatever the synthesis
step does with a missing worker finding is the orchestrator's actual,
un-engineered behaviour, not a designed fallback. See w10d_run.py's
`failure` stage and results_week10d.md/failure_case.md for what it did.
"""

import json
import time

from w7d_claims_tools import (
    COMPUTE_PAYOUT_TOOL,
    SEARCH_POLICY_TOOL,
    dispatch,
    get_claim_impl,
)
from w7d_common import (
    DEFAULT_BUDGET,
    MODEL,
    REASONING_EFFORT,
    RunResult,
    call_llm,
    extract_json_obj,
)

WORKER_TOOLS = [SEARCH_POLICY_TOOL, COMPUTE_PAYOUT_TOOL]

NOTES_SUMMARY_SYSTEM = """You summarize adjuster notes for a downstream coverage analyst who will never see
the raw notes themselves. Read the claim's adjuster notes and produce ONLY a fenced JSON
object, in exactly this shape:

```json
{"cause_of_loss": "<one phrase>", "key_facts": ["<fact 1>", "<fact 2>", "..."],
 "notable_dates_or_durations": ["..."]}
```

List every fact that could affect a coverage or exclusion decision - timing, occupancy,
maintenance or mitigation actions taken, who was present, any co-occurring damage. Do not
editorialize about coverage itself; deciding coverage is not your job."""

COVERAGE_WORKER_SYSTEM = """You are the coverage/exclusions specialist in a claims-triage pipeline. You do not
see the adjuster's raw notes - you have already been given a distilled fact summary
below. Using ONLY search_policy and compute_payout, work out the coverage position and
the payable amount.

Typical process:
1. Call search_policy (one or more times) against the form on file to find the governing
   exclusion rows and deductible clause. If a result redirects to another form (for
   example "see Form HO-0521"), search that form too before deciding.
2. Call compute_payout with the coverage status you have reached and, if covered, the
   loss amount and the dollar deductible you found.
3. Once compute_payout has returned, answer with ONLY a fenced JSON object and no further
   tool calls, in exactly this shape:

```json
{"coverage_status": "covered" | "excluded" | "undetermined", "exclusion_code": "E-.." or null,
 "deductible": <number or null>, "payout": <number>, "rationale": "<one or two sentences>"}
```

Do not answer before calling compute_payout. Do not skip search_policy - a status decided
from the fact summary alone, without checking what the policy wording actually excludes,
is not grounded."""

SYNTHESIS_SYSTEM = """You are the final-answer step of a claims-triage pipeline. You are given the claim
header, the adjuster-note summary one worker produced, and the coverage/exclusions
worker's finding (if it completed). Compose the single final answer this pipeline
reports to the adjuster, as ONLY a fenced JSON object in exactly this shape:

```json
{"claim_id": "...", "coverage_status": "covered" | "excluded" | "undetermined",
 "exclusion_code": "E-.." or null, "deductible": <number or null>, "payout": <number>,
 "rationale": "<one or two sentences>"}
```

Report the coverage/exclusions worker's finding faithfully - do not soften, round up, or
restate a conditional or exception-dependent finding as a plain "covered"."""


class ClaimsWorkerError(Exception):
    """A simulated transport-level failure calling the exclusions worker."""


def _run_notes_worker(claim):

    messages = [
        {"role": "system", "content": NOTES_SUMMARY_SYSTEM},
        {"role": "user", "content": f"Adjuster notes for claim {claim['claim_id']}:\n\n{claim['notes']}"},
    ]

    response = call_llm(model=MODEL, messages=messages, reasoning_effort=REASONING_EFFORT)
    usage = response.usage
    content = response.choices[0].message.content

    return {
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "parsed": extract_json_obj(content),
        "raw": content,
    }


def _run_coverage_worker(claim, adjuster_summary, budget, inject_failure=False):

    if inject_failure:
        raise ClaimsWorkerError(f"HTTP 500: exclusions-worker unavailable for claim {claim['claim_id']}")

    fact_lines = "\n".join(f"- {f}" for f in adjuster_summary.get("key_facts", []) or [])

    user_content = (
        f"Claim ID: {claim['claim_id']}\n"
        f"Form on file: {claim['form_number']}\n"
        f"Reported loss amount: {claim['reported_loss_amount']}\n"
        f"Coverage A limit: {claim['coverage_a_limit']}\n"
        f"Cause of loss (from adjuster-note summary): {adjuster_summary.get('cause_of_loss')}\n"
        f"Key facts (from adjuster-note summary):\n{fact_lines or '(none extracted)'}"
    )

    messages = [
        {"role": "system", "content": COVERAGE_WORKER_SYSTEM},
        {"role": "user", "content": user_content},
    ]

    prompt_tokens = completion_tokens = 0
    tool_calls, transcript = [], []
    iteration = 0
    parsed = None

    while True:

        iteration += 1

        if iteration > budget.max_iterations:
            transcript.append(f"[handoff 2 lap {iteration}] budget max_iterations reached")
            break

        response = call_llm(
            model=MODEL,
            messages=messages,
            tools=WORKER_TOOLS,
            tool_choice="auto",
            reasoning_effort=REASONING_EFFORT,
        )

        usage = response.usage
        prompt_tokens += usage.prompt_tokens
        completion_tokens += usage.completion_tokens

        message = response.choices[0].message
        messages.append(message.model_dump(exclude_none=True))

        if not message.tool_calls:
            transcript.append(f"[handoff 2 lap {iteration}] final: {message.content!r}")
            parsed = extract_json_obj(message.content)
            break

        for call in message.tool_calls:

            args = json.loads(call.function.arguments or "{}")
            tool_result = dispatch(call.function.name, args)

            tool_calls.append({"name": call.function.name, "arguments": args, "result": tool_result})
            transcript.append(f"[handoff 2 lap {iteration}] tool {call.function.name}({args}) -> {tool_result}")

            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(tool_result),
            })

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "iterations": iteration,
        "tool_calls": tool_calls,
        "transcript": transcript,
        "parsed": parsed,
    }


def _run_synthesis(claim, adjuster_summary, coverage_out, coverage_error):

    if coverage_error:
        worker_block = f"worker_status: unavailable\nerror: {coverage_error}"
    elif coverage_out and coverage_out["parsed"]:
        worker_block = "worker_status: ok\nfinding: " + json.dumps(coverage_out["parsed"])
    else:
        worker_block = "worker_status: unavailable\nerror: worker did not return a parseable finding"

    user_content = (
        f"Claim ID: {claim['claim_id']}\n"
        f"Reported loss amount: {claim['reported_loss_amount']}\n\n"
        f"ADJUSTER-NOTE SUMMARY\n{json.dumps(adjuster_summary)}\n\n"
        f"COVERAGE/EXCLUSIONS WORKER FINDING\n{worker_block}"
    )

    messages = [
        {"role": "system", "content": SYNTHESIS_SYSTEM},
        {"role": "user", "content": user_content},
    ]

    response = call_llm(model=MODEL, messages=messages, reasoning_effort=REASONING_EFFORT)
    usage = response.usage
    content = response.choices[0].message.content

    return {
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "parsed": extract_json_obj(content),
        "raw": content,
    }


def run_orchestrator(claim_id, budget=None, inject_failure=False):

    budget = budget or DEFAULT_BUDGET

    result = RunResult(system="orchestrator", claim_id=claim_id, outcome="error")
    result.handoffs = []
    start = time.perf_counter()

    claim = get_claim_impl(claim_id)
    result.transcript.append(f"[intake] get_claim({claim_id!r}) -> form={claim.get('form_number')}")

    if "error" in claim:
        result.outcome, result.budget_reason = "error", claim["error"]
        result.wall_clock_s = time.perf_counter() - start
        return result

    # Handoff 1: notes-summary worker.
    summary_out = _run_notes_worker(claim)
    result.prompt_tokens += summary_out["prompt_tokens"]
    result.completion_tokens += summary_out["completion_tokens"]
    result.handoffs.append({
        "name": "orchestrator -> notes-summary-worker",
        "prompt_tokens": summary_out["prompt_tokens"],
        "completion_tokens": summary_out["completion_tokens"],
        "total_tokens": summary_out["prompt_tokens"] + summary_out["completion_tokens"],
    })
    result.transcript.append(f"[handoff 1] notes-summary-worker -> {summary_out['parsed']}")
    result.wall_clock_s = time.perf_counter() - start

    adjuster_summary = summary_out["parsed"] or {
        "cause_of_loss": None, "key_facts": [], "notable_dates_or_durations": [],
    }

    # Handoff 2: exclusions worker. May raise ClaimsWorkerError if
    # inject_failure=True - caught here, not inside the worker, because the
    # orchestrator is what has to decide what to do about a dead worker,
    # not the worker itself.
    coverage_out, coverage_error = None, None
    try:
        coverage_out = _run_coverage_worker(claim, adjuster_summary, budget, inject_failure=inject_failure)
        result.prompt_tokens += coverage_out["prompt_tokens"]
        result.completion_tokens += coverage_out["completion_tokens"]
        result.iterations += coverage_out["iterations"]
        result.tool_calls.extend(coverage_out["tool_calls"])
        result.transcript.extend(coverage_out["transcript"])
        result.handoffs.append({
            "name": "orchestrator -> exclusions-worker",
            "prompt_tokens": coverage_out["prompt_tokens"],
            "completion_tokens": coverage_out["completion_tokens"],
            "total_tokens": coverage_out["prompt_tokens"] + coverage_out["completion_tokens"],
            "laps": coverage_out["iterations"],
        })
    except ClaimsWorkerError as error:
        coverage_error = str(error)
        result.transcript.append(f"[handoff 2] exclusions-worker -> {coverage_error}")
        result.handoffs.append({
            "name": "orchestrator -> exclusions-worker",
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
            "error": coverage_error,
        })

    result.wall_clock_s = time.perf_counter() - start

    if result.wall_clock_s > budget.max_wall_clock_s:
        result.outcome, result.budget_reason = "budget_exceeded", "wall_clock"
        return result

    # Handoff 3: synthesis.
    synth_out = _run_synthesis(claim, adjuster_summary, coverage_out, coverage_error)
    result.prompt_tokens += synth_out["prompt_tokens"]
    result.completion_tokens += synth_out["completion_tokens"]
    result.handoffs.append({
        "name": "exclusions-worker+notes-summary -> synthesis",
        "prompt_tokens": synth_out["prompt_tokens"],
        "completion_tokens": synth_out["completion_tokens"],
        "total_tokens": synth_out["prompt_tokens"] + synth_out["completion_tokens"],
    })
    result.transcript.append(f"[handoff 3] synthesis -> {synth_out['parsed']}")
    result.wall_clock_s = time.perf_counter() - start

    parsed = synth_out["parsed"]

    if parsed is None:
        result.outcome, result.budget_reason = "error", "synthesis call was not valid JSON"
        return result

    for budget_check, reason in (
        (result.total_tokens > budget.max_tokens, "max_tokens"),
        (result.cost_usd > budget.max_cost_usd, "max_cost"),
        (result.wall_clock_s > budget.max_wall_clock_s, "wall_clock"),
    ):
        if budget_check:
            result.outcome, result.budget_reason = "budget_exceeded", reason
            return result

    result.outcome = "completed"
    result.raw_final = parsed
    result.coverage_status = parsed.get("coverage_status")
    result.exclusion_code = parsed.get("exclusion_code")
    result.deductible = parsed.get("deductible")

    # Same rule as w7d_agent.py: a compute_payout tool result is
    # authoritative over whatever number the model typed into the JSON
    # free-hand. If the exclusions worker never ran (inject_failure), no
    # compute_payout call exists in result.tool_calls at all, and the
    # synthesis step's free-hand payout - if it states one - is exactly
    # the "fluent fiction" case Week 8 (c08) already showed exists.
    last_payout_tool_result = None
    for call in reversed(result.tool_calls):
        if call["name"] == "compute_payout" and "error" not in call["result"]:
            last_payout_tool_result = call["result"]
            break

    result.payout = last_payout_tool_result["payout"] if last_payout_tool_result else parsed.get("payout")

    return result
