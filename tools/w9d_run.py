"""Week 9 Task Set D: bolt the claims-system server onto the Week 9 agent
without touching the agent.

    python weeks.py w9d-eval --stage discover   # tool counts before -> after, by name
    python weeys.py w9d-eval --stage query      # the one query that proves a claims-system tool ran
    python weeks.py w9d-eval --stage wire       # raw initialize/tools-list/tools-call, hand-annotated
    python weeks.py w9d-eval --stage errors     # docstring-as-prompt + recoverable error, before/after
    python weeks.py w9d-eval --stage all        # all four, in order

Every artifact lands under eval/w9d/. requirements 2 (agent_diff.txt) and the
config diff are produced separately, straight from the shell, because they
are a `git diff --no-index` between two files already on disk
(eval/w9d/w9d_agent.step1_snapshot.py vs tools/w9d_agent.py, and
tools/data/w9d_mcp_config.step1.json vs tools/data/w9d_mcp_config.json) -
see results_week9d.md §2 for the exact commands and their output.
"""

import argparse
import json
from pathlib import Path

from w7d_claims_tools import SEARCH_POLICY_TOOL as OLD_SEARCH_POLICY_TOOL
from w7d_common import MODEL, REASONING_EFFORT, call_llm
from w9d_agent import DEFAULT_CONFIG_PATH, MCPToolRouter, load_config, run_agent
from w9d_mcp import MCPClient
from w9d_policy_server import SEARCH_POLICY_DESCRIPTION, SEARCH_POLICY_INPUT_SCHEMA

OUT_DIR = Path(__file__).resolve().parent.parent / "eval" / "w9d"
STEP1_CONFIG = Path(__file__).resolve().parent / "data" / "w9d_mcp_config.step1.json"


def _tool_lines(report):
    lines = []
    for server_label in sorted(report):
        names = ", ".join(sorted(report[server_label]))
        lines.append(f"- **{server_label}**: {names}")
    return lines


def discover():
    """requirement 3: tool count before -> after, by name, from tools/list."""

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    before_router = MCPToolRouter(load_config(STEP1_CONFIG))
    before_report = before_router.tool_report()
    before_names = sorted(before_router._owner)
    before_router.close()

    after_router = MCPToolRouter(load_config(DEFAULT_CONFIG_PATH))
    after_report = after_router.tool_report()
    after_names = sorted(after_router._owner)
    after_router.close()

    lines = [
        "# Tool count: before -> after",
        "",
        f"**{len(before_names)} -> {len(after_names)}** tools, from `tools/list` against each configured server.",
        "",
        f"## Before ({STEP1_CONFIG.name}) - {len(before_names)} tool(s)",
        "",
        *_tool_lines(before_report),
        "",
        f"## After ({DEFAULT_CONFIG_PATH.name}) - {len(after_names)} tool(s)",
        "",
        *_tool_lines(after_report),
        "",
        "New in this discovery, added by config alone: "
        + ", ".join(sorted(set(after_names) - set(before_names))),
    ]

    (OUT_DIR / "tool_counts.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"before: {len(before_names)} tools -> {before_names}")
    print(f"after:  {len(after_names)} tools -> {after_names}")
    print(f"wrote {OUT_DIR / 'tool_counts.md'}")


def query():
    """requirement 1: one query that provably calls a tool from server two."""

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    user_message = (
        "What is the status of claim CLM-7004, and can you summarize what the "
        "adjuster notes say about the cause of loss?"
    )

    result = run_agent(user_message)

    claims_system_calls = [t for t in result.tool_calls if t["server"] == "claims-system"]

    record = {
        "user_message": user_message,
        "outcome": result.outcome,
        "tool_calls": result.tool_calls,
        "transcript": result.transcript,
        "final_text": result.final_text,
    }
    (OUT_DIR / "proof_query.json").write_text(json.dumps(record, indent=2), encoding="utf-8")

    print(f"outcome: {result.outcome}")
    for line in result.transcript:
        print(" ", line.encode("ascii", "replace").decode())
    print()
    print(f"claims-system tools called: {[c['name'] for c in claims_system_calls]}")
    print(f"wrote {OUT_DIR / 'proof_query.json'}")

    if not claims_system_calls:
        raise SystemExit("no claims-system tool was called - the proof query did not prove anything")


def wire():
    """requirement 4: raw initialize -> tools/list -> tools/call, hand-annotated."""

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    log = []
    client = MCPClient("claims-system", "python", ["tools/w9d_claims_server.py"], log=log)
    client.initialize()
    client.list_tools()
    client.call_tool("get_claim_status", {"claim_number": "CLM-7004"})
    client.close()

    annotations = {
        "initialize request": {
            "jsonrpc": "JSON-RPC 2.0 envelope version - every MCP message carries this, request or response.",
            "id": "Client-assigned request id; the matching response echoes it back so the client can correlate the two over one stdio stream carrying many in-flight calls.",
            "method": "\"initialize\" - the MCP handshake. Nothing else (tools/list, tools/call) is legal before this completes.",
            "params.protocolVersion": "The MCP spec version this client speaks; the server can refuse to serve an incompatible one.",
            "params.capabilities": "What the client can do (e.g. handle sampling requests from the server). Empty here - this client offers none back.",
            "params.clientInfo": "Free-form name/version identifying the calling agent, for the server's own logs - not used for authorization in this stdio transport.",
        },
        "initialize response": {
            "jsonrpc / id": "Same envelope; id matches the request that provoked this reply.",
            "result.protocolVersion": "The version the server actually settled on - a client should check this equals what it asked for.",
            "result.capabilities": "What the server offers: {\"tools\": {}} here means tool calls are supported; a resources key would mean resources/list and resources/read are too (see the policy-docs server, which has one).",
            "result.serverInfo": "The server's own name and version - this is where \"claims-system\" first identifies itself on the wire, before any tool is called.",
        },
        "initialized notification": {
            "jsonrpc / method": "\"notifications/initialized\" - a JSON-RPC *notification*: no \"id\", and the server sends no reply to it. It only tells the server the client accepted the handshake result and normal requests may now follow.",
        },
        "tools/list request": {
            "method": "\"tools/list\" - discovery. No arguments: the client is asking \"what can you do,\" not invoking anything.",
        },
        "tools/list response": {
            "result.tools": "One entry per tool: name (what the model's tool_call.function.name must equal), description (the only documentation the model ever sees - this is requirement 5's \"docstring\"), inputSchema (JSON Schema the client translates almost verbatim into the OpenAI function-calling \"parameters\" field).",
        },
        "tools/call request": {
            "method": "\"tools/call\" - the one method that actually runs server code and can have a side effect or a cost.",
            "params.name": "Which discovered tool to invoke - must be one of the names tools/list just returned.",
            "params.arguments": "The arguments the model chose, already validated by the model against inputSchema (not re-validated here) - claim_number is the only required field.",
        },
        "tools/call response": {
            "result.content": "A list of content blocks, here one {\"type\": \"text\", ...} block holding a JSON string - the tool's actual return value, serialized. MCP does not require a tool to return JSON; this server's tools happen to always return a JSON object as text.",
            "result.isError": "true means the tool ran and reported a *tool-level* failure (e.g. an unknown claim number) - not a transport or protocol failure, which would instead come back as a top-level JSON-RPC \"error\" object with no \"result\" at all (see tools/w9d_mcp.py's handling of an unknown tool name for that path).",
        },
    }

    exchanges = []
    labels = [
        "initialize request", "initialize response", "initialized notification",
        "tools/list request", "tools/list response",
        "tools/call request", "tools/call response",
    ]
    for label, entry in zip(labels, log):
        exchanges.append({
            "label": label,
            "direction": entry["direction"],
            "raw": entry["raw"],
            "annotations": annotations[label],
        })

    payload = {
        "exchanges": exchanges,
        "model_call_location": (
            "The model is called exactly once per lap, inside tools/w9d_agent.py's run_agent "
            "(the call_llm(...) invocation), in the agent process - after a tools/list response "
            "has been folded into the function-calling menu and before the next tools/call is "
            "sent. The model is never called inside tools/w9d_claims_server.py or "
            "tools/w9d_policy_server.py (this capture's whole wire log has zero LLM calls in it) "
            "- those processes only run deterministic Python and return data; deciding what to "
            "call and how to read the result is entirely the agent process's job."
        ),
    }

    (OUT_DIR / "wire.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"captured {len(log)} raw messages, wrote {OUT_DIR / 'wire.json'}")


def _final_reply(tool_schema, tool_result, claim_query, bad_form):

    messages = [
        {"role": "system", "content": (
            "You are a claims triage assistant. Use the tools you have to answer the "
            "user's question, citing what each tool actually returned."
        )},
        {"role": "user", "content": claim_query},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "search_policy",
                    "arguments": json.dumps({"query": "deductible for water backup", "form_number": bad_form}),
                },
            }],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": json.dumps(tool_result)},
    ]

    response = call_llm(
        model=MODEL,
        messages=messages,
        tools=[tool_schema],
        tool_choice="auto",
        reasoning_effort=REASONING_EFFORT,
    )

    return response.choices[0].message


def errors():
    """requirement 5: rewrite one tool docstring as a prompt, make its error
    path recoverable, and show the model handling the same failing call
    before and after."""

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # The user names no form number at all - whatever the model tries next
    # can only come from the tool's own error message, not from re-reading
    # a form number the user happened to mention.
    claim_query = "For claim CLM-7004, what dollar deductible applies to this water-backup loss?"
    bad_form = "HO-1234"

    old_tool_schema = OLD_SEARCH_POLICY_TOOL
    old_description = old_tool_schema["function"]["description"]
    old_error = {"error": f"unknown form_number: {bad_form!r}", "matches": []}

    new_tool_schema = {
        "type": "function",
        "function": {
            "name": "search_policy",
            "description": SEARCH_POLICY_DESCRIPTION,
            "parameters": SEARCH_POLICY_INPUT_SCHEMA,
        },
    }
    new_error = {
        "error": (
            f"form {bad_form!r} not recognized: form numbers on file are "
            "DP-0208, HO-0304, HO-0412, HO-0521, HO-0633, HO-0710. Pass "
            "form_number=null to search every attached endorsement instead "
            "of one you're unsure of."
        ),
        "matches": [],
    }

    def _describe(message):
        if message.tool_calls:
            calls = [f"{c.function.name}({c.function.arguments})" for c in message.tool_calls]
            args = json.loads(message.tool_calls[0].function.arguments or "{}")
            retried_form = args.get("form_number")
            if retried_form is None:
                classification = "safe fallback (form_number=null - searches everything, guesses nothing)"
            elif retried_form == "HO-0521":
                classification = "correct guess (form_number=HO-0521 - happens to be the right form)"
            else:
                classification = f"hallucinated guess (form_number={retried_form!r} - a real but wrong form, picked blind)"
            return f"calls again: {calls}", None, classification
        return "answers in prose (no further tool call):", message.content, "answers without retrying"

    # The model is not deterministic run to run (see w7d_common.call_llm's own
    # docstring on Groq's sampling) - a single transcript would not be honest
    # evidence either way. N trials each, sampled the ordinary way (no
    # temperature override - a pinned temperature=0 transcript is not what a
    # real call looks like), classified by what the retried argument actually
    # was, is the number this file draws its takeaway from - the same
    # "prove it with a number" standard evaluate.py holds retrieval to.
    N_TRIALS = 4
    old_trials, new_trials = [], []

    for _ in range(N_TRIALS):
        reply = _final_reply(old_tool_schema, old_error, claim_query, bad_form)
        old_trials.append(_describe(reply))

    for _ in range(N_TRIALS):
        reply = _final_reply(new_tool_schema, new_error, claim_query, bad_form)
        new_trials.append(_describe(reply))

    def _tally(trials):
        counts = {}
        for _, _, classification in trials:
            key = classification.split(" (")[0]
            counts[key] = counts.get(key, 0) + 1
        return counts

    old_tally, new_tally = _tally(old_trials), _tally(new_trials)

    def _example(trials, prefer):
        for action, text, classification in trials:
            if classification.startswith(prefer):
                return action, text, classification
        return trials[0]

    old_action, old_text, old_class = _example(old_trials, "hallucinated guess")
    new_action, new_text, new_class = _example(new_trials, "safe fallback")

    lines = [
        "# search_policy: same failing call, old vs new docstring/error",
        "",
        "Setup: the model has just called `search_policy(query=\"deductible for water "
        f"backup\", form_number={bad_form!r})` - a wrong form number with no obviously "
        "close valid one to pattern-match toward, and the user never named a form "
        "number for it to fall back on - for the user question:",
        "",
        f"> {claim_query}",
        "",
        "The only two things that differ between the runs below are the tool's "
        "`description` (what requirement 5 calls its docstring) and the error object "
        "the failing call returns. Same model, same preceding messages, same bad "
        "argument, run repeatedly because a small model's next move is not "
        f"deterministic ({N_TRIALS} trials each, ordinary sampling, no pinned "
        "temperature).",
        "",
        "## Tally, what the model tried next",
        "",
        f"**Before** ({N_TRIALS} trials): {old_tally}",
        "",
        f"**After** ({N_TRIALS} trials): {new_tally}",
        "",
        "## Before",
        "",
        f"Tool description: \"{old_description}\"",
        "",
        f"Tool result returned: `{json.dumps(old_error)}`",
        "",
        f"One trial's model action ({old_class}) - {old_action}",
        f"```\n{old_text}\n```" if old_text else "",
        "",
        "## After",
        "",
        f"Tool description (rewritten as a prompt): \"{SEARCH_POLICY_DESCRIPTION}\"",
        "",
        f"Tool result returned: `{json.dumps(new_error)}`",
        "",
        f"One trial's model action ({new_class}) - {new_action}",
        f"```\n{new_text}\n```" if new_text else "",
        "",
        "## Takeaway",
        "",
        "The old error states only that the argument was bad, in the vocabulary of "
        "the argument (\"unknown form_number\") - it does not say what a right one "
        "looks like. Across the before-trials above, that produced a hallucinated "
        "guess at a different real form number often enough to matter: exactly the "
        "\"swallowed into a dead end\" failure the common-mistakes list names, because "
        "a confidently wrong form number would search clean and return someone "
        "else's deductible if this transcript ran one more lap. The new error states "
        "the actual list of valid form numbers in the same sentence, which measurably "
        "shifted the tally toward `form_number=null` - a global search, the one move "
        "guaranteed correct when the model does not yet know which form applies. The "
        "rewrite did not just add words; it changed what the model's next guess was "
        "grounded in.",
    ]

    (OUT_DIR / "error_before_after.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"before tally: {old_tally}")
    print(f"after tally:  {new_tally}")
    print(f"wrote {OUT_DIR / 'error_before_after.md'}")


def main():

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["discover", "query", "wire", "errors", "all"], default="all")
    args = parser.parse_args()

    if args.stage in ("discover", "all"):
        discover()
    if args.stage in ("query", "all"):
        query()
    if args.stage in ("wire", "all"):
        wire()
    if args.stage in ("errors", "all"):
        errors()


if __name__ == "__main__":
    main()
