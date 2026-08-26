"""The Week 6 evaluation claims: 23 authored, plus 2 replayed from traces.

Held apart from tools/claims_population.py on purpose. That file is the
week of traffic the Week 5 taxonomy was built by reading; this one is the
eval set the Week 6 numbers are measured on. Reusing the traffic as the
eval set would mean every number is reported on the cases the taxonomy was
derived from, which measures how well the taxonomy describes its own
source rather than how the app behaves.

The two regression cases are the exception, and they are the exception on
purpose: they are lifted verbatim out of real failed traces, `source_trace_id`
and all, so that the specific thing that went wrong in production has a
row in the eval that will go red if it comes back.

The scenarios were written to span the failure modes, NOT to be uniformly
hard or uniformly easy. Several are cases the app should get right; if a
25-case set contains no case the app handles, the pass rate cannot fall
and so it cannot detect a regression either.

Every claim number here is fictional and every claimant name is invented.
They exist so that the redaction path has something to redact and so that
the claim-number assertion has something to check.
"""

# Each entry becomes one ClaimFile. `expect` is a note to the human
# labeller about what the wording actually says - it is NOT read by the
# app, the assertions or the judge, and exists so a disagreement can be
# adjudicated later against something written down rather than remembered.

W6_CLAIMS = [
    {
        "id": "w6-01",
        "claim_number": "CLM-2026-05101",
        "claimant": "Aurelia Katsaridis",
        "date_of_loss": "2026-04-03",
        "policy_line": "homeowners",
        "form_number": "HO-0304",
        "notes": """Flexible connector under the kitchen sink failed
        abruptly at around 6am, insured was home and heard it. Water across
        the kitchen and into the hall. Stopcock shut within ten minutes,
        restoration firm attended same day. Connector retained. Notified us
        that afternoon. Building damage 8,900.""",
        "expect": "Sudden and accidental under Clause 2.1; E-17 does not "
                  "reach it; $2,500 deductible under Clause 5.3.",
    },
    {
        "id": "w6-02",
        "claim_number": "CLM-2026-05104",
        "claimant": "Ptolemy Vansittart",
        "date_of_loss": "2026-03-11",
        "policy_line": "homeowners",
        "form_number": "HO-0304",
        "notes": """Insured reports the utility room floor has been damp
        "on and off since around Christmas". Plumber found a pinhole in the
        hot feed weeping steadily. Wet rot to the joists. That is roughly
        eleven weeks of escape. Mould to the cavity, remediation quoted
        18,000, building damage 12,000.""",
        "expect": "E-17 applies absolutely (seepage 14+ days). Mould is "
                  "additionally capped at $10,000 by Clause 5.2.",
    },
    {
        "id": "w6-03",
        "claim_number": "CLM-2026-05107",
        "claimant": "Winnifred Oduya-Marsh",
        "date_of_loss": "2026-04-18",
        "policy_line": "homeowners",
        "form_number": "HO-0412",
        "notes": """Hail 18 April. Roof inspected 24 April. Dents to ridge
        capping and bruising across the south slope, some granule loss. No
        penetration, water-shedding function intact per the inspector, no
        interior damage. Roof installed 2021 per the inspection record.
        Insured's contractor quoting a full replacement at 34,000.""",
        "expect": "E-34 excludes cosmetic damage absolutely. Roof age is "
                  "irrelevant once E-34 bites. 2% deductible, min $1,000.",
    },
    {
        "id": "w6-04",
        "claim_number": "CLM-2026-05110",
        "claimant": "Casimir Brandolini",
        "date_of_loss": "2026-04-18",
        "policy_line": "homeowners",
        "form_number": "HO-0412",
        "notes": """Same 18 April storm, different risk. Hail punched
        through the surfacing in four places on the west slope, decking
        exposed, water into the loft and down into a bedroom ceiling. Roof
        installed 2007, insured has the original invoice. Coverage A
        430,000. Damage 26,000 including interior.""",
        "expect": "E-34 does NOT apply (penetration). Roof is 19 years old, "
                  "so Clause 2.2 settles on actual cash value, not RCV.",
    },
    {
        "id": "w6-05",
        "claim_number": "CLM-2026-05113",
        "claimant": "Hyacinth Nwabueze",
        "date_of_loss": "2026-02-28",
        "policy_line": "homeowners",
        "form_number": "HO-0521",
        "notes": """Sump overflowed during heavy rain, finished basement
        flooded to 150mm. Pump is four years old. Insured produced dated
        service invoices for each of the last two years matching the
        manufacturer's annual schedule. Battery backup fitted, tested by our
        electrician, holds for about eleven hours. Damage 28,000.""",
        "expect": "Covered under Clause 2.1. E-44 does not apply (records "
                  "produced). Clause 2.2 satisfied (>=8h backup). $1,000 "
                  "deductible, $25,000 annual aggregate.",
    },
    {
        "id": "w6-06",
        "claim_number": "CLM-2026-05116",
        "claimant": "Ferdinand Achterhof",
        "date_of_loss": "2026-02-28",
        "policy_line": "homeowners",
        "form_number": "HO-0521",
        "notes": """Same storm. Sump pump seized, basement took water.
        Insured has never had the pump serviced - confirmed in writing, no
        records exist, manufacturer schedule requires an annual test. There
        IS a battery backup and it works. Damage 19,500.""",
        "expect": "E-44 excludes absolutely - failure to maintain, service "
                  "or test to the manufacturer schedule.",
    },
    {
        "id": "w6-07",
        "claim_number": "CLM-2026-05119",
        "claimant": "Rosalind Tchaikovskaya",
        "date_of_loss": "2026-03-07",
        "policy_line": "homeowners",
        "form_number": "HO-0521",
        "notes": """Back-up through the basement shower. Pump serviced
        annually, records fine. However there is no secondary power source
        fitted at all - never has been, confirmed on inspection. Mains power
        did not fail during the event; the pump simply could not keep up.
        Damage 16,000.""",
        "expect": "Clause 2.2 voids cover under this endorsement outright: "
                  "absence of a secondary power source at the time of loss. "
                  "Note it voids regardless of whether power failed.",
    },
    {
        "id": "w6-08",
        "claim_number": "CLM-2026-05122",
        "claimant": "Barnabas Ekwueme",
        "date_of_loss": "2026-01-26",
        "policy_line": "homeowners",
        "form_number": "HO-0633",
        "notes": """Short-let guest tripped on a rug and broke a wrist.
        Booked through a platform, two nights. Insured's rental log is
        contemporaneous and shows 9 days let in the current policy year.
        Guest claiming 22,000 in medical costs.""",
        "expect": "E-53 disapplied by Clause 4.2 - within the 14-day "
                  "allowance in Clause 4.1. Adjudicated under base liability.",
    },
    {
        "id": "w6-09",
        "claim_number": "CLM-2026-05125",
        "claimant": "Millicent Obiageli",
        "date_of_loss": "2026-02-14",
        "policy_line": "homeowners",
        "form_number": "HO-0633",
        "notes": """Short-let guest injured on the stairs. Platform
        statement shows 63 nights let so far this policy year. Insured keeps
        no rental log of her own. Guest claiming 45,000.""",
        "expect": "E-53 excludes absolutely; 63 nights is far outside the "
                  "14-day allowance, and Clause 5.1 raises the presumption "
                  "against the insured anyway for want of a log.",
    },
    {
        "id": "w6-10",
        "claim_number": "CLM-2026-05128",
        "claimant": "Evander Ravensworth",
        "date_of_loss": "2026-03-30",
        "policy_line": "homeowners",
        "form_number": "HO-0633",
        "notes": """Insured repairs bicycles from the garage. Gross receipts
        about 4,100 last year per his accountant. Customers do drop bikes off
        at the house - he confirms roughly two visits a week. A customer
        tripped in the driveway and is claiming 9,000.""",
        "expect": "The Clause 4.3 incidental exception requires BOTH "
                  "receipts under $5,000 AND no customer visits. Visits "
                  "occur, so the exception fails and the E-50 series bites.",
    },
    {
        "id": "w6-11",
        "claim_number": "CLM-2026-05131",
        "claimant": "Theodora Blackwood-Amadi",
        "date_of_loss": "2026-03-22",
        "policy_line": "dwelling_fire",
        "form_number": "DP-0208",
        "notes": """Tenanted rental. Supply pipe to the bathroom basin split
        abruptly. Tenant in occupation under a written tenancy at the date of
        loss. Reported to us 28 March. Water damage 19,000. On attending we
        also found mould to the bathroom wall cavity, remediation quoted
        7,600.""",
        "expect": "Water damage covered under Clause 2.1. But E-76 excludes "
                  "mould ABSOLUTELY on this line with NO sublimit - unlike "
                  "HO-0304's $10,000. $5,000 deductible.",
    },
    {
        "id": "w6-12",
        "claim_number": "CLM-2026-05134",
        "claimant": "Ignatius Featherstonehaugh",
        "date_of_loss": "2026-02-09",
        "policy_line": "dwelling_fire",
        "form_number": "DP-0208",
        "notes": """Rental standing empty since the last tenancy ended on 21
        September. That is about 20 weeks. Pipe in the utility split, water
        found by a neighbour. No inspection records produced for the vacant
        period. Damage 31,000.""",
        "expect": "E-72 excludes absolutely - plumbing water damage in a "
                  "dwelling vacant more than 60 consecutive days. Clause 4.1 "
                  "90-day inspection condition also breached.",
    },
    {
        "id": "w6-13",
        "claim_number": "CLM-2026-05137",
        "claimant": "Perpetua Vandersteen",
        "date_of_loss": "2026-04-11",
        "policy_line": "dwelling_fire",
        "form_number": "DP-0208",
        "notes": """Tenant vacated after a dispute and, on his own admission
        in a text message the landlord has provided, left the bath running
        with the overflow taped over. Two floors of water damage, 52,000.
        Rent was 71 days in arrears at the date of loss.""",
        "expect": "E-73 (deliberate damage by a tenant) excludes absolutely. "
                  "E-77 independently excludes: rent more than 60 days in "
                  "arrears at the date of loss.",
    },
    {
        "id": "w6-14",
        "claim_number": "CLM-2026-05140",
        "claimant": "Cornelius Ashworth-Diallo",
        "date_of_loss": "2026-04-24",
        "policy_line": "homeowners",
        "form_number": None,
        "notes": """River burst its banks after three days of rain. Water
        into the ground floor to about 300mm. Whole ground floor, contents
        and finishes, 61,000. Nothing on the premises failed - this is
        surface water from the river.""",
        "expect": "E-10 excludes flood/surface water absolutely on the "
                  "homeowners line. Not a HO-0304 claim at all.",
    },
    {
        "id": "w6-15",
        "claim_number": "CLM-2026-05143",
        "claimant": "Genevieve Osazuwa",
        "date_of_loss": "2026-01-17",
        "policy_line": "homeowners",
        "form_number": "HO-0304",
        "notes": """Cold snap. Insured away for two weeks, heating switched
        off entirely at the boiler. Pipe in the unheated rear extension froze
        and split. Water ran for some days. Damage to the extension, hall and
        kitchen, 24,000.""",
        "expect": "E-14 excludes freezing loss unless heat maintained at "
                  "55F or above. Heat was off, so it bites. E-12 also in "
                  "play only if vacant 60+ days, which it was not.",
    },
    {
        "id": "w6-16",
        "claim_number": "CLM-2026-05146",
        "claimant": "Anastasios Papadimitriou",
        "date_of_loss": "2025-12-02",
        "policy_line": "homeowners",
        "form_number": "HO-0304",
        "notes": """Insured discovered a washing machine hose failure on 2
        December and dealt with it himself. He has only now called us - the
        call was taken on 14 April, so 133 days after discovery. He says he
        did not think it was worth claiming until the floor started lifting.
        Claim presented at 21,000.""",
        "expect": "Clause 4.1 requires notice within 30 days of discovery; "
                  "notice at 133 days voids coverage for the loss unless the "
                  "insured shows it could not reasonably have been given "
                  "sooner, which on these facts he cannot.",
    },
    {
        "id": "w6-17",
        "claim_number": "CLM-2026-05149",
        "claimant": "Leocadia Whitmore-Nkemelu",
        "date_of_loss": "2026-04-06",
        "policy_line": "homeowners",
        "form_number": "HO-0412",
        "notes": """Windstorm. Pool screen enclosure destroyed, quote 14,000.
        Two fence panels and a gate down, 3,400. A satellite dish came off
        the gable, 600 to refit. No damage to the dwelling roof. Coverage A
        580,000.""",
        "expect": "E-33 caps screening at $2,500; E-37 caps fences/gates at "
                  "$5,000; E-31 excludes the dish absolutely. Three "
                  "different dispositions in one claim.",
    },
    {
        "id": "w6-18",
        "claim_number": "CLM-2026-05152",
        "claimant": "Sebastiano Quattrocchi",
        "date_of_loss": "2026-04-06",
        "policy_line": "homeowners",
        "form_number": "HO-0412",
        "notes": """Fourth hail claim on this roof since 2021. Our inspector
        is clear that the current storm caused no breach and that what is
        present is accumulated bruising across four separate events, none of
        which individually breached the surfacing. Contractor pressing for
        replacement on a cumulative-damage argument.""",
        "expect": "E-38 excludes repeated hail impact over multiple storm "
                  "events where no single event caused breach. Absolutely.",
    },
    {
        "id": "w6-19",
        "claim_number": "CLM-2026-05155",
        "claimant": "Marguerite Adeyemi-Strand",
        "date_of_loss": "2026-03-28",
        "policy_line": "homeowners",
        "form_number": "HO-0304",
        "notes": """Radiator valve failed suddenly, water damage to two
        rooms, 11,400. Insured had the failed valve thrown out by his plumber
        before we attended, so we cannot inspect it. Insured also asks
        whether we will pay to replace the radiator itself, and for the
        tear-out of the wall to reach the pipework, quoted at 3,200.""",
        "expect": "Clause 2.2: tear-out covered, the appliance/system itself "
                  "NOT (E-15). Clause 4.3: disposal may prejudice the claim "
                  "to the extent our investigation is impaired - which is a "
                  "qualified consequence, not an automatic denial.",
    },
    {
        "id": "w6-20",
        "claim_number": "CLM-2026-05158",
        "claimant": "Octavian Mbeki-Laurent",
        "date_of_loss": "2026-02-21",
        "policy_line": "homeowners",
        "form_number": "HO-0521",
        "notes": """Sewer back-up. This insured has had three prior back-up
        claims with us since 2021. No remediation certificate has ever been
        provided. Pump serviced, backup power fine. Family have been in a
        hotel for 38 days and counting. Damage 24,000 plus loss of use.""",
        "expect": "E-49 excludes UNLESS remediation is certified; none is, "
                  "so it bites. E-48 independently excludes loss of use "
                  "beyond thirty days.",
    },
    {
        "id": "w6-21",
        "claim_number": "CLM-2026-05161",
        "claimant": "Wilhelmina Osterhagen",
        "date_of_loss": "2026-04-29",
        "policy_line": "homeowners",
        "form_number": None,
        "notes": """Earthquake. Chimney cracked and now leaning, render
        cracked on two elevations. Structural engineer booked. Insured asking
        whether this is covered and what his excess would be.""",
        "expect": "Nothing in the retrieved endorsements addresses "
                  "earthquake at all. The correct answer is UNDETERMINED - "
                  "the wording does not settle it.",
    },
    {
        "id": "w6-22",
        "claim_number": "CLM-2026-05164",
        "claimant": "Emmerich Vasquez-Oyelaran",
        "date_of_loss": "2026-03-15",
        "policy_line": "homeowners",
        "form_number": "HO-0304",
        "notes": """Water in the basement. Source genuinely not established:
        could be groundwater through the block work (there is efflorescence
        and the water table is high after the thaw) or could be the washing
        machine drain. Plumber would not commit either way. Contents damage
        6,800.""",
        "expect": "Turns entirely on cause. E-11 excludes subsurface water "
                  "pressure absolutely; a drain failure is a HO-0521 "
                  "question. The condition is unresolved and the summary "
                  "should say so rather than pick one.",
    },
    {
        "id": "w6-23",
        "claim_number": "CLM-2026-05167",
        "claimant": "Persephone Achebe-Lindqvist",
        "date_of_loss": "2026-04-02",
        "policy_line": "homeowners",
        "form_number": "HO-0304",
        "notes": """Dishwasher supply line let go while the insured was out
        for the afternoon. Perhaps four hours of discharge. Kitchen floor,
        cabinets and the ceiling of the room below. Reported next morning.
        Failed line retained. Damage 15,700. Insured also wants the
        dishwasher replaced, 780, and asks about the emergency drying bill
        of 2,100 that he paid himself on the night.""",
        "expect": "Covered under 2.1 (four hours is not seepage). E-15 "
                  "excludes the dishwasher itself. Clause 4.2 says "
                  "protective costs are covered and NOT subject to the "
                  "Clause 5.3 deductible.",
    },
]
