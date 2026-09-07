"""The 10 claims Task Set D races the agent against the workflow on.

Not sampled from traffic - Week 5/6 traffic never ran a claims-triage
agent, only claim summarisation. These are written by hand against the
real endorsement text in endorsement_content.py, the same source
tools/make_endorsements.py renders into insurance_docs/*.pdf, so a search
against tools/w7d_policy_corpus.py and a search against the indexed PDFs
would find the same clause.

Each claim carries a `golden` outcome computed by hand from that source
text - the coverage position, the deductible, and the payout after it -
so tools/w7d_race.py can grade both systems the same way evaluate.py
grades retrieval: by checking a number against a known-correct one, not
by asking a second model whether the first model's answer sounds right.

`dependency=True` marks the three claims (c04, c06, c08) required by Task
Set D §2.3: cases where step 3 cannot be decided until step 2's *specific
result* is read, not just its presence. In each, the notes alone are
ambiguous or misleading about the outcome:

  c04 - filed as a HO-0304 water claim, but HO-0304's own exclusion table
        (E-19) redirects sewer back-up to HO-0521 - which form has the
        controlling deductible is not knowable before that first search
        returns.
  c06 - the notes say the roof was "dented", which reads like the E-34
        cosmetic exclusion, but the clause note reverses that the moment
        a co-occurring penetration is also read.
  c08 - the notes describe a home-sharing occupant causing damage, which
        reads as excluded by E-50, and only the day-count in the notes
        against the 14-day exception in the clause (found by the search)
        settles whether the exception rescues it - it doesn't here, but
        the workflow has to actually check.

A fixed workflow can hard-code a branch for each of these because there
are only three shapes. An agent has no such ceiling. The race is what
tells you whether that ceiling was ever actually the wrong size for a
10-claim day - see results_week7d.md.
"""

CLAIMS = [
    {
        "claim_id": "c01",
        "claim_number": "CLM-7001",
        "claimant": "[CLAIMANT-A1]",
        "date_of_loss": "2026-02-03",
        "policy_line": "homeowners",
        "form_number": "HO-0304",
        "reported_loss_amount": 18000,
        "coverage_a_limit": None,
        "notes": (
            "Supply line to the dishwasher ruptured abruptly on 2026-02-03 "
            "while the insured was home. Heat was maintained throughout the "
            "winter at normal levels. Water was shut off within an hour of "
            "discovery and the area was dry within two days. Damage to "
            "kitchen flooring and cabinetry, estimated 18,000."
        ),
        "dependency": False,
    },
    {
        "claim_id": "c02",
        "claim_number": "CLM-7002",
        "claimant": "[CLAIMANT-A2]",
        "date_of_loss": "2026-01-14",
        "policy_line": "homeowners",
        "form_number": "HO-0304",
        "reported_loss_amount": 19600,
        "coverage_a_limit": None,
        "notes": (
            "Cold snap 12-14 Jan. Insured was away and had switched the "
            "heating off entirely for the nine days they were absent. Pipe "
            "in the unheated garage-side utility room froze and split, "
            "water leaking for an unknown period until a neighbour noticed. "
            "Water damage to the utility room, hall and part of the "
            "kitchen, estimated 19,600."
        ),
        "dependency": False,
    },
    {
        "claim_id": "c03",
        "claim_number": "CLM-7003",
        "claimant": "[CLAIMANT-A3]",
        "date_of_loss": "2026-02-20",
        "policy_line": "homeowners",
        "form_number": "HO-0304",
        "reported_loss_amount": 6200,
        "coverage_a_limit": None,
        "notes": (
            "Insured noticed a damp patch under the kitchen sink cabinet. "
            "On investigation, the supply line fitting had been dripping "
            "slowly for approximately three weeks before it was noticed. "
            "Water damage to the cabinet base and adjoining flooring, "
            "estimated 6,200."
        ),
        "dependency": False,
    },
    {
        "claim_id": "c04",
        "claim_number": "CLM-7004",
        "claimant": "[CLAIMANT-A4]",
        "date_of_loss": "2026-03-01",
        "policy_line": "homeowners",
        "form_number": "HO-0304",
        "reported_loss_amount": 14000,
        "coverage_a_limit": None,
        "notes": (
            "Heavy rain overnight; water backed up through the basement "
            "floor drain and flooded the finished basement. Not a supply "
            "line or appliance failure - the water came up through the "
            "drain itself. The home has a sump pump fitted with a battery "
            "backup, serviced by a technician six weeks ago with a service "
            "record on file. Damage to flooring, drywall and stored "
            "furniture, estimated 14,000."
        ),
        "dependency": True,
    },
    {
        "claim_id": "c05",
        "claim_number": "CLM-7005",
        "claimant": "[CLAIMANT-A5]",
        "date_of_loss": "2026-03-09",
        "policy_line": "homeowners",
        "form_number": "HO-0521",
        "reported_loss_amount": 9000,
        "coverage_a_limit": None,
        "notes": (
            "Sump pump overflowed during a storm, flooding part of the "
            "basement. Insured confirms the sump pump has no battery or "
            "secondary power source - the home lost mains power for two "
            "hours during the storm and the pump could not run. Estimated "
            "damage 9,000."
        ),
        "dependency": False,
    },
    {
        "claim_id": "c06",
        "claim_number": "CLM-7006",
        "claimant": "[CLAIMANT-A6]",
        "date_of_loss": "2026-03-15",
        "policy_line": "homeowners",
        "form_number": "HO-0412",
        "reported_loss_amount": 22000,
        "coverage_a_limit": 300000,
        "notes": (
            "Hail storm on 2026-03-15 dented the roof shingles and also "
            "penetrated the surfacing in two places, allowing water "
            "infiltration into the attic. Roof surfacing installed 8 years "
            "ago per the inspection record on file. Estimated damage "
            "22,000."
        ),
        "dependency": True,
    },
    {
        "claim_id": "c07",
        "claim_number": "CLM-7007",
        "claimant": "[CLAIMANT-A7]",
        "date_of_loss": "2026-03-15",
        "policy_line": "homeowners",
        "form_number": "HO-0412",
        "reported_loss_amount": 8000,
        "coverage_a_limit": 250000,
        "notes": (
            "Hail storm caused granule loss and surface scuffing across "
            "the roof. Insured confirms no leaks and no penetration of the "
            "roof surfacing was observed after inspection. Estimated cost "
            "to address appearance, 8,000."
        ),
        "dependency": False,
    },
    {
        "claim_id": "c08",
        "claim_number": "CLM-7008",
        "claimant": "[CLAIMANT-A8]",
        "date_of_loss": "2026-02-27",
        "policy_line": "homeowners",
        "form_number": "HO-0633",
        "reported_loss_amount": 11000,
        "coverage_a_limit": None,
        "notes": (
            "A guest staying at the property through a home-sharing "
            "platform accidentally started a kitchen fire that also caused "
            "water damage from the sprinkler system, during a 5-night "
            "stay. Insured's records show this guest's stay brings the "
            "total home-sharing nights for the policy year to 40 so far. "
            "Estimated damage 11,000."
        ),
        "dependency": True,
    },
    {
        "claim_id": "c09",
        "claim_number": "CLM-7009",
        "claimant": "[CLAIMANT-A9]",
        "date_of_loss": "2026-03-22",
        "policy_line": "dwelling_fire",
        "form_number": "DP-0208",
        "reported_loss_amount": 7500,
        "coverage_a_limit": None,
        "notes": (
            "Tenant-occupied unit under an active written tenancy "
            "agreement. Heavy rain caused the sewer to back up into the "
            "basement through the floor drain, damaging tenant belongings "
            "and finishes. Estimated damage 7,500."
        ),
        "dependency": False,
    },
    {
        "claim_id": "c10",
        "claim_number": "CLM-7010",
        "claimant": "[CLAIMANT-A10]",
        "date_of_loss": "2026-03-25",
        "policy_line": "dwelling_fire",
        "form_number": "DP-0208",
        "reported_loss_amount": 9400,
        "coverage_a_limit": None,
        "notes": (
            "Tenant-occupied unit under an active written tenancy "
            "agreement, tenant present at the time. Supply line to the "
            "washing machine ruptured suddenly; tenant shut off the water "
            "within the hour and reported it the same day. Estimated "
            "damage 9,400."
        ),
        "dependency": False,
    },
]

# The answer each claim would settle to if the exclusion tables, clause
# notes and deductible clauses in endorsement_content.py are read
# correctly. `payout` is what compute_payout must return; a system passes
# a claim when its coverage_status matches AND its payout is within $1 of
# this figure - see grade() in w7d_common.py.
GOLDEN = {
    "c01": {"status": "covered", "exclusion_code": None, "deductible": 2500, "payout": 15500},
    "c02": {"status": "excluded", "exclusion_code": "E-14", "deductible": None, "payout": 0},
    "c03": {"status": "excluded", "exclusion_code": "E-17", "deductible": None, "payout": 0},
    "c04": {"status": "covered", "exclusion_code": None, "deductible": 1000, "payout": 13000},
    "c05": {"status": "excluded", "exclusion_code": None, "deductible": None, "payout": 0},
    "c06": {"status": "covered", "exclusion_code": None, "deductible": 6000, "payout": 16000},
    "c07": {"status": "excluded", "exclusion_code": "E-34", "deductible": None, "payout": 0},
    "c08": {"status": "excluded", "exclusion_code": "E-50", "deductible": None, "payout": 0},
    "c09": {"status": "excluded", "exclusion_code": "E-78", "deductible": None, "payout": 0},
    "c10": {"status": "covered", "exclusion_code": None, "deductible": 5000, "payout": 4400},
}

CLAIMS_BY_ID = {claim["claim_id"]: claim for claim in CLAIMS}
