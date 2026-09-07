"""The week of claims traffic the Week 5 traces are drawn from.

Kept as source rather than as a fixture dumped from a live system, so the
sample the taxonomy is built on is reviewable in the diff and rebuildable
by anyone.

Two rules governed how these were written, and both matter for whether the
frequencies in the taxonomy mean anything:

  * They were written from the *claims desk* side — what an adjuster would
    plausibly send this app during a week — and NOT from the corpus side.
    Nothing here was written to trip a retriever, and nothing was tuned
    after seeing what the app did with it. Writing traffic that targets
    known weak spots produces a taxonomy whose frequencies describe the
    author's suspicions rather than the system.
  * The mix is weighted the way a homeowners water/wind desk is weighted:
    a lot of water and roof, some liability, a few things the corpus was
    never going to answer. A uniform spread across every form would be
    tidier and would misstate every frequency in the taxonomy.

Claimant names and claim numbers are fictional. They are here at all
because the redaction path has to have something to redact — a trace
pipeline tested only on text with no identifiers in it is a pipeline whose
redaction has never run.
"""

# ==================================================================
# CLAIM FILES -> the "summarise these notes" half of the traffic
# ==================================================================

CLAIM_FILES = [
    {
        "claim_id": "c01",
        "claim_number": "CLM-2026-04417",
        "claimant": "Priya Raghunathan",
        "date_of_loss": "2026-02-11",
        "policy_line": "homeowners",
        "form_number": "HO-0304",
        "notes": """Attended 11 Feb. Insured reports the braided hose to the
        upstairs basin let go some time overnight, water through the ceiling
        into the lounge below. Plumber attended same morning and capped it.
        Hose is retained in the garage. Insured called it in on the 12th.
        Damage to plasterboard ceiling, lounge carpet, and one wall. No sign
        of staining around the fitting before the event per insured. Coverage
        A limit 480,000.""",
    },
    {
        "claim_id": "c02",
        "claim_number": "CLM-2026-04418",
        "claimant": "Desmond Achterberg",
        "date_of_loss": "2026-01-29",
        "policy_line": "homeowners",
        "form_number": "HO-0304",
        "notes": """Insured noticed the hall carpet was damp "for a few weeks,
        maybe a month" before calling. Behind the wall there is a weeping joint
        on the hot feed, corroded, clearly long standing. Wet rot to the skirting
        and the subfloor. Plumber's report says the joint has been seeping "for
        a considerable period". Mould visible to the wall cavity, remediation
        quote 14,200.""",
    },
    {
        "claim_id": "c03",
        "claim_number": "CLM-2026-04421",
        "claimant": "Marisol Ferreira-Nunes",
        "date_of_loss": "2026-03-02",
        "policy_line": "homeowners",
        "form_number": "HO-0412",
        "notes": """Hail event 2 March. Roof inspected 9 March. Surfacing shows
        dents to the metal ridge capping and bruising to maybe 30 shingles,
        granule loss in patches. Inspector's note: no penetration, no lifted or
        cracked tabs, roof is shedding water normally, no interior water at all.
        Insured wants a full roof replacement. Roof installed 2019 per the
        inspection record. Coverage A 615,000.""",
    },
    {
        "claim_id": "c04",
        "claim_number": "CLM-2026-04425",
        "claimant": "Tobias Lindqvist",
        "date_of_loss": "2026-03-02",
        "policy_line": "homeowners",
        "form_number": "HO-0412",
        "notes": """Same 2 March storm. This one has actual holes - three
        shingles punched through on the west slope, decking exposed, water into
        the second bedroom. Ceiling down in that room. Insured cannot produce
        an installation date for the roof and there is no inspection record on
        file. Neighbour says the roof is "original to the house", built 2004.
        Coverage A 390,000.""",
    },
    {
        "claim_id": "c05",
        "claim_number": "CLM-2026-04430",
        "claimant": "Aoife Ni Bhraonain",
        "date_of_loss": "2026-02-19",
        "policy_line": "homeowners",
        "form_number": "HO-0521",
        "notes": """Basement back-up during the thaw. Sump pump did not run.
        Pump is nine years old. Insured says he has "never really touched it",
        no service records produced, and the manufacturer schedule calls for an
        annual test. There is a battery backup fitted and it tested fine.
        Finished basement, contents and flooring, quote 31,000.""",
    },
    {
        "claim_id": "c06",
        "claim_number": "CLM-2026-04431",
        "claimant": "Gareth Oyelaran",
        "date_of_loss": "2026-02-19",
        "policy_line": "homeowners",
        "form_number": "HO-0521",
        "notes": """Same thaw event, different insured. Sump pump seized.
        Insured produced dated service invoices for 2024 and 2025, both consistent
        with the manufacturer's annual schedule. Pump retained. Secondary power
        source: there is a battery unit but the electrician's report says it was
        dead and would not have carried the pump for any length of time. Water
        to 200mm in a finished basement.""",
    },
    {
        "claim_id": "c07",
        "claim_number": "CLM-2026-04436",
        "claimant": "Henrietta Vogelsang",
        "date_of_loss": "2026-01-08",
        "policy_line": "homeowners",
        "form_number": "HO-0633",
        "notes": """Guest fell on the internal stairs during a short-let stay
        and fractured a wrist. Booking was through a home-sharing platform, three
        nights. Insured's rental log shows the property was let for 10 days total
        in the current policy year and the log looks contemporaneous. Guest is
        pursuing the insured for medical costs, approx 18,000.""",
    },
    {
        "claim_id": "c08",
        "claim_number": "CLM-2026-04437",
        "claimant": "Ruslan Dzhaparidze",
        "date_of_loss": "2026-01-22",
        "policy_line": "homeowners",
        "form_number": "HO-0633",
        "notes": """Short-let guest slipped in the shower, head injury, ambulance
        attended. Insured has been letting the place most weekends - platform
        statement shows 41 nights let so far this policy year. No rental log kept
        by the insured, the 41 nights come off the platform statement we pulled.
        Claim from the guest for 60,000+.""",
    },
    {
        "claim_id": "c09",
        "claim_number": "CLM-2026-04440",
        "claimant": "Beatriz Colmenares",
        "date_of_loss": "2026-02-27",
        "policy_line": "dwelling_fire",
        "form_number": "DP-0208",
        "notes": """Tenanted rental. Pipe under the kitchen sink failed, water
        through the kitchen floor and into the unit below. Tenancy agreement in
        place and the tenant was living there at the date of loss. Notified us
        on 3 March. Damage includes visible mould to the base units by the time
        we attended on the 12th - remediation quoted at 9,400 separately from
        the 22,000 of water damage.""",
    },
    {
        "claim_id": "c10",
        "claim_number": "CLM-2026-04442",
        "claimant": "Fionnuala Mac Giolla Bhride",
        "date_of_loss": "2026-02-05",
        "policy_line": "dwelling_fire",
        "form_number": "DP-0208",
        "notes": """Rental property, previous tenancy ended 15 October, no new
        tenant since. Pipe froze and split, discovered 5 Feb when the neighbour
        saw water coming out under the door. Property had been empty about 16
        weeks. Insured says he drove past regularly but has no inspection
        records. Heating was off at the main. Damage 27,000.""",
    },
    {
        "claim_id": "c11",
        "claim_number": "CLM-2026-04445",
        "claimant": "Oluwaseun Adebanjo",
        "date_of_loss": "2026-03-18",
        "policy_line": "homeowners",
        "form_number": None,
        "notes": """River came up after two days of rain, water into the ground
        floor to about 400mm. Whole ground floor affected, contents and finishes.
        Insured is adamant this should be covered because "the water came from a
        burst somewhere upstream". Nothing on the premises failed - this is the
        river. Insured also holds a separate flood policy, details not yet on
        file.""",
    },
    {
        "claim_id": "c12",
        "claim_number": "CLM-2026-04449",
        "claimant": "Yevgenia Mstislavovna",
        "date_of_loss": "2026-01-14",
        "policy_line": "homeowners",
        "form_number": "HO-0304",
        "notes": """Cold snap 12-14 Jan. Insured was away. Pipe in the unheated
        garage-side utility room froze and split, water for an unknown period
        until the neighbour noticed. Insured confirms the heating was switched
        off entirely while away, house was empty about 9 days. Water damage to
        the utility room, hall and part of the kitchen, 19,600.""",
    },
    {
        "claim_id": "c13",
        "claim_number": "CLM-2026-04452",
        "claimant": "Bartholomew Nkemdirim",
        "date_of_loss": "2025-11-30",
        "policy_line": "homeowners",
        "form_number": "HO-0304",
        "notes": """Insured is only reporting this now (call taken 20 Feb).
        Says the dishwasher supply connector let go on 30 November, he "dealt
        with it himself" at the time and has now found the floor has lifted and
        the units are swollen. So notification is about 82 days after discovery.
        No prior contact on file, nothing logged. Claim now presented at
        16,800.""",
    },
    {
        "claim_id": "c14",
        "claim_number": "CLM-2026-04455",
        "claimant": "Anneliese Brockhausen",
        "date_of_loss": "2026-03-09",
        "policy_line": "homeowners",
        "form_number": "HO-0412",
        "notes": """Wind event. Screen enclosure over the pool is wrecked, frame
        twisted, screens gone. Quote to replace 11,500. Also two fence panels
        down at the rear, 2,100 to reinstate. No damage to the dwelling roof
        itself. Coverage A 520,000.""",
    },
    {
        "claim_id": "c15",
        "claim_number": "CLM-2026-04458",
        "claimant": "Sunniva Haugelund",
        "date_of_loss": "2026-02-02",
        "policy_line": "homeowners",
        "form_number": "HO-0304",
        "notes": """Washing machine hose failed, sudden, water across the
        kitchen and into the adjoining dining room. Insured shut the stopcock
        and called a restoration firm out of hours, they set driers, 1,850 for
        the emergency attendance. Reported to us the following morning. The
        machine itself is a write-off, insured wants that replaced too, 900.
        Building damage 12,300.""",
    },
    {
        "claim_id": "c16",
        "claim_number": "CLM-2026-04461",
        "claimant": "Ikaika Kahananui",
        "date_of_loss": "2026-01-19",
        "policy_line": "homeowners",
        "form_number": "HO-0521",
        "notes": """Sewer back-up through the downstairs shower. City main
        surcharged during heavy rain. Insured has had two previous back-up claims
        with us, 2022 and 2024. No remediation certificate on file from either.
        Sump pump present with battery backup, all serviced. Damage 21,000 plus
        loss of use, family in a hotel going on three weeks now.""",
    },
    {
        "claim_id": "c17",
        "claim_number": "CLM-2026-04463",
        "claimant": "Thandiwe Mokoena",
        "date_of_loss": "2026-02-24",
        "policy_line": "homeowners",
        "form_number": "HO-0633",
        "notes": """Insured runs a small pottery business from the garage.
        Annual receipts about 3,200 per her accountant. She sells online only,
        nobody comes to the property. A kiln fault caused a fire in the garage,
        damage to the garage and to about 4,000 of finished stock she was holding
        for an online order. Dwelling itself not affected.""",
    },
    {
        "claim_id": "c18",
        "claim_number": "CLM-2026-04466",
        "claimant": "Ferdinand Oyelowo-Achebe",
        "date_of_loss": "2026-03-21",
        "policy_line": "homeowners",
        "form_number": "HO-0304",
        "notes": """Slab leak. Insured noticed a warm patch on the floor about
        three weeks ago and the water bill was up, called a leak detection firm
        who found the hot supply under the slab weeping. Not a rupture - it has
        been going for a while, the firm says likely months. Floor coverings and
        the base of two walls affected. Tear-out to reach the pipe quoted at
        8,900, repair to the pipe 2,400.""",
    },
    {
        "claim_id": "c19",
        "claim_number": "CLM-2026-04470",
        "claimant": "Solveig Ravndal",
        "date_of_loss": "2026-03-05",
        "policy_line": "homeowners",
        "form_number": "HO-0412",
        "notes": """Third hail claim on this roof in four years - 2022, 2024 and
        now. Inspector says the current storm did not breach anything; what is
        there is accumulated bruising across the three events. No single event
        breached the surfacing. Insured's contractor is insisting on full
        replacement citing "cumulative damage". Roof installed 2016.""",
    },
    {
        "claim_id": "c20",
        "claim_number": "CLM-2026-04473",
        "claimant": "Chidinma Uzoamaka",
        "date_of_loss": "2026-02-14",
        "policy_line": "homeowners",
        "form_number": None,
        "notes": """Water into the basement, insured not sure of the source.
        Could be the sump, could be groundwater through the wall - there is
        efflorescence on the block work and the ground outside is saturated.
        Sump has a battery backup and was serviced last spring. Plumber could not
        say definitively. Damage to stored contents mainly, about 7,400.""",
    },
    {
        "claim_id": "c21",
        "claim_number": "CLM-2026-04477",
        "claimant": "Ezekiel Bamidele",
        "date_of_loss": "2026-01-31",
        "policy_line": "dwelling_fire",
        "form_number": None,
        "notes": """Tenanted property. Tenant admits he left a tap running into
        a blocked sink deliberately after an argument with the landlord about the
        deposit, then left. Substantial water damage through two floors, 44,000.
        Tenant has since vacated. Rent was also two months behind at the date of
        loss per the landlord's statement.""",
    },
    {
        "claim_id": "c22",
        "claim_number": "CLM-2026-04480",
        "claimant": "Perpetua Nwachukwu",
        "date_of_loss": "2026-03-12",
        "policy_line": "homeowners",
        "form_number": "HO-0304",
        "notes": """Supply line to the fridge water dispenser failed behind the
        unit. Sudden. Insured was home, heard it, shut it off within minutes.
        Small footprint - flooring in front of the fridge and the base of the
        cabinet, 4,100 total. Reported same day. Insured has thrown out the
        failed connector already, it went in the bin before we attended.""",
    },
    {
        "claim_id": "c23",
        "claim_number": "CLM-2026-04484",
        "claimant": "Gwendolyn Achterberg-Rhys",
        "date_of_loss": "2026-02-08",
        "policy_line": "homeowners",
        "form_number": "HO-0304",
        "notes": """Heating system leak, sudden failure of a radiator valve.
        Water damage 9,200. Separately, once the wall was opened up there is
        mould behind it that the remediation firm has quoted 22,000 to deal with
        - they say it is extensive through the cavity. Insured wants confirmation
        we will meet the remediation in full.""",
    },
    {
        "claim_id": "c24",
        "claim_number": "CLM-2026-04488",
        "claimant": "Cormac O Suilleabhain",
        "date_of_loss": "2026-03-16",
        "policy_line": "homeowners",
        "form_number": None,
        "notes": """Earthquake. Cracking to the chimney breast and to the render
        on the north elevation, chimney is now leaning and has been strapped.
        Structural engineer attending next week. Insured asking whether this is
        covered under his homeowners policy and what his excess would be.""",
    },
]


# ==================================================================
# ADJUSTER QUESTIONS -> the "answer this" half of the traffic
#
# `follow_up` chains a question onto the previous one in the same
# session, so the condensation step and the history handling are
# exercised by the traffic rather than only by the demo set.
# ==================================================================

QUESTIONS = [
    {"id": "q01", "text": "Burst supply line overnight, water through the ceiling. Does E-17 knock this out under HO-0304?"},
    {"id": "q02", "text": "What is the deductible on a water damage loss under HO-0304?", "follow_up": True},
    {"id": "q03", "text": "Insured had a weeping joint going for about a month before he called. Covered?"},
    {"id": "q04", "text": "How long does seepage have to run before E-17 applies?"},
    {"id": "q05", "text": "Hail dented the shingles but the roof still sheds water. What is our position under HO-0412?"},
    {"id": "q06", "text": "And what deductible applies to a hail loss?", "follow_up": True},
    {"id": "q07", "text": "Roof is 19 years old at date of loss. Replacement cost or actual cash value?"},
    {"id": "q08", "text": "Insured can't prove when the roof went on. What do we presume?"},
    {"id": "q09", "text": "Sump pump with no service records at all - which exclusion do I cite?"},
    {"id": "q10", "text": "Does E-44 still bite if the insured produces annual service invoices?"},
    {"id": "q11", "text": "Sump pump had no working battery backup at the time of loss. Does that void the cover?"},
    {"id": "q12", "text": "What is the aggregate limit on the water back-up endorsement?"},
    {"id": "q13", "text": "Short let guest injured, property let 10 days this year. Does E-53 apply?"},
    {"id": "q14", "text": "Same facts but 41 nights let. Does that change it?", "follow_up": True},
    {"id": "q15", "text": "Insured keeps no rental log. What does that do to the fourteen day allowance?"},
    {"id": "q16", "text": "Home business turning over 3,200 a year, online only. Is that excluded?"},
    {"id": "q17", "text": "Tenanted dwelling fire risk, pipe failed, mould found afterwards. Is there a mould sublimit?"},
    {"id": "q18", "text": "What is the deductible under DP-0208?"},
    {"id": "q19", "text": "Rental empty since the last tenancy ended 16 weeks ago. Water damage. Covered?"},
    {"id": "q20", "text": "Tenant deliberately flooded the place on the way out. What is our position?"},
    {"id": "q21", "text": "River flooded the ground floor. Is that a homeowners claim or does it go to flood?"},
    {"id": "q22", "text": "What does E-10 exclude?"},
    {"id": "q23", "text": "Pipe froze while the insured was away with the heating off. Which exclusion?"},
    {"id": "q24", "text": "Insured reported a water loss 82 days after he discovered it. Are we still on risk?"},
    {"id": "q25", "text": "Insured binned the failed connector before we could inspect it. Does that prejudice the claim?"},
    {"id": "q26", "text": "Do we pay to replace the appliance the water came out of?"},
    {"id": "q27", "text": "Emergency drying costs to stop further damage - are those subject to the deductible?"},
    {"id": "q28", "text": "What is the mould sublimit on the homeowners water damage endorsement?"},
    {"id": "q29", "text": "Screen enclosure destroyed by wind, quote is 11,500. What do we pay?"},
    {"id": "q30", "text": "Fence panels down in a windstorm, 2,100 to reinstate. Covered?"},
    {"id": "q31", "text": "Third hail claim in four years, no single event breached the roof. Position?"},
    {"id": "q32", "text": "Define sudden and accidental for me."},
    {"id": "q33", "text": "Is a drain line a supply line?"},
    {"id": "q34", "text": "Two endorsements both engage and they carry different deductibles. Which applies?"},
    {"id": "q35", "text": "Who carries the burden of proving an exclusion applies?"},
    {"id": "q36", "text": "Two endorsements conflict on the same loss. Which one controls?"},
    {"id": "q37", "text": "Sewer back-up, insured has had two prior back-up claims in five years. Does E-49 apply?"},
    {"id": "q38", "text": "Family has been in a hotel five weeks after a back-up. How long do we pay loss of use?"},
    {"id": "q39", "text": "Groundwater coming through the basement wall under pressure. Covered?"},
    {"id": "q40", "text": "Earthquake damage to the chimney. Is that covered and what is the excess?"},
    {"id": "q41", "text": "Does the policy cover a cyber extortion demand against the insured's home network?"},
    {"id": "q42", "text": "What is the registration number of the insured bike on the motor policy?"},
    {"id": "q43", "text": "Insured wants to know if theft during a short let is covered."},
    {"id": "q44", "text": "Solar panels damaged by hail. Are they covered?"},
    {"id": "q45", "text": "Loss of use where the house is still liveable after a hail storm - do we pay?"},
    {"id": "q46", "text": "Water got in through a window the insured left open in a storm. Covered?"},
]


# ==================================================================
# THE CURATED DEMO SET -> the bonus.
#
# These are the ones that get shown at the monthly review. They were
# picked, over time, because they demo well.
# ==================================================================

DEMO_QUESTIONS = [
    {"id": "d01", "text": "Does exclusion E-17 apply under form HO-0304 ed. 03-24 when a supply line bursts?"},
    {"id": "d02", "text": "Insured is claiming hail dents that did not puncture the shingles. Does E-34 on HO-0412 knock it out?"},
    {"id": "d03", "text": "Sump pump had no service records at all. Which exclusion code on HO-0521 do I cite?"},
    {"id": "d04", "text": "Guest hurt during a short-let stay. Does E-53 bite if they only rented the place 10 days that year?"},
    {"id": "d05", "text": "What does E-72 exclude on DP-0208 ed. 05-24?"},
    {"id": "d06", "text": "Under HO-0710 ed. 11-23, what counts as a supply line?"},
    {"id": "d07", "text": "What is the mould sublimit under HO-0304 ed. 03-24?"},
    {"id": "d08", "text": "What deductible applies to a windstorm and hail loss under HO-0412?"},
    {"id": "d09", "text": "Under HO-0521, what secondary power source does the sump pump need for cover to apply?"},
    {"id": "d10", "text": "What is the aggregate limit under HO-0521 ed. 01-24?"},
    {"id": "d11", "text": "Under HO-0633, what is the incidental business exception in Clause 4.3?"},
    {"id": "d12", "text": "Which endorsement controls where two endorsements address the same loss?"},
]
