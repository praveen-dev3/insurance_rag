"""The three tools: get_claim, search_policy, compute_payout.

One module so the agent's tool-calling loop and the workflow's direct
calls run the literal same Python functions - the race is agent-loop vs
fixed-workflow, not "two different implementations of get_claim that
happen to agree." Task Set D scores the third tool's description against
the first two, so all three are specified together, in the same voice, on
purpose.
"""

from data.w7d_claims import CLAIMS_BY_ID
from w7d_policy_corpus import FORM_NUMBERS, search_policy_corpus

# ------------------------------------------------------------------
# Tool schemas (OpenAI/Groq function-calling format)
# ------------------------------------------------------------------

GET_CLAIM_TOOL = {
    "type": "function",
    "function": {
        "name": "get_claim",
        "description": (
            "Fetch one claim's file header and adjuster notes by claim ID. "
            "Returns the claim number, claimant, date of loss, policy "
            "line, form number and reported loss amount on file, and the "
            "adjuster's notes verbatim. Does not search policy wording "
            "and does not compute a payout."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "claim_id": {
                    "type": "string",
                    "description": "The internal claim ID, e.g. 'c04'.",
                },
            },
            "required": ["claim_id"],
        },
    },
}

SEARCH_POLICY_TOOL = {
    "type": "function",
    "function": {
        "name": "search_policy",
        "description": (
            "Search the endorsement wording for text matching a query, "
            "optionally scoped to one form number. Returns the top "
            "matching clauses and exclusion-table rows with their form "
            "number and clause label. Does not fetch a claim file and "
            "does not compute a payout."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "What to search for, in the vocabulary of the "
                        "clause where possible (e.g. 'sudden and "
                        "accidental discharge freezing plumbing system')."
                    ),
                },
                "form_number": {
                    "type": ["string", "null"],
                    "enum": FORM_NUMBERS + [None],
                    "description": (
                        "Restrict the search to one form number. Pass "
                        "null to search every attached endorsement."
                    ),
                },
                "top_k": {
                    "type": ["integer", "null"],
                    "description": "How many results to return. Defaults to 3.",
                },
            },
            "required": ["query"],
        },
    },
}

# The third tool. Requirement 1 (§2.1): one job, an enum for claim status,
# no overlap with the two tools above. See results_week7d.md for the diff
# against the first draft, which failed all three of those.
COMPUTE_PAYOUT_TOOL = {
    "type": "function",
    "function": {
        "name": "compute_payout",
        "description": (
            "Compute the payable amount for one already-assessed claim: "
            "the loss amount minus the deductible when the claim is "
            "covered, zero otherwise. Does not decide coverage, does not "
            "fetch a claim file, and does not search policy wording - "
            "call get_claim and search_policy first and pass in what they "
            "found."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "claim_id": {
                    "type": "string",
                    "description": "The claim this payout is for.",
                },
                "claim_status": {
                    "type": "string",
                    "enum": ["covered", "excluded", "undetermined"],
                    "description": (
                        "The coverage position already reached from the "
                        "notes and the policy wording. 'undetermined' "
                        "returns a zero payout pending further review."
                    ),
                },
                "loss_amount": {
                    "type": ["number", "null"],
                    "description": "The reported loss amount in dollars.",
                },
                "deductible": {
                    "type": ["number", "null"],
                    "description": (
                        "The dollar deductible that applies, already "
                        "resolved from the policy wording (e.g. a flat "
                        "amount or a percentage of Coverage A already "
                        "converted to dollars). Pass null when "
                        "claim_status is not 'covered' - there is no "
                        "deductible to resolve for an excluded or "
                        "undetermined claim."
                    ),
                },
            },
            "required": ["claim_id", "claim_status"],
        },
    },
}

TOOLS = [GET_CLAIM_TOOL, SEARCH_POLICY_TOOL, COMPUTE_PAYOUT_TOOL]

# The naive first draft of the third tool - kept here (never wired into
# TOOLS) purely so results_week7d.md can diff it against the version
# above. It fails all three requirements: it does two jobs (decide *and*
# compute), "status" is a free string instead of an enum, and "handles
# the claim" overlaps both get_claim (which also "handles" the claim
# file) and search_policy (deciding coverage is what reading the policy
# wording is for).
COMPUTE_PAYOUT_TOOL_DRAFT = {
    "type": "function",
    "function": {
        "name": "compute_payout",
        "description": "Handles the claim decision and payout.",
        "parameters": {
            "type": "object",
            "properties": {
                "claim_id": {"type": "string"},
                "status": {"type": "string"},
                "amount": {"type": "number"},
            },
            "required": ["claim_id"],
        },
    },
}


# ------------------------------------------------------------------
# Implementations
# ------------------------------------------------------------------

def get_claim_impl(claim_id):

    claim = CLAIMS_BY_ID.get(claim_id)

    if claim is None:
        return {"error": f"no such claim: {claim_id!r}"}

    return {
        "claim_id": claim["claim_id"],
        "claim_number": claim["claim_number"],
        "claimant": claim["claimant"],
        "date_of_loss": claim["date_of_loss"],
        "policy_line": claim["policy_line"],
        "form_number": claim["form_number"],
        "reported_loss_amount": claim["reported_loss_amount"],
        "coverage_a_limit": claim["coverage_a_limit"],
        "notes": claim["notes"],
    }


def search_policy_impl(query, form_number=None, top_k=3):

    if form_number and form_number not in FORM_NUMBERS:
        return {"error": f"unknown form_number: {form_number!r}", "matches": []}

    matches = search_policy_corpus(query, form_number=form_number, top_k=top_k or 3)

    return {"matches": matches}


def compute_payout_impl(claim_id, claim_status, loss_amount=None, deductible=None):

    if claim_status not in ("covered", "excluded", "undetermined"):
        return {"error": f"unknown claim_status: {claim_status!r}"}

    if claim_status != "covered":
        return {"claim_id": claim_id, "claim_status": claim_status, "payout": 0.0}

    if loss_amount is None:
        return {"error": "loss_amount is required when claim_status is 'covered'"}

    deductible = deductible or 0

    payout = max(0.0, float(loss_amount) - float(deductible))

    return {"claim_id": claim_id, "claim_status": claim_status, "payout": payout}


DISPATCH = {
    "get_claim": lambda args: get_claim_impl(args["claim_id"]),
    "search_policy": lambda args: search_policy_impl(
        args["query"], args.get("form_number"), args.get("top_k", 3),
    ),
    "compute_payout": lambda args: compute_payout_impl(
        args["claim_id"], args["claim_status"], args.get("loss_amount"), args.get("deductible"),
    ),
}


def dispatch(name, arguments):

    handler = DISPATCH.get(name)

    if handler is None:
        return {"error": f"no such tool: {name!r}"}

    try:
        return handler(arguments)
    except (KeyError, TypeError, ValueError) as error:
        return {"error": f"bad arguments for {name}: {error}"}
