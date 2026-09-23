"""MCP server two: the claims-system server - claim status by claim number,
and the adjuster note history behind it. Run as
`python tools/w9d_claims_server.py`, spoken to over stdio.

Framed as the platform team's third-party server (problem statement §1), not
this team's own code - see eval/w9d/risk_note.md for what that trust
boundary actually means. It is bolted onto the agent by config alone: see
tools/data/w9d_mcp_config.step1.json vs tools/data/w9d_mcp_config.json and
eval/w9d/agent_diff.txt for the diff (none) this produces in
tools/w9d_agent.py.

Built over the same 10 claims Week 7 Task Set D used
(tools/data/w7d_claims.py) so a claim number here resolves to the same
underlying claim a policy search would - but exposed as the claims *system*
would expose it: status and notes are two separate calls, because that is
what the problem statement asks this server for, not one do-everything
get_claim like Week 7's tool.
"""

from data.w7d_claims import CLAIMS_BY_ID
from w9d_mcp import MCPServer, Tool

CLAIMS_BY_NUMBER = {claim["claim_number"]: claim for claim in CLAIMS_BY_ID.values()}

# Synthesized system status - Week 7's claim record models a claim *file*,
# never a claim *system*, so there is no status field to reuse; picked by
# hand per claim_id to spread across open/closed/paid/denied rather than
# leaving every claim in one state.
STATUS_BY_CLAIM_NUMBER = {
    "CLM-7001": "closed - paid",
    "CLM-7002": "closed - denied",
    "CLM-7003": "closed - denied",
    "CLM-7004": "open - under review",
    "CLM-7005": "closed - denied",
    "CLM-7006": "open - under review",
    "CLM-7007": "closed - denied",
    "CLM-7008": "closed - denied",
    "CLM-7009": "closed - denied",
    "CLM-7010": "open - under review",
}

_VALID_NUMBERS = ", ".join(sorted(CLAIMS_BY_NUMBER))

GET_CLAIM_STATUS_SCHEMA = {
    "type": "object",
    "properties": {
        "claim_number": {
            "type": "string",
            "description": "The public claim number, e.g. 'CLM-7004'.",
        },
    },
    "required": ["claim_number"],
}

GET_ADJUSTER_NOTES_SCHEMA = {
    "type": "object",
    "properties": {
        "claim_number": {
            "type": "string",
            "description": "The public claim number, e.g. 'CLM-7004'.",
        },
    },
    "required": ["claim_number"],
}


def _not_found(claim_number):
    # The same recoverable shape requirement 5 puts on our own server's
    # search_policy error - a typo'd claim number reads as a claim number,
    # not as "the claims system is down," and the message says what a valid
    # one looks like instead of just failing.
    return {"error": f"claim {claim_number!r} not found: claim numbers on file look like {_VALID_NUMBERS}."}


def _get_claim_status_handler(args):
    claim_number = args.get("claim_number")
    claim = CLAIMS_BY_NUMBER.get(claim_number)

    if claim is None:
        return _not_found(claim_number)

    return {
        "claim_number": claim_number,
        "status": STATUS_BY_CLAIM_NUMBER.get(claim_number, "unknown"),
        "claimant": claim["claimant"],
        "date_of_loss": claim["date_of_loss"],
        "form_number": claim["form_number"],
    }


def _get_adjuster_notes_handler(args):
    claim_number = args.get("claim_number")
    claim = CLAIMS_BY_NUMBER.get(claim_number)

    if claim is None:
        return _not_found(claim_number)

    return {"claim_number": claim_number, "notes": claim["notes"]}


def build_server():
    server = MCPServer(name="claims-system", version="0.1.0")

    server.add_tool(Tool(
        name="get_claim_status",
        description=(
            "Look up one claim's current status in the claims system by its "
            "public claim number (e.g. 'CLM-7004'). Returns the status, "
            "claimant, date of loss and form number. Does not return adjuster "
            "notes and does not search policy wording - call "
            "get_adjuster_notes or search_policy for those."
        ),
        input_schema=GET_CLAIM_STATUS_SCHEMA,
        handler=_get_claim_status_handler,
    ))

    server.add_tool(Tool(
        name="get_adjuster_notes",
        description=(
            "Fetch the adjuster note history for one claim by its public "
            "claim number. Returns the notes verbatim, exactly as the "
            "adjuster wrote them - nothing in this system sanitizes them. "
            "Does not return claim status and does not search policy wording."
        ),
        input_schema=GET_ADJUSTER_NOTES_SCHEMA,
        handler=_get_adjuster_notes_handler,
    ))

    return server


if __name__ == "__main__":
    build_server().serve_forever()
