"""MCP server of our own: policy-wording search, scoped by product and date.

Run as `python tools/w12_policy_server.py`, spoken to over stdio by any MCP
client - the capstone's Thursday fresh-eyes reviewer is meant to be one that
isn't ours (tools/w12_external_client.py is a stand-alone stand-in for that
client, which shares no code with this repo).

Two tools. Both take the loss date as a *required* argument, and that is the
design: a search tool that treats the date as optional gets called without
it, and "no date" can only be answered with "the wording that ranks best",
which is the 2024-loss-against-2025-wording failure. Here the missing date
is an error that says how to fix the call, not a silent default.

The search runs the real Week 3-4 pipeline (hybrid retrieval, RRF, rerank)
through tools/w12_retrieval.py, with the date filter enforced in code.
"""

import os

from data.w12_wordings import PERIL_CLASSES, PRODUCT_FORMS
from w12_inforce import limits_for, parse_date
from w12_mcp import TracedMCPServer
from w12_pii import find_pii
from w9d_mcp import Tool

SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "What to look for, in the vocabulary of the wording "
                           "(e.g. 'flood exclusion dwelling river overflow').",
        },
        "product": {"type": "string", "enum": sorted(PRODUCT_FORMS),
                    "description": "Which product's wordings to search."},
        "loss_date": {"type": "string",
                      "description": "Date of loss, ISO format YYYY-MM-DD. The "
                                     "wording in force on this date is what is searched."},
        "top_k": {"type": ["integer", "null"],
                  "description": "How many passages to return. Defaults to 3."},
    },
    "required": ["query", "product", "loss_date"],
}

LIMITS_SCHEMA = {
    "type": "object",
    "properties": {
        "policy_number": {"type": "string", "description": "e.g. 'POL-H-1001'."},
        "loss_date": {"type": "string", "description": "Date of loss, YYYY-MM-DD."},
        "peril_class": {
            "type": "string",
            "enum": sorted({p for perils in PERIL_CLASSES.values() for p in perils}),
            "description": "The peril that best fits the loss. Household: flood "
                           "(rising river water), surface_water (rainfall pooling), "
                           "escape_of_water (burst or leaking pipes), theft, fire, "
                           "other. Motor: flood, collision, other.",
        },
    },
    "required": ["policy_number", "loss_date", "peril_class"],
}


def _bad_date(value):
    try:
        parse_date(value)
        return None
    except (ValueError, TypeError):
        return {"error": f"loss_date {value!r} is not a valid date; pass it as "
                         "YYYY-MM-DD, e.g. '2024-08-11'. Read it from the claim "
                         "intake rather than guessing.", "matches": []}


def _search(args):

    problem = _bad_date(args.get("loss_date"))

    if problem:
        return problem

    product = args.get("product")

    if product not in PRODUCT_FORMS:
        return {"error": f"product {product!r} not recognised; use one of "
                         f"{', '.join(sorted(PRODUCT_FORMS))}.", "matches": []}

    # Imported here, not at module top: loading the engine costs seconds and
    # `tools/list` must answer instantly, before any model is loaded.
    from w12_retrieval import search_wording

    # W12_DATE_FILTER=0 is the "before" arm of the bonus challenge: the same
    # engine, scoped to the product but blind to the date. It exists so the
    # RED run is the system as it was, not a reconstruction of it.
    date_filter = os.environ.get("W12_DATE_FILTER", "1") != "0"

    complete = os.environ.get("W12_COMPLETE_PAIRS", "1") != "0"

    return search_wording(args["query"], product, args["loss_date"],
                          top_k=args.get("top_k") or 3, date_filter=date_filter,
                          complete_pairs=complete)


def _limits(args):

    problem = _bad_date(args.get("loss_date"))

    if problem:
        return problem

    return limits_for(args.get("policy_number"), args["loss_date"], args.get("peril_class"))


def build_server():

    server = TracedMCPServer("policy-wording", "1.0.0", wire_guard=find_pii)

    server.add_tool(Tool(
        name="search_policy_wording",
        description=(
            "Search the policy wording (clauses and exclusion tables) for one "
            "product as it stood on the date of loss. Returns passages with "
            "their form number, edition date, the date range that edition was "
            "in force, and `cite_as` - the clause numbers and exclusion codes "
            "you may cite from each passage. Only editions in "
            "force on loss_date are searched, so every passage returned is one "
            "that may be cited for this loss; `editions_in_force` and "
            "`notices` say which forms had no edition in force on that date. "
            "Call this after checking the policy was in force. It does not "
            "look up a claim and does not compute deductibles."
        ),
        input_schema=SEARCH_SCHEMA,
        handler=_search,
    ))

    server.add_tool(Tool(
        name="get_limits",
        description=(
            "Look up the deductible, the sub-limit and the policy limit for a "
            "policy, peril and loss date. These are three different numbers: "
            "the deductible is what the insured bears first, the sub-limit "
            "caps one peril, the policy limit caps everything. They come from "
            "the limits table for the wording edition in force on loss_date - "
            "never read them out of a wording passage. sub_limit is null where "
            "the peril has none. Returns an error if no edition was in force."
        ),
        input_schema=LIMITS_SCHEMA,
        handler=_limits,
    ))

    return server


if __name__ == "__main__":

    # Pay the engine's load and first-query cost at boot, not on the first
    # request: a cold first search is ~75 s on this machine, and a latency
    # figure that includes it describes the start-up, not the service.
    if os.environ.get("W12_WARM", "1") != "0":
        import contextlib
        import sys

        from w12_retrieval import search_wording

        # stdout is the JSON-RPC channel; the engine prints while loading.
        with contextlib.redirect_stdout(sys.stderr):
            search_wording("warm-up", "household", "2025-06-01", top_k=1)

    build_server().serve_forever()
