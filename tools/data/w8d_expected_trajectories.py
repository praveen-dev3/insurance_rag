"""Expected tool-call shapes for the Week 8 trajectory eval, one per claim in
tools/data/w7d_claims.py - same 10 claims, same agent (tools/w7d_agent.py),
same tools (tools/w7d_claims_tools.py). Task Set D's own agent already
exists; what did not exist yet is scoring *how* it got there, not just
whether the final number was right.

Each entry is a SET of accepted tool-name sequences, not one sequence -
Task Set D's own common-mistakes list calls out asserting a single exact
sequence as the thing that "scores correct runs as failures and inflates
your gap". Two axes of legitimate variation are accepted here:

  1. An excluded claim never needs a deductible, so one search_policy call
     is enough; a second, confirming search is also a reasonable path and
     is accepted, not penalised.
  2. A covered claim always needs a deductible figure, which the corpus
     rarely returns from the same search that finds the coverage/exclusion
     wording (see w7d_workflow.py's two-leg design and its docstring) - so
     two searches are the norm, and a third confirming search is accepted.

`required_forms` is the one thing NOT allowed to vary: the specific form
number(s) whose wording the golden answer in w7d_claims.GOLDEN actually
turns on. A trajectory that never scopes (or globally searches, form_number
= null covers every form) at least one call to each required form has not
actually opened the clause the decision depends on, regardless of how many
tool calls it spent - that is the "reached the payout without ever opening
the exclusions" failure Task Set D §1 names, made checkable in code.

`min_steps` is the shortest accepted shape's length (get_claim + every
search in the shortest accepted sequence + compute_payout), used as the
denominator for step efficiency.
"""

from data.w7d_claims import CLAIMS_BY_ID


def _shape(n_searches):
    """get_claim, n_searches x search_policy, compute_payout."""
    return ("get_claim",) + ("search_policy",) * n_searches + ("compute_payout",)


# excluded, no dependency: one search is enough (no deductible to find), a
# second confirming search is also a legitimate path.
_EXCLUDED_SIMPLE = {
    "accepted_shapes": [_shape(1), _shape(2)],
    "min_steps": 3,
    "needs_deductible_grounding": False,
}

# covered, no cross-form dependency: two searches are the norm (coverage
# leg + deductible leg - see w7d_workflow.py's docstring on why one query
# rarely surfaces both), a third confirming search is also legitimate.
_COVERED_SIMPLE = {
    "accepted_shapes": [_shape(2), _shape(3)],
    "min_steps": 4,
    "needs_deductible_grounding": True,
}

EXPECTED = {
    "c01": {
        **_COVERED_SIMPLE,
        "required_forms": {"HO-0304"},
        "note": "covered, no dependency: coverage leg + deductible leg on HO-0304.",
    },
    "c02": {
        **_EXCLUDED_SIMPLE,
        "required_forms": {"HO-0304"},
        "note": "excluded (E-14, unheated 9-day absence): one search on HO-0304 is enough.",
    },
    "c03": {
        **_EXCLUDED_SIMPLE,
        "required_forms": {"HO-0304"},
        "note": "excluded (E-17, seepage >=14 days): one search on HO-0304 is enough.",
    },
    "c04": {
        # dependency: HO-0304's E-19 redirects sewer back-up to HO-0521.
        # Both forms must be searched before compute_payout - as few as 2
        # calls (one per form, if each single call returns both its
        # coverage and deductible wording) or as many as 6 (both legs,
        # both forms, one call each). required_forms is the check that
        # actually matters; the count is left wide on purpose.
        "accepted_shapes": [_shape(n) for n in range(2, 7)],
        "min_steps": 4,
        "required_forms": {"HO-0304", "HO-0521"},
        "needs_deductible_grounding": True,
        "note": "dependency (redirect): must search HO-0304 AND the form its exclusion table names, HO-0521.",
    },
    "c05": {
        **_EXCLUDED_SIMPLE,
        "required_forms": {"HO-0521"},
        "note": "excluded (no secondary power source): one search on HO-0521 is enough.",
    },
    "c06": {
        **_COVERED_SIMPLE,
        "required_forms": {"HO-0412"},
        "note": "covered, dependency by reasoning only (no form redirect fires): same shape as c01, the risk is misreading the penetration clause, not under-searching.",
    },
    "c07": {
        **_EXCLUDED_SIMPLE,
        "required_forms": {"HO-0412"},
        "note": "excluded (E-34, cosmetic-only, no penetration): one search on HO-0412 is enough.",
    },
    "c08": {
        **_EXCLUDED_SIMPLE,
        "required_forms": {"HO-0633"},
        "note": "excluded (E-50, >14 home-sharing nights), dependency by reasoning only: one search on HO-0633 is enough.",
    },
    "c09": {
        **_EXCLUDED_SIMPLE,
        "required_forms": {"DP-0208"},
        "note": "excluded (E-78, tenant sewer back-up): one search on DP-0208 is enough.",
    },
    "c10": {
        **_COVERED_SIMPLE,
        "required_forms": {"DP-0208"},
        "note": "covered: coverage leg + deductible leg on DP-0208.",
    },
}

assert set(EXPECTED) == set(CLAIMS_BY_ID), "expected trajectory spec must cover exactly the 10 w7d claims"

# Every claim below has more than one accepted shape - see module docstring
# item 1/2 for why. Recorded explicitly so the eval report can point at it
# instead of asserting it by prose.
CLAIMS_WITH_ALTERNATE_PATHS = sorted(cid for cid, spec in EXPECTED.items() if len(spec["accepted_shapes"]) > 1)
