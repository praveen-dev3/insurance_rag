# Fresh-eyes note - NOT DONE

The capstone asks for a reviewer from another squad to call the policy-wording MCP server live, and for a note on
who they were, where they stumbled and what changed. **That review has not happened.** Nobody from another squad
ran anything, so there is no reviewer name, no squad, and no stumble to report, and this file does not invent one.

## What exists instead (and what it is worth)

`tools/w12_external_client.py` is a stand-alone MCP client - standard library only, no import from this repo - that
spawns the server and does what a cold reviewer would: `initialize`, `tools/list`, read the descriptions, call each
tool, then try three wrong calls (no loss date, unknown product, a loss before any wording existed). Its output is
in `eval/w12/external_client_run.txt`. Every call succeeded and every error message said how to recover.

That proves the server speaks the protocol to a client that shares none of our code. It does **not** substitute for
the review, because I wrote the client and the server in the same sitting: it can only find the stumbles I could
already imagine. Things a stranger will probably still hit, listed so they are not a surprise:

- the first connect takes 30 s warm and 2-3 minutes cold while the server loads its models and answers a warm-up
  query; a client with a short initialize timeout will give up;
- `loss_date` is required and has no default, on purpose - a reviewer who calls `search_policy_wording` with just a
  query gets an error, and the error text is the documentation;
- the server expects to be launched from the repo root with the project's `.venv` Python;
- `get_limits` takes a `peril_class` enum whose values are only explained in the tool description.

## To close this properly

Hand `python tools/w12_policy_server.py` (and nothing else) to someone from another squad, and ask them to
connect their own client without reading `tools/`. Record their name and squad, where they stalled (watch the
first connect), and what you change. Put it here.
