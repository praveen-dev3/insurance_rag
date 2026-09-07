"""The hand-built agent: an LLM tool-calling loop over get_claim,
search_policy and compute_payout.

This is the side of the race the claims director is asking whether the
team needed. It is not artificially hobbled to make the workflow look
good - it gets the same three tools, the same model, and the same output
contract (see w7d_workflow.py) - it is just left free to decide, lap by
lap, which tool to call next and how many times, instead of following a
hard-coded sequence.

All four Task Set D §2.4 budgets are enforced *before* the next model
call is made, not after, and a breach returns a RunResult with
outcome="budget_exceeded" rather than raising - a budget is a stop
condition, not an error. run_budget_demo() in w7d_race.py exercises this
path directly with a deliberately tiny budget.
"""

import json
import time

from w7d_claims_tools import TOOLS, dispatch
from w7d_common import (
    DEFAULT_BUDGET,
    MODEL,
    REASONING_EFFORT,
    RunResult,
    call_llm,
    extract_json_obj,
)

SYSTEM_PROMPT = """You are a claims triage assistant. For the claim ID the user gives you,
work out the coverage position and the payable amount using ONLY the three tools provided -
never use outside knowledge of how insurance usually works, and never guess a deductible or
an exclusion code that a tool has not shown you.

Typical process:
1. Call get_claim to read the claim file and adjuster notes.
2. Call search_policy (one or more times) to find the exclusion rows and deductible clause
   that govern this claim. If a result you find redirects to another form (for example "see
   Form HO-0521"), search that form too before deciding.
3. Call compute_payout with the coverage status you have reached and, if covered, the loss
   amount and the dollar deductible you found.
4. Once compute_payout has returned, answer with ONLY a fenced JSON object and no further
   tool calls, in exactly this shape:

```json
{"claim_id": "...", "coverage_status": "covered" | "excluded" | "undetermined",
 "exclusion_code": "E-.." or null, "deductible": <number or null>, "payout": <number>,
 "rationale": "<one or two sentences citing the form and clause>"}
```

Do not answer before calling compute_payout. Do not skip search_policy - a status decided
from the notes alone, without checking what the policy wording actually excludes, is not
grounded."""


def run_agent(claim_id, budget=None):

    budget = budget or DEFAULT_BUDGET

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Triage claim {claim_id}."},
    ]

    result = RunResult(system="agent", claim_id=claim_id, outcome="error")
    start = time.perf_counter()
    last_payout_tool_result = None

    iteration = 0

    while True:

        iteration += 1
        result.iterations = iteration
        result.wall_clock_s = time.perf_counter() - start

        if iteration > budget.max_iterations:
            result.outcome, result.budget_reason = "budget_exceeded", "max_iterations"
            result.transcript.append(f"[budget] max_iterations ({budget.max_iterations}) reached before lap {iteration}")
            break

        if result.wall_clock_s > budget.max_wall_clock_s:
            result.outcome, result.budget_reason = "budget_exceeded", "wall_clock"
            result.transcript.append(f"[budget] wall_clock ({budget.max_wall_clock_s}s) exceeded at {result.wall_clock_s:.1f}s")
            break

        if result.total_tokens > budget.max_tokens:
            result.outcome, result.budget_reason = "budget_exceeded", "max_tokens"
            result.transcript.append(f"[budget] max_tokens ({budget.max_tokens}) exceeded at {result.total_tokens}")
            break

        if result.cost_usd > budget.max_cost_usd:
            result.outcome, result.budget_reason = "budget_exceeded", "max_cost"
            result.transcript.append(f"[budget] max_cost (${budget.max_cost_usd}) exceeded at ${result.cost_usd:.5f}")
            break

        result.transcript.append(f"[lap {iteration}] calling {MODEL}, {len(messages)} messages so far")

        response = call_llm(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            reasoning_effort=REASONING_EFFORT,
        )

        usage = response.usage
        result.prompt_tokens += usage.prompt_tokens
        result.completion_tokens += usage.completion_tokens
        result.wall_clock_s = time.perf_counter() - start

        message = response.choices[0].message
        messages.append(message.model_dump(exclude_none=True))

        if not message.tool_calls:
            result.transcript.append(f"[lap {iteration}] final answer: {message.content!r}")

            parsed = extract_json_obj(message.content)

            if parsed is None:
                result.outcome = "error"
                result.budget_reason = "final answer was not valid JSON"
                break

            result.outcome = "completed"
            result.raw_final = parsed
            result.coverage_status = parsed.get("coverage_status")
            result.exclusion_code = parsed.get("exclusion_code")
            result.deductible = parsed.get("deductible")

            # The payout a compute_payout call actually returned is
            # authoritative over whatever number the model typed into the
            # JSON free-hand - see the module docstring on "same tools".
            result.payout = (
                last_payout_tool_result["payout"]
                if last_payout_tool_result is not None
                else parsed.get("payout")
            )
            break

        for call in message.tool_calls:

            args = json.loads(call.function.arguments or "{}")
            tool_result = dispatch(call.function.name, args)

            result.tool_calls.append({"name": call.function.name, "arguments": args, "result": tool_result})
            result.transcript.append(f"[lap {iteration}] tool {call.function.name}({args}) -> {tool_result}")

            if call.function.name == "compute_payout" and "error" not in tool_result:
                last_payout_tool_result = tool_result

            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(tool_result),
            })

    return result
