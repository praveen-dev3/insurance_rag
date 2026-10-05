"""Claims added in Week 11 Task Set D, on top of the ten from Week 7.

Each one is a failure the logs surfaced or a neighbour of it that guards
the same mechanism, so the suite grows by *observed* failures rather than
by claims someone thought of at a desk. `register()` folds them into the
same CLAIMS_BY_ID / GOLDEN dicts the Week 7-10 tools already read, which is
why nothing in w7d_claims_tools.py had to change to serve them.
"""

from data.w7d_claims import CLAIMS_BY_ID, GOLDEN

NEW_CLAIMS = [
    {
        # The drill's failure. Notes say "dimpled", "pitted", "for looks":
        # none of those words appear in the HO-0412 exclusion rows (which say
        # "marring, scuffing or granule loss" and "cosmetic damage"), so a
        # keyword search in the notes' own vocabulary lands on the coverage
        # basis clauses (2.1-2.3) and never on E-34 / E-36.
        "claim_id": "c11",
        "claim_number": "CLM-7011",
        "claimant": "[CLAIMANT-A11]",
        "date_of_loss": "2026-04-02",
        "policy_line": "homeowners",
        "form_number": "HO-0412",
        "reported_loss_amount": 9000,
        "coverage_a_limit": 250000,
        "notes": (
            "Hail left the south-facing shingles dimpled and pitted. The "
            "insured's roofer found the shingle surface intact, no leaks in "
            "the attic and no breach anywhere. Insured wants the slope "
            "replaced because it looks bad from the street, estimated 9,000."
        ),
        "dependency": False,
    },
    {
        # Same mechanism, opposite answer: the notes DO describe a breach, so
        # E-34 is reversed by the clause note and the claim is payable. It is
        # in the suite so that "always find the exclusion" cannot be fixed by
        # making the system say excluded for every hail claim.
        "claim_id": "c12",
        "claim_number": "CLM-7012",
        "claimant": "[CLAIMANT-A12]",
        "date_of_loss": "2026-04-09",
        "policy_line": "homeowners",
        "form_number": "HO-0412",
        "reported_loss_amount": 12000,
        "coverage_a_limit": 300000,
        "notes": (
            "Hail dented the roof surfacing and punched through the shingle "
            "mat over the back bedroom; water came through the ceiling the "
            "same night. Roofer confirms penetration. Repair estimate 12,000."
        ),
        "dependency": False,
    },
]

NEW_GOLDEN = {
    "c11": {"status": "excluded", "exclusion_code": "E-34", "deductible": None, "payout": 0},
    # 2% of 300,000 = 6,000 (above the 1,000 minimum): payout 12,000 - 6,000.
    "c12": {"status": "covered", "exclusion_code": None, "deductible": 6000, "payout": 6000},
}


def register():
    for claim in NEW_CLAIMS:
        CLAIMS_BY_ID[claim["claim_id"]] = claim
    GOLDEN.update(NEW_GOLDEN)
