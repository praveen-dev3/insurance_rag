"""The Week 11 claims-triage app: the Week 7 agent, instrumented.

Same three tools, same model and same output contract as
tools/w7d_agent.py - what changes is that every model call and every tool
call is a span in one request log (tools/w11_obs.py), and that the two
things a fix can change are now *versioned and logged* instead of being
edits to a string literal:

    prompt_version     "triage-v1" (the Week 7 prompt, verbatim) or "triage-v2"
    retrieval_version  "kw-r1" (keyword top-k, as shipped) or "kw-r2"
                       (exclusions-always: see _attach_exclusions)

Keeping the Week 7 prompt byte-for-byte as v1 is what makes the drill's
"RED before the fix" honest - the thing that fails is the thing that
shipped, not a reconstruction of it.

The failure this versioning exists to fix (eval case c11): a claim whose
notes say "dimpled", "pitted", "looks bad" never shares a word with the
HO-0412 exclusion rows ("marring, scuffing or granule loss", "cosmetic
damage"). Keyword search in the notes' own vocabulary returns the coverage
basis clauses and never the row that excludes the loss, and a model that
was told to ground its answer in what search returned grounds it in a
coverage grant. That is a retrieval miss, not a reasoning error, and the
r2 fix is therefore at the retrieval layer: whenever a search touches a
form, the form's whole exclusion table - and the note under it that
reverses some rows - comes back with the results.
"""

import json
import time

from w7d_agent import SYSTEM_PROMPT as PROMPT_V1
from w7d_claims_tools import TOOLS, dispatch
from w7d_common import DEFAULT_BUDGET, MODEL, REASONING_EFFORT, call_llm, extract_json_obj
from w7d_policy_corpus import _CHUNKS
from w11_obs import RequestTrace, notes_digest, prompt_fingerprint
from data.w11d_cases import register

register()

from data.w7d_claims import CLAIMS_BY_ID  # noqa: E402  (after register())

PROMPT_V2_ADDENDUM = """

Added in v2 - every search_policy result for a form also carries an
`exclusion_schedule`: that form's complete exclusion table, plus the note
under it that says when a row does NOT apply. Before you decide a claim is
covered, read every row of the schedule against the adjuster notes. The
notes will rarely use the row's own words (a roof described as "dimpled" or
"pitted" is the row's "marring, scuffing or granule loss"), so match on
what physically happened, not on shared vocabulary. If a row describes what
happened and the table's note does not reverse it, the claim is excluded
under that row's code, whatever the coverage-basis clauses say."""

# Added in v3, after the first GREEN attempt: with v2 + kw-r2 the controlling
# rows (E-34, E-36) WERE in the model's context and gpt-oss-20b still wrote
# "Loss is penetration (pitted) so not cosmetic, no exclusion applies". The
# retrieval fix had done its job and exposed the second cause: the model read
# the word "pitted" as a breach. So the remaining failure is generation, and
# is addressed in the prompt - not by touching retrieval again.
PROMPT_V3_ADDENDUM = """

Penetration is a fact the notes state: a breach, a hole, an exposed mat, or
water coming through. Words such as dimpled, pitted, dented, scuffed or
bruised describe appearance, not penetration. If the notes say the surface is
intact, or that nothing was breached and nothing leaked, there was no
penetration - and then a row that excludes appearance-only damage describes
the claim, and the claim is excluded under that row's code."""

PROMPTS = {
    "triage-v1": PROMPT_V1,
    "triage-v2": PROMPT_V1 + PROMPT_V2_ADDENDUM,
    "triage-v3": PROMPT_V1 + PROMPT_V2_ADDENDUM + PROMPT_V3_ADDENDUM,
}

RETRIEVALS = ("kw-r1", "kw-r2")


# ---- exclusion schedule: the r2 retrieval fix ------------------------------

def exclusion_chunks(form_number):
    """Every exclusion-table row of one form, plus the note under the table."""

    return [
        chunk for chunk in _CHUNKS
        if chunk["form_number"] == form_number
        and ("(E-" in chunk["clause"] or "(note)" in chunk["clause"])
    ]


def _attach_exclusions(result, scope_form, already_attached):
    """
    Add `exclusion_schedule` to a search result for every form it touched.

    A form is attached once per request: the schedule is ~400 tokens and
    the agent loop re-sends the whole transcript on every lap, so attaching
    it on each search would pay for it again on each later lap for no
    information gain. `already_attached` is what makes that a property of
    the code rather than of the model's search habits.
    """

    forms = {m["form_number"] for m in result.get("matches", [])}

    if scope_form:
        forms.add(scope_form)

    rows = []

    for form in sorted(forms - already_attached):
        already_attached.add(form)
        rows.extend(exclusion_chunks(form))

    if not rows:
        return result, []

    schedule = [
        {"id": c["id"], "form_number": c["form_number"],
         "clause": c["clause"], "text": c["text"]}
        for c in rows
    ]

    return {**result, "exclusion_schedule": schedule}, [c["id"] for c in rows]


# ---- the request -----------------------------------------------------------

def run_request(claim_id, user_id="u-adjuster-01", prompt_version="triage-v2",
                retrieval_version="kw-r2", sink=None, budget=None, ts=None):
    """
    One claim triage, run and logged. Returns (RequestTrace, final dict).

    The returned trace has already been written to `sink` when one is
    given, so a caller that only wants the answer can pass sink=None and
    still get the spans back.
    """

    budget = budget or DEFAULT_BUDGET
    claim = CLAIMS_BY_ID[claim_id]

    trace = RequestTrace(
        user_id=user_id,
        input_type="claim_triage",
        prompt_version=prompt_version,
        retrieval_version=retrieval_version,
        model=MODEL,
        claim_number=claim["claim_number"],
        ts=ts,
    )

    trace.input = {
        "claim_id": claim_id,
        "question": f"Triage claim {claim_id}.",
        "prompt_sha256": prompt_fingerprint(
            prompt_version, PROMPTS[prompt_version]
        )["template_sha256"],
        **notes_digest(claim["notes"]),
    }

    if sink is not None:
        sink.register_claim(claim["claim_number"], claim["claimant"])

    messages = [
        {"role": "system", "content": PROMPTS[prompt_version]},
        {"role": "user", "content": f"Triage claim {claim_id}."},
    ]

    attached_forms = set()
    last_payout = None
    final = {}
    start = time.perf_counter()
    prompt_tokens = completion_tokens = 0

    try:
        for lap in range(1, budget.max_iterations + 1):

            if time.perf_counter() - start > budget.max_wall_clock_s:
                trace.outcome = "budget_exceeded:wall_clock"
                break

            with trace.span(f"llm.lap{lap}", "generation", lap=lap) as span:
                response = call_llm(
                    model=MODEL, messages=messages, tools=TOOLS,
                    tool_choice="auto", reasoning_effort=REASONING_EFFORT,
                )
                span["tokens_in"] = response.usage.prompt_tokens
                span["tokens_out"] = response.usage.completion_tokens

            prompt_tokens += response.usage.prompt_tokens
            completion_tokens += response.usage.completion_tokens

            message = response.choices[0].message
            messages.append(message.model_dump(exclude_none=True))

            if not message.tool_calls:
                parsed = extract_json_obj(message.content)

                if parsed is None:
                    trace.outcome = "error:final_not_json"
                    trace.output = {"text": message.content}
                    break

                final = {
                    "coverage_status": parsed.get("coverage_status"),
                    "exclusion_code": parsed.get("exclusion_code"),
                    "deductible": parsed.get("deductible"),
                    # compute_payout's number is authoritative over the one
                    # the model typed, as in tools/w7d_agent.py.
                    "payout": (last_payout["payout"] if last_payout
                               else parsed.get("payout")),
                    "rationale": parsed.get("rationale"),
                }
                trace.output = {"text": message.content, **final}
                trace.outcome = "completed"
                break

            for call in message.tool_calls:

                args = json.loads(call.function.arguments or "{}")
                is_search = call.function.name == "search_policy"
                stage = "retrieval" if is_search else "tools"

                with trace.span(f"tool.{call.function.name}", stage, lap=lap,
                                args=_loggable_args(args)) as span:

                    tool_result = dispatch(call.function.name, args)

                    if is_search:
                        ids = [m["id"] for m in tool_result.get("matches", [])]

                        if retrieval_version == "kw-r2":
                            tool_result, extra_ids = _attach_exclusions(
                                tool_result, args.get("form_number"), attached_forms
                            )
                            span["attrs"]["exclusion_rows_attached"] = len(extra_ids)
                            ids += extra_ids

                        span["attrs"]["context_ids"] = ids
                        trace.add_context(ids)

                if call.function.name == "compute_payout" and "error" not in tool_result:
                    last_payout = tool_result

                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(tool_result),
                })
        else:
            trace.outcome = "budget_exceeded:max_iterations"

    finally:
        trace.extra["usage"] = {
            "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
        }

        if sink is not None:
            trace.written = sink.write(trace)

    return trace, final


def _loggable_args(args):
    """Tool arguments for the span, minus anything free-text and long."""

    return {k: (v[:120] if isinstance(v, str) else v) for k, v in args.items()}
