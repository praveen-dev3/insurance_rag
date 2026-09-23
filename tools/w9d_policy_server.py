"""MCP server one: policy-document search - the agent's OWN server, run as
`python tools/w9d_policy_server.py` and spoken to over stdio.

Wraps the same tools/w7d_policy_corpus.py keyword search Week 7 Task Set D
used, so a result found here is word-for-word what that search already
returns - this file changes how the search is *reached* (MCP tool call
instead of an in-process function call) and how its edges are *described*
(requirement 5: the tool description rewritten as a prompt, and the
unrecognized-form-number error made recoverable), not what it searches.

Exposes one tool (search_policy) and one resource (the exclusions schedule,
attached context rather than a model-invoked call - see the module docstring
on tools/w9d_claims_server.py's neighbour, and the Task Set D "common
mistakes" list, for why that split matters).
"""

from data.endorsement_content import ENDORSEMENTS
from w7d_policy_corpus import FORM_NUMBERS, search_policy_corpus
from w9d_mcp import MCPServer, Resource, Tool

SEARCH_POLICY_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": (
                "What to search for, in the vocabulary of the clause where "
                "possible (e.g. 'sudden and accidental discharge freezing "
                "plumbing system')."
            ),
        },
        "form_number": {
            "type": ["string", "null"],
            "enum": FORM_NUMBERS + [None],
            "description": (
                "Restrict the search to one form number. Pass null (or omit "
                "it) to search every attached endorsement."
            ),
        },
        "top_k": {
            "type": ["integer", "null"],
            "description": "How many results to return. Defaults to 3.",
        },
    },
    "required": ["query"],
}

# Requirement 5, first half: the old description ("Search the endorsement
# wording for text matching a query, optionally scoped to one form number...")
# only stated what the tool does. This one is written as a prompt: it tells
# the model *when* to call it and what to do with a redirect, the same way
# the Week 7 agent's SYSTEM_PROMPT used to have to spell out by hand - see
# eval/w9d/error_before_after.md for the before/after this produces.
SEARCH_POLICY_DESCRIPTION = (
    "Search the attached homeowners and dwelling-fire endorsement wording for "
    "text matching a query, optionally scoped to one form number. Returns the "
    "top matching clauses and exclusion-table rows, each with its form "
    "number, clause label and exclusion code. "
    "Call this before stating any coverage position - a status decided from "
    "notes alone, without checking what the policy wording actually excludes, "
    "is not grounded. If a result redirects to another form (for example "
    "'see Form HO-0521'), call this again scoped to that form before "
    "deciding. Known form numbers: " + ", ".join(FORM_NUMBERS) + ". Pass "
    "form_number=null to search every attached endorsement at once - do that "
    "first whenever you are not yet sure which form governs, rather than "
    "guessing a form number. This tool only searches wording; it does not "
    "fetch a claim file and does not compute a payout."
)


def _search_policy_handler(args):
    query = args.get("query")
    form_number = args.get("form_number")
    top_k = args.get("top_k") or 3

    # Requirement 5, second half: an unrecognized form_number used to fall
    # straight through to search_policy_corpus's own filter, which just
    # returns no rows for a form it doesn't recognize - indistinguishable
    # from "the wording was searched and nothing matched." That silence is
    # exactly the "swallowed into a dead end" trap Task Set D's common-
    # mistakes list warns about: the model has no way to tell a typo'd form
    # number from a real, searched, empty result, and states a coverage
    # position with no clause behind it either way. This fails loud instead,
    # in the same vocabulary the fix names: the actual list of valid forms.
    if form_number and form_number not in FORM_NUMBERS:
        return {
            "error": (
                f"form {form_number!r} not recognized: form numbers on file "
                f"are {', '.join(FORM_NUMBERS)}. Pass form_number=null to "
                "search every attached endorsement instead of one you're "
                "unsure of."
            ),
            "matches": [],
        }

    return {"matches": search_policy_corpus(query, form_number=form_number, top_k=top_k)}


def _exclusions_schedule_reader():
    """Every exclusion-table row, across every attached endorsement.

    Exposed as a *resource*, not a tool - it is context the app should have
    already attached, not something the model should have to spend a turn
    calling out for. See the Task Set D "common mistakes" list.
    """

    lines = []

    for form in ENDORSEMENTS:
        for kind, payload in form["blocks"]:
            if kind != "t":
                continue
            for code, description, disposition in payload["rows"]:
                lines.append(f"{form['form_number']} {code}: {description} -> {disposition}")

    return "\n".join(lines)


def build_server():
    server = MCPServer(name="policy-docs", version="1.0.0")

    server.add_tool(Tool(
        name="search_policy",
        description=SEARCH_POLICY_DESCRIPTION,
        input_schema=SEARCH_POLICY_INPUT_SCHEMA,
        handler=_search_policy_handler,
    ))

    server.add_resource(Resource(
        uri="policy://exclusions-schedule",
        name="Exclusions schedule",
        description="Every exclusion-table row across every attached endorsement, by form and code.",
        mime_type="text/plain",
        reader=_exclusions_schedule_reader,
    ))

    return server


if __name__ == "__main__":
    build_server().serve_forever()
