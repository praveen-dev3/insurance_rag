"""MCP server: the claims records - FNOL intake and policy in-force checks.

Run as `python tools/w12_claims_server.py`. The agent discovers these tools
from tools/list; nothing in the agent names them.

This is the server the brief's PII warning is about. The claim file holds
the claimant's name, address and injury description, and "your MCP server
will hand whatever you don't redact to another squad's agent". So `get_fnol`
returns a *view*, built field by field: identifiers and facts the triage
needs (policy number, loss date, the redacted account of the loss, the
reported amount), and nothing else. Adding a field to the record does not
add it to the view; the view has to be edited on purpose.

The answer key (`truth`) is in the same data module as the claims - this
server never reads it, and the wire guard would catch a name or injury
that slipped into any response regardless.
"""

from data.w12_claims import CLAIMS_BY_NUMBER
from data.w12_wordings import POLICIES
from w12_inforce import editions_for_product, parse_date, policy_in_force
from w12_mcp import TracedMCPServer
from w12_pii import find_pii, redact_narrative
from w9d_mcp import Tool

CLAIM_NUMBERS = ", ".join(sorted(CLAIMS_BY_NUMBER)[:3]) + ", ..."


def _get_fnol(args):

    claim = CLAIMS_BY_NUMBER.get(args.get("claim_number"))

    if claim is None:
        return {"error": f"claim {args.get('claim_number')!r} not found; claim "
                         f"numbers look like {CLAIM_NUMBERS}."}

    return {
        "claim_number": claim["claim_number"],
        "policy_number": claim["policy_number"],
        "loss_date": claim["loss_date"],
        "reported_cause": redact_narrative(claim),
        "reported_amount": claim["reported_amount"],
    }


def _lookup_policy(args):

    policy = POLICIES.get(args.get("policy_number"))

    if policy is None:
        return {"error": f"policy {args.get('policy_number')!r} not found; policy "
                         "numbers look like POL-H-1001 (household) or POL-M-2001 (motor)."}

    return {
        "policy_number": args["policy_number"],
        "product": policy["product"],
        "policy_limit": policy["policy_limit"],
        "in_force_ranges": [[s.isoformat(), e.isoformat()] for s, e in policy["ranges"]],
    }


def _check_in_force(args):

    policy = POLICIES.get(args.get("policy_number"))

    if policy is None:
        return {"error": f"policy {args.get('policy_number')!r} not found."}

    try:
        parse_date(args.get("loss_date"))
    except (ValueError, TypeError):
        return {"error": f"loss_date {args.get('loss_date')!r} is not a valid date; "
                         "pass YYYY-MM-DD taken from the claim intake."}

    in_force, matching, reason = policy_in_force(args["policy_number"], args["loss_date"])

    return {
        "policy_number": args["policy_number"],
        "loss_date": args["loss_date"],
        "in_force": in_force,
        "matching_range": list(matching) if matching else None,
        "reason": reason,
        "product": policy["product"],
        "wording_editions_in_force": editions_for_product(policy["product"], args["loss_date"]),
    }


def build_server():

    server = TracedMCPServer("claims-records", "1.0.0", wire_guard=find_pii)

    server.add_tool(Tool(
        name="get_fnol",
        description=(
            "Fetch the first notice of loss for one claim by claim number "
            "(e.g. 'CLM-2026-80001'): policy number, loss date, a redacted "
            "account of the loss, and the reported amount. Claimant names, "
            "addresses and injury details are removed. Does not check the "
            "policy and does not search wording."
        ),
        input_schema={"type": "object", "properties": {
            "claim_number": {"type": "string", "description": "The public claim number."}},
            "required": ["claim_number"]},
        handler=_get_fnol,
    ))

    server.add_tool(Tool(
        name="lookup_policy",
        description=(
            "Look up a policy by policy number: its product (household or "
            "motor), its policy limit (the sum insured) and the date ranges "
            "it has been in force. Does not take a loss date and does not "
            "say whether the policy was in force on one - use "
            "check_coverage_in_force for that."
        ),
        input_schema={"type": "object", "properties": {
            "policy_number": {"type": "string"}}, "required": ["policy_number"]},
        handler=_lookup_policy,
    ))

    server.add_tool(Tool(
        name="check_coverage_in_force",
        description=(
            "Check whether a policy was in force on the date of loss. Returns "
            "in_force (true/false), the in-force range that matched, the "
            "product, and which wording editions were in force on that date. "
            "Do this before reading any wording: a loss outside the in-force "
            "ranges is referred as not in force, whatever the wording says. "
            "This checks dates only; it says nothing about whether the peril "
            "is covered."
        ),
        input_schema={"type": "object", "properties": {
            "policy_number": {"type": "string"},
            "loss_date": {"type": "string", "description": "YYYY-MM-DD, from the FNOL."}},
            "required": ["policy_number", "loss_date"]},
        handler=_check_in_force,
    ))

    return server


if __name__ == "__main__":
    build_server().serve_forever()
