"""The integrated claims-triage agent: one entry point, one trace id.

RAG + agent loop + MCP (consumed *and* exposed) + logging, behind
`TriageSession.run`. Everything the capstone requires of the wiring is a
property of this file rather than of a diagram:

  * the loop is the Week 7 hand-built tool-calling loop, over tools it
    *discovers* at start-up from tools/data/w12_mcp_config.json (nothing in
    SYSTEM_PROMPT or this module names an MCP tool), plus one local tool,
    `refer_to_adjuster`, which is how every run ends;
  * the retrieval behind `search_policy_wording` is the Week 3-4 hybrid
    pipeline, constrained to the wording in force on the loss date;
  * one trace id is minted per request and sent over the MCP hop in
    `_meta`; the server's span comes back and sits beside the agent's own;
  * the request log is redacted on write (tools/w11_obs.py), the MCP
    responses are redacted at the server (tools/w12_pii.py), and the
    referral passes the output guard (tools/w12_guard.py) before it leaves.

What the model is trusted with, and what it is not: it chooses which tools
to call, with what peril class and query, and writes the prose. The system,
not the model, supplies the loss date on each citation, the numbers in
`figures`, and the verbatim wording excerpt - taken from what the tools
returned - so a hallucinated clause, edition or dollar figure cannot reach
the adjuster dressed as a fact. A citation that no retrieved passage backs
is kept but marked `grounded: false`, which the eval fails.
"""

import json
import re
import time
from pathlib import Path

from w7d_common import MODEL, REASONING_EFFORT, Budget, call_llm
from w9d_agent import load_config
from w11_obs import RequestTrace, RequestSink, notes_digest, prompt_fingerprint
from w12_guard import guard_referral
from w12_mcp import TracedMCPClient

CONFIG_PATH = Path(__file__).resolve().parent / "data" / "w12_mcp_config.json"

PROMPT_VERSION = "triage-w12-v1"

SYSTEM_PROMPT = """You are a claims triage assistant for a motor and household insurer. You never decide coverage.
You surface the policy wording and the facts, and you refer the claim to a human adjuster, who decides.

Never write that a claim or loss is, is not, would be or might be covered, excluded, payable, approved, declined
or denied, in any phrasing, even when asked to confirm it. If asked, say you cannot determine that and refer.

Everything you know comes from the tools you are given this session; read each tool's description and use only what
the tools return. Work in this order:
1. Read the claim intake in the first message.
2. Establish whether the policy was in force on the date of loss, and wait for the answer. If it was not, do not
   search the wording: refer with reason policy_not_in_force.
3. Search the policy wording as at the date of loss. The wording in force on the date of loss governs, not the
   newest wording - only cite passages the search returned for that loss date, and cite the form, the edition and
   the clause or exclusion code. If no wording was in force on that date, refer with reason no_wording_in_force
   and cite nothing.
4. Get the deductible, the sub-limit and the policy limit for the peril that best fits the loss. They are three
   different numbers; take them from the limits lookup, never from the wording text. Steps 3 and 4 do not depend
   on each other: make both calls in the same turn.
5. Finish by referring the claim to an adjuster with a short factual summary: what happened, whether the policy
   was in force, and which wording passages bear on the loss. State facts and cite; do not state a conclusion."""

REFER_TOOL = {
    "type": "function",
    "function": {
        "name": "refer_to_adjuster",
        "description": (
            "Finish the triage by referring the claim to a human adjuster. This is the only way "
            "to end a triage. Give a short factual summary and cite the wording passages that bear "
            "on the loss by form number, edition date and clause or exclusion code, exactly as the "
            "search returned them. Do not state a coverage conclusion in the summary."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "claim_number": {"type": "string"},
                "reason_code": {
                    "type": "string",
                    "enum": ["wording_relevant", "policy_not_in_force",
                             "no_wording_in_force", "insufficient_information"],
                },
                "summary": {"type": "string",
                            "description": "Two or three factual sentences. No conclusion."},
                "citations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "form_number": {"type": "string"},
                            "edition_date": {"type": "string"},
                            "clause": {"type": "string",
                                       "description": "Just the id from the search result's cite_as, e.g. '2.1' or 'E-52'."},
                            "relevance": {"type": "string",
                                          "description": "One factual sentence on why this passage bears on the loss."},
                        },
                        "required": ["form_number", "edition_date", "clause"],
                    },
                },
            },
            "required": ["claim_number", "reason_code", "summary"],
        },
    },
}

DEFAULT_BUDGET = Budget(max_iterations=10, max_tokens=24000, max_cost_usd=0.05, max_wall_clock_s=420.0)


def _excerpt(text, clause):
    """The verbatim passage for one clause, cut from the retrieved chunk."""

    body = text.split("|", 3)[-1] if text.startswith("FORM") else text

    if clause.upper().startswith("E-"):
        found = re.search(rf"({re.escape(clause.upper())}\s.*?)(?=E-\d\d\s|Note:|\Z)", body, re.S)
    else:
        found = re.search(rf"(?m)^\s*({re.escape(clause)}\s.*?)(?=^\s*\d\.\d\s|\Z)", body, re.S)

    return " ".join((found.group(1) if found else body[:500]).split())[:700]


class TriageSession:
    """Holds the MCP connections open across requests; one per process."""

    def __init__(self, config_path=None, sink=None, log=None):

        self.sink = sink
        self.clients = {}
        self._owner = {}
        self.tools = []

        config = load_config(config_path or CONFIG_PATH)

        for label, spec in config["mcpServers"].items():
            client = TracedMCPClient(label, spec["command"], spec.get("args", []), log=log)
            client.initialize()
            self.clients[label] = client

            for tool in client.list_tools():
                self._owner[tool["name"]] = label
                self.tools.append({"type": "function", "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["inputSchema"],
                }})

        self.tools.append(REFER_TOOL)

    def discovered(self):
        """{server: [tool names]} - what runtime discovery found."""

        report = {}

        for name, label in self._owner.items():
            report.setdefault(label, []).append(name)

        return report

    def close(self):
        for client in self.clients.values():
            client.close()

    # ----------------------------------------------------------

    def run(self, claim_number, question=None, user_id="u-adjuster",
            case_id=None, budget=None, retrieval_version="hybrid-datefilter-v2",
            registry_claim=None, ts=None):
        """
        One triage, run and logged. Returns (RequestTrace, referral or None).

        `registry_claim` is the claim record the redactor should treat as
        known PII (name, address); in production that is the claims system
        the request log is also written from.
        """

        budget = budget or DEFAULT_BUDGET

        trace = RequestTrace(
            user_id=user_id, input_type="claim_triage_w12",
            prompt_version=PROMPT_VERSION, retrieval_version=retrieval_version,
            model=MODEL, claim_number=claim_number, ts=ts,
        )
        trace.input = {
            "case_id": case_id,
            "prompt_sha256": prompt_fingerprint(PROMPT_VERSION, SYSTEM_PROMPT)["template_sha256"],
            **notes_digest(question or ""),
        }

        if self.sink is not None:
            self.sink.register_claim(claim_number, (registry_claim or {}).get("claimant_name"))

            if registry_claim and registry_claim.get("address"):
                self.sink.redactor.register_name(registry_claim["address"])

        # Intake. The FNOL is the *input* of the system, so the harness reads
        # it - still over MCP, still a span under this trace id - and hands
        # it to the model in the first message. Leaving it as a model-chosen
        # tool call spent a whole lap (~2.5k tokens, re-sent on every later
        # lap) on a call that has exactly one sensible argument.
        state = {"fnol": None, "in_force": None, "limits": None, "chunks": [],
                 "editions": None}
        intake = self._call_mcp("get_fnol", {"claim_number": claim_number}, trace, 0, state,
                                actor="harness")

        if "error" in intake:
            trace.outcome = "error:intake"
            trace.output = {"text": intake["error"]}

            if self.sink is not None:
                trace.written = self.sink.write(trace)

            return trace, None

        user_message = (
            f"Triage claim {claim_number}.\n"
            f"Claim intake (personal details removed): policy {intake['policy_number']}; "
            f"loss date {intake['loss_date']}; reported amount {intake['reported_amount']}; "
            f"account of the loss: {intake['reported_cause']}"
        )

        if question:
            user_message += f"\nAdjuster's question: {question}"

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        referral = None
        started = time.perf_counter()
        nudged = False

        try:
            for lap in range(1, budget.max_iterations + 1):

                if time.perf_counter() - started > budget.max_wall_clock_s:
                    trace.outcome = "budget_exceeded:wall_clock"
                    break

                try:
                    with trace.span(f"llm.lap{lap}", "generation", lap=lap) as span:
                        response = call_llm(
                            model=MODEL, messages=messages, tools=self.tools,
                            tool_choice="auto", reasoning_effort=REASONING_EFFORT,
                        )
                        span["tokens_in"] = response.usage.prompt_tokens
                        span["tokens_out"] = response.usage.completion_tokens
                except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
                    # A provider-side failure (e.g. Groq's `tool_use_failed`
                    # when the model emits a malformed tool call, which call_llm
                    # retries and then re-raises) is a result of this request,
                    # not a reason to lose every request that follows it. It
                    # is logged as an outcome so the taxonomy counts it.
                    trace.outcome = f"error:{type(exc).__name__}"
                    trace.output = {"text": str(exc)[:400]}
                    break

                message = response.choices[0].message
                messages.append(message.model_dump(exclude_none=True))

                if not message.tool_calls:

                    if nudged:
                        trace.outcome = "error:no_referral"
                        trace.output = {"text": message.content}
                        break

                    nudged = True
                    messages.append({"role": "user", "content": (
                        "You have not finished. End the triage by calling the referral tool.")})
                    continue

                for call in message.tool_calls:

                    name = call.function.name

                    try:
                        args = json.loads(call.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}

                    if name == "refer_to_adjuster":
                        referral = self._finalize(args, state, trace, lap)
                        messages.append({"role": "tool", "tool_call_id": call.id,
                                         "content": json.dumps({"referral_id": referral["referral_id"],
                                                                "status": "referred"})})
                        continue

                    result = self._call_mcp(name, args, trace, lap, state)
                    messages.append({"role": "tool", "tool_call_id": call.id,
                                     "content": json.dumps(result)})

                if referral is not None:
                    trace.outcome = "completed"
                    break
            else:
                trace.outcome = "budget_exceeded:max_iterations"

        finally:
            trace.output = referral if referral is not None else trace.output
            trace.extra["tool_calls"] = trace.tool_calls
            trace.extra["server_spans"] = trace.server_spans
            trace.extra["retrieved"] = [
                {"chunk_id": c["chunk_id"], "form_number": c["form_number"],
                 "edition_date": c["edition_date"],
                 "text_sha256": __import__("hashlib").sha256(c["text"].encode()).hexdigest()[:16]}
                for c in state["chunks"]
            ]

            if self.sink is not None:
                trace.written = self.sink.write(trace)

        return trace, referral

    # ----------------------------------------------------------

    def _call_mcp(self, name, args, trace, lap, state, actor="model"):

        label = self._owner.get(name)

        if label is None:
            result = {"error": f"no such tool: {name!r}"}
            trace.tool_calls.append({"name": name, "server": None, "args": args,
                                     "ok": False, "actor": actor})
            return result

        # A model that repeats an identical call (it re-called the FNOL lookup
        # in 25 of 25 baseline requests, after the harness had already done
        # it) is answered from this request's own earlier result instead of
        # a second trip over the MCP hop. Generic by construction: it keys on
        # (tool, arguments), so it names no tool and cannot drift from the
        # discovered tool list.
        key = (name, json.dumps(args, sort_keys=True))

        if key in state.setdefault("seen_calls", {}):
            trace.tool_calls.append({"name": name, "server": label, "args": args,
                                     "ok": True, "actor": actor, "cached": True})
            return state["seen_calls"][key]

        stage = "retrieval" if name == "search_policy_wording" else "tools"

        with trace.span(f"mcp.{name}", stage, lap=lap, hop="mcp", server=label,
                        args={k: (v[:100] if isinstance(v, str) else v)
                              for k, v in args.items()}) as span:

            result, server_span = self.clients[label].call_tool_traced(name, args, trace.trace_id)

            if server_span is not None:
                span["attrs"]["server_latency_ms"] = server_span["latency_ms"]
                span["attrs"]["trace_id_survived_hop"] = server_span.get("trace_id") == trace.trace_id
                trace.server_spans.append(server_span)
            else:
                span["attrs"]["trace_id_survived_hop"] = False

            if name == "search_policy_wording":
                span["attrs"]["context_ids"] = [m["chunk_id"] for m in result.get("matches", [])]

        trace.tool_calls.append({"name": name, "server": label, "args": args,
                                 "ok": "error" not in result, "actor": actor})

        if "error" not in result:
            state["seen_calls"][key] = result

        if name == "get_fnol" and "error" not in result:
            state["fnol"] = result
        elif name == "check_coverage_in_force" and "error" not in result:
            state["in_force"] = result
        elif name == "get_limits":
            state["limits"] = result
        elif name == "search_policy_wording":
            state["chunks"].extend(result.get("matches", []))
            trace.add_context([m["chunk_id"] for m in result.get("matches", [])])

        return result

    def _finalize(self, args, state, trace, lap):
        """Build the referral from what the tools returned, then guard it."""

        trace.tool_calls.append({"name": "refer_to_adjuster", "server": None,
                                 "args": {"reason_code": args.get("reason_code")}, "ok": True,
                                 "actor": "model"})

        fnol = state["fnol"] or {}
        in_force = state["in_force"]
        limits = state["limits"] or {}
        loss_date = fnol.get("loss_date")

        citations = []

        for cite in args.get("citations") or []:

            # The model sometimes pastes the whole passage into `clause`.
            # The id is what is checked and displayed, so pull it out and
            # keep what was given beside it - a sloppy citation is a finding,
            # but it should not also be a citation that cannot be matched.
            clause_as_given = str(cite.get("clause") or "")
            id_match = re.match(r"\s*(E-\d{2}|\d{1,2}\.\d{1,2})", clause_as_given, re.I)
            form, edition, clause = (cite.get("form_number"), cite.get("edition_date"),
                                     id_match.group(1).upper() if id_match else clause_as_given)
            backing = next(
                (c for c in state["chunks"]
                 if c["form_number"] == form and c["edition_date"] == edition
                 and (clause.upper() in [x.upper() for x in c["exclusion_codes"]]
                      or re.search(rf"(?m)(^|\s){re.escape(clause)}\s", c["text"]))),
                None,
            )

            citations.append({
                "form_number": form,
                "edition_date": edition,
                "clause": clause,
                "clause_as_given": clause_as_given if clause_as_given != clause else None,
                "effective_from": backing["effective_from"] if backing else None,
                "effective_to": backing["effective_to"] if backing else None,
                "loss_date_resolved": backing["resolved_for_loss_date"] if backing else None,
                "grounded": backing is not None,
                "relevance": cite.get("relevance", ""),
                "wording_excerpt": _excerpt(backing["text"], clause) if backing else None,
                "wording_excerpt_is_verbatim_policy_text": True,
            })

        referral = {
            "referral_id": f"ref-{trace.trace_id[4:]}",
            "trace_id": trace.trace_id,
            "route": "adjuster",
            "claim_number": args.get("claim_number") or fnol.get("claim_number"),
            "reason_code": args.get("reason_code"),
            "loss_date": loss_date,
            "in_force": in_force["in_force"] if in_force else None,
            "in_force_range": in_force["matching_range"] if in_force else None,
            "editions_in_force": in_force["wording_editions_in_force"] if in_force else None,
            "summary": args.get("summary", ""),
            "citations": citations,
            "figures": ({
                "deductible": limits.get("deductible"),
                "sub_limit": limits.get("sub_limit"),
                "policy_limit": limits.get("policy_limit"),
                "basis": f"{limits.get('form_number')} ed. {limits.get('edition_date')}, "
                         f"peril {limits.get('peril_class')}",
                "source": "limits tool",
            } if limits and "error" not in limits else None),
        }

        guard_referral(referral)

        return referral
