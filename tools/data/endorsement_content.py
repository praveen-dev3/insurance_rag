"""Source text for the six-endorsement drop.

Kept as data rather than as six binary PDFs checked into the repo, so the
pack is reproducible and reviewable in the diff. tools/make_endorsements.py
renders it; nothing at runtime imports this module.

Exclusion codes are consistent across forms - E-17 means the same thing
wherever it is referenced - because the whole point of the exercise is
whether a chunker keeps a code attached to the form that scopes it.
"""


# ------------------------------------------------------------------
# Block helpers. A document body is a list of blocks; a block is a tuple
# of (kind, payload) where kind is "h" (clause heading), "p" (paragraph)
# or "t" (exclusion table).
# ------------------------------------------------------------------

def h(text):
    return ("h", text)


def p(text):
    return ("p", " ".join(text.split()))


def t(title, rows, note=None):
    return ("t", {
        "title": title,
        "rows": rows,
        "note": " ".join(note.split()) if note else None,
    })


# ==================================================================
# 1. HO-0304 - water damage. Carries E-17, the code the brief names.
# ==================================================================

HO_0304 = {
    "file": "HO-0304_water_damage_ed_03-24.pdf",
    "form_number": "HO-0304",
    "edition_date": "03-24",
    "policy_line": "homeowners",
    "title": "Water Damage, Discharge and Overflow Endorsement",
    "effective": "March 1, 2024",
    "supersedes": "HO-0304 ed. 08-21",
    "blocks": [
        h("1. PURPOSE AND SCOPE"),
        p("""This endorsement amends the water damage provisions of the
        homeowners policy wording to which it is attached. Where the language
        of this endorsement conflicts with the base wording, this endorsement
        controls. All other terms, conditions and exclusions of the policy
        remain in full force. This endorsement applies only to direct physical
        loss to covered property arising from the escape of water within the
        described premises, and does not extend to flood, surface water or
        tidal action, which remain excluded under the base wording."""),
        p("""Capitalised terms used but not defined in this endorsement have
        the meaning given to them in Form HO-0710, Definitions and General
        Conditions Amendment. The insured is directed to that form for the
        meaning of sudden and accidental, supply line, and seepage, each of
        which materially affects the operation of Clause 3 below."""),

        h("2. COVERAGE GRANT - SUDDEN AND ACCIDENTAL DISCHARGE"),
        p("""2.1 We cover direct physical loss to covered property caused by
        the sudden and accidental discharge, leakage or overflow of water or
        steam from a plumbing, heating, air conditioning, fire protective
        sprinkler system, or household appliance located within the described
        dwelling. A supply line that ruptures, splits or otherwise fails
        abruptly is a sudden and accidental discharge for the purposes of this
        clause, and loss resulting from it is covered subject to the
        exclusions in Clause 3 and the limits in Clause 5."""),
        p("""2.2 We also cover the reasonable cost of tearing out and replacing
        any part of the dwelling necessary to gain access to the system or
        appliance from which the water escaped. We do not cover the cost of
        repairing or replacing the system or appliance itself, except where
        that system or appliance is itself damaged by a separate covered
        peril."""),
        p("""2.3 Coverage under this clause is available only where the
        discharge is first detected and reported in accordance with Clause 4.
        A discharge that the insured knew of, or reasonably should have known
        of, and did not report is not a sudden and accidental discharge
        regardless of how the failure began."""),

        h("3. EXCLUSIONS APPLICABLE TO WATER DAMAGE"),
        p("""3.1 We do not cover loss described in the exclusion table below.
        Each exclusion is identified by a code which is used consistently
        across all endorsements attached to this policy line. Where an
        exclusion is shown as conditional, it applies only in the
        circumstances stated in the disposition column."""),
        t(
            "EXCLUSION TABLE 3.1 - WATER DAMAGE EXCLUSIONS",
            [
                ("E-10", "Flood, surface water, waves, tidal water or overflow of a body of water",
                 "Excluded absolutely"),
                ("E-11", "Water below the surface of the ground exerting pressure on foundations",
                 "Excluded absolutely"),
                ("E-12", "Water damage occurring while the dwelling is vacant for more than 60 consecutive days",
                 "Excluded unless heat maintained and water shut off"),
                ("E-13", "Discharge from a system the insured failed to drain before a period of vacancy",
                 "Excluded absolutely"),
                ("E-14", "Loss caused by freezing of a plumbing system during the heating season",
                 "Excluded unless heat maintained at 55F or above"),
                ("E-15", "Cost of repairing the appliance or system from which the water escaped",
                 "Excluded, tear-out still covered under Clause 2.2"),
                ("E-16", "Rust, corrosion, wet rot or dry rot forming before the discharge",
                 "Excluded absolutely"),
                ("E-17", "Constant or repeated seepage or leakage of water occurring over a period of fourteen (14) days or more, whether or not the insured was aware of it",
                 "Excluded absolutely; does NOT apply to a sudden and accidental discharge under Clause 2.1"),
                ("E-18", "Mould, fungus or wet rot except as provided by the sublimit in Clause 5.2",
                 "Excluded above sublimit"),
                ("E-19", "Water damage caused by or resulting from a sewer or drain back-up",
                 "Excluded here; see Form HO-0521"),
                ("E-20", "Loss to landscaping, paving or fencing caused by escaping water",
                 "Excluded absolutely"),
                ("E-21", "Water damage arising out of a home-sharing occupancy",
                 "Excluded; see Form HO-0633"),
            ],
            note="""Exclusion E-17 is directed at a slow, ongoing failure. It is
            not triggered by an abrupt rupture. A burst supply line that
            discharges water over a period shorter than fourteen days is
            adjudicated under Clause 2.1 and remains covered.""",
        ),

        h("4. CONDITIONS PRECEDENT TO PAYMENT"),
        p("""4.1 The insured must give notice of a water damage loss within
        thirty (30) days of the date the discharge is first discovered. Notice
        given after that period voids coverage for the loss unless the insured
        shows that notice could not reasonably have been given sooner."""),
        p("""4.2 The insured must take reasonable steps to protect the property
        from further damage, including shutting off the water supply to the
        affected system. Costs reasonably incurred in doing so are covered and
        are not subject to the deductible in Clause 5.3."""),
        p("""4.3 The insured must preserve the failed component and make it
        available for inspection. Disposal of the failed component before we
        have had a reasonable opportunity to inspect it may prejudice the
        claim to the extent our investigation is impaired."""),

        h("5. LIMITS, SUBLIMITS AND DEDUCTIBLE"),
        p("""5.1 The most we will pay for any one water damage loss under this
        endorsement is the Coverage A limit shown in the declarations, less the
        deductible in Clause 5.3."""),
        p("""5.2 Our total liability for mould, fungus or wet rot resulting
        from a covered water damage loss is limited to ten thousand dollars
        ($10,000) in any one policy year, regardless of the number of losses or
        claimants. This sublimit is part of, and not in addition to, the
        Coverage A limit."""),
        p("""5.3 A deductible of two thousand five hundred dollars ($2,500)
        applies separately to each water damage loss under this endorsement.
        This deductible replaces, and is not in addition to, the all-perils
        deductible shown in the declarations."""),
    ],
}


# ==================================================================
# 2. HO-0412 - windstorm and hail. Cosmetic damage is the live row.
# ==================================================================

HO_0412 = {
    "file": "HO-0412_windstorm_hail_ed_06-24.pdf",
    "form_number": "HO-0412",
    "edition_date": "06-24",
    "policy_line": "homeowners",
    "title": "Windstorm and Hail - Exterior Surfaces Limitation",
    "effective": "June 15, 2024",
    "supersedes": "HO-0412 ed. 02-22",
    "blocks": [
        h("1. PURPOSE AND SCOPE"),
        p("""This endorsement limits the coverage otherwise provided for
        windstorm and hail damage to exterior surfaces of the dwelling and
        other structures. It does not restrict coverage for resulting interior
        water damage where the exterior surface has been physically breached by
        wind or hail."""),

        h("2. COVERAGE BASIS FOR ROOF SURFACING"),
        p("""2.1 Loss to roof surfacing caused by windstorm or hail is settled
        on a replacement cost basis where the roof surfacing is fifteen (15)
        years old or less at the date of loss, measured from the date of
        original installation as shown in the inspection record."""),
        p("""2.2 Where the roof surfacing is more than fifteen (15) years old at
        the date of loss, loss is settled on an actual cash value basis. Actual
        cash value is replacement cost less depreciation calculated on the
        schedule maintained by us and available to the insured on request."""),
        p("""2.3 Where the insured cannot establish the installation date of the
        roof surfacing, the roof is presumed to be more than fifteen years old
        and Clause 2.2 applies. This presumption may be rebutted by documentary
        evidence of installation."""),

        h("3. EXCLUSIONS APPLICABLE TO WINDSTORM AND HAIL"),
        p("""3.1 We do not cover loss described in the exclusion table below.
        Codes in the E-30 series are specific to windstorm and hail and do not
        apply to perils addressed by other endorsements."""),
        t(
            "EXCLUSION TABLE 3.1 - WINDSTORM AND HAIL EXCLUSIONS",
            [
                ("E-30", "Loss to awnings, canopies or shade structures not permanently attached",
                 "Excluded absolutely"),
                ("E-31", "Loss to outdoor antennas, satellite dishes and their masts",
                 "Excluded absolutely"),
                ("E-32", "Wind-driven rain entering through an opening not caused by wind or hail",
                 "Excluded absolutely"),
                ("E-33", "Loss to screening, screen enclosures and pool cages",
                 "Excluded above $2,500"),
                ("E-34", "Cosmetic damage to roof surfacing that does not compromise the water-shedding function of the roof",
                 "Excluded absolutely"),
                ("E-35", "Loss to solar collectors or their mountings caused by hail",
                 "Excluded unless scheduled"),
                ("E-36", "Marring, scuffing or granule loss not accompanied by penetration",
                 "Excluded absolutely"),
                ("E-37", "Loss to fences, gates and retaining walls caused by windstorm",
                 "Excluded above $5,000"),
                ("E-38", "Repeated hail impact over multiple storm events where no single event caused breach",
                 "Excluded absolutely"),
                ("E-39", "Consequential loss of use where the dwelling remains habitable",
                 "Excluded absolutely"),
            ],
            note="""Cosmetic damage under E-34 means damage that alters the
            appearance of roof surfacing without reducing its ability to shed
            water. Where hail both dents and penetrates the surfacing, E-34 does
            not apply and the loss is settled under Clause 2.""",
        ),

        h("4. CONDITIONS"),
        p("""4.1 The insured must report windstorm or hail damage within one
        year of the date of the storm event. A claim reported after that period
        is not payable under this endorsement."""),
        p("""4.2 We may require a roof inspection by an inspector of our
        choosing before settling a claim under this endorsement. The insured
        must provide reasonable access for that inspection."""),

        h("5. DEDUCTIBLE"),
        p("""5.1 A windstorm and hail deductible of two percent (2%) of the
        Coverage A limit shown in the declarations applies to each windstorm or
        hail loss. This deductible replaces the all-perils deductible for losses
        under this endorsement and is subject to a minimum of one thousand
        dollars ($1,000)."""),
    ],
}


# ==================================================================
# 3. HO-0521 - sewer and sump back-up.
# ==================================================================

HO_0521 = {
    "file": "HO-0521_water_backup_sump_ed_01-24.pdf",
    "form_number": "HO-0521",
    "edition_date": "01-24",
    "policy_line": "homeowners",
    "title": "Water Back-Up and Sump Discharge or Overflow",
    "effective": "January 1, 2024",
    "supersedes": "None - new form",
    "blocks": [
        h("1. PURPOSE AND SCOPE"),
        p("""This endorsement provides limited coverage for loss caused by water
        which backs up through sewers or drains, or which overflows or is
        discharged from a sump, sump pump or related equipment. Loss of this
        kind is excluded under Form HO-0304 by exclusion E-19 and is covered
        only to the extent set out here."""),

        h("2. COVERAGE GRANT"),
        p("""2.1 We cover direct physical loss to covered property caused by
        water or waterborne material which backs up through sewers or drains
        serving the described dwelling, or which overflows or is discharged from
        a sump, sump pump or related equipment, even where the overflow results
        from mechanical breakdown of the pump."""),
        p("""2.2 Coverage under this endorsement applies only where the dwelling
        is equipped with a sump pump fitted with a functioning secondary power
        source capable of operating the pump for not less than eight (8) hours
        in the event of a mains power failure. Absence of a secondary power
        source at the time of loss voids coverage under this endorsement."""),

        h("3. EXCLUSIONS APPLICABLE TO BACK-UP AND OVERFLOW"),
        p("""3.1 We do not cover loss described in the exclusion table below.
        Codes in the E-40 series are specific to this endorsement."""),
        t(
            "EXCLUSION TABLE 3.1 - BACK-UP AND SUMP OVERFLOW EXCLUSIONS",
            [
                ("E-40", "Back-up caused by flood or surface water entering the sewer system",
                 "Excluded absolutely"),
                ("E-41", "Back-up occurring while the dwelling is under construction or renovation",
                 "Excluded absolutely"),
                ("E-42", "Loss to the sump, sump pump or related equipment itself",
                 "Excluded absolutely"),
                ("E-43", "Back-up caused by roots, debris or blockage the insured was on notice of",
                 "Excluded absolutely"),
                ("E-44", "Back-up or overflow caused by the failure of the insured to maintain, service or test the sump pump in accordance with the manufacturer schedule",
                 "Excluded absolutely"),
                ("E-45", "Back-up originating from a sewer or drain that does not serve the described dwelling",
                 "Excluded absolutely"),
                ("E-46", "Loss caused by a sump pump discharge line that was not disconnected before a freeze",
                 "Excluded absolutely"),
                ("E-47", "Mould, fungus or wet rot resulting from a back-up",
                 "Excluded above $5,000"),
                ("E-48", "Loss of use exceeding thirty days following a back-up",
                 "Excluded absolutely"),
                ("E-49", "Back-up in a dwelling with a history of two or more prior back-up claims in five years",
                 "Excluded unless remediation certified"),
            ],
            note="""E-44 turns on maintenance records. Where the insured
            produces a service record consistent with the manufacturer schedule,
            E-44 does not apply and the loss is adjudicated under Clause 2.1
            even where the pump ultimately failed.""",
        ),

        h("4. CONDITIONS"),
        p("""4.1 The insured must retain the sump pump and its power source
        following a loss and make them available for inspection and
        testing."""),
        p("""4.2 The insured must provide service records for the sump pump
        covering the twenty-four (24) months preceding the loss where such
        records are requested by us."""),

        h("5. LIMIT AND DEDUCTIBLE"),
        p("""5.1 The most we will pay under this endorsement is twenty-five
        thousand dollars ($25,000) in the aggregate for all losses occurring in
        any one policy year, regardless of the number of back-up events. This
        limit is part of, and not in addition to, the Coverage A limit."""),
        p("""5.2 A deductible of one thousand dollars ($1,000) applies to each
        loss under this endorsement."""),
    ],
}


# ==================================================================
# 4. HO-0633 - home-sharing and home business.
# ==================================================================

HO_0633 = {
    "file": "HO-0633_home_sharing_business_ed_09-23.pdf",
    "form_number": "HO-0633",
    "edition_date": "09-23",
    "policy_line": "homeowners",
    "title": "Home-Sharing and Home Business Activity Exclusion",
    "effective": "September 1, 2023",
    "supersedes": "HO-0633 ed. 04-20",
    "blocks": [
        h("1. PURPOSE AND SCOPE"),
        p("""This endorsement excludes coverage for loss, liability and expense
        arising out of home-sharing activity and out of business activity
        conducted from the described dwelling. It applies to Coverage A,
        Coverage B, Coverage C and to the liability coverages alike."""),

        h("2. DEFINITIONS SPECIFIC TO THIS ENDORSEMENT"),
        p("""2.1 Home-sharing activity means the rental or holding for rental of
        the described dwelling, or any part of it, to a person who is not an
        insured, where the arrangement is made through a home-sharing network
        platform or any similar service, and where the occupancy is for a period
        of less than thirty (30) consecutive days."""),
        p("""2.2 Home-sharing occupant means a person occupying the described
        dwelling under a home-sharing activity, and includes that person's
        guests and invitees."""),
        p("""2.3 Business activity means a trade, profession or occupation
        engaged in for profit, conducted in whole or in part from the described
        dwelling, other than an activity falling within the incidental exception
        in Clause 4.3."""),

        h("3. EXCLUSIONS APPLICABLE TO HOME-SHARING AND BUSINESS"),
        p("""3.1 We do not cover loss, liability or expense described in the
        exclusion table below. Codes in the E-50 series are specific to this
        endorsement."""),
        t(
            "EXCLUSION TABLE 3.1 - HOME-SHARING AND BUSINESS EXCLUSIONS",
            [
                ("E-50", "Property damage to the dwelling caused by a home-sharing occupant",
                 "Excluded absolutely"),
                ("E-51", "Theft of personal property occurring during a home-sharing occupancy",
                 "Excluded absolutely"),
                ("E-52", "Loss of rental income arising out of home-sharing activity",
                 "Excluded absolutely"),
                ("E-53", "Bodily injury to a home-sharing occupant however caused",
                 "Excluded absolutely, subject to the exception in Clause 4.2"),
                ("E-54", "Liability arising out of the rendering of any service for a fee at the dwelling",
                 "Excluded absolutely"),
                ("E-55", "Property damage to business property held on the premises for sale or distribution",
                 "Excluded above $2,500"),
                ("E-56", "Bodily injury to an employee of a business conducted from the dwelling",
                 "Excluded absolutely"),
                ("E-57", "Liability arising out of the preparation or sale of food to the public",
                 "Excluded absolutely"),
                ("E-58", "Loss arising out of the storage of goods for a business at the dwelling",
                 "Excluded absolutely"),
                ("E-59", "Liability arising out of the operation of a day nursery or child care service",
                 "Excluded absolutely"),
            ],
            note="""The E-50 series operates on occupancy and purpose, not on
            the peril. Where the same physical loss would have been covered
            absent the home-sharing occupancy, the exclusion still applies.""",
        ),

        h("4. EXCEPTIONS TO THE EXCLUSIONS"),
        p("""4.1 The exclusions in Clause 3 do not apply to a rental of the
        described dwelling to a person who is not an insured where the total
        number of days on which any part of the dwelling is rented does not
        exceed fourteen (14) days in any one policy year."""),
        p("""4.2 Exclusion E-53 does not apply where the total rental period in
        the policy year is within the fourteen (14) day allowance in Clause 4.1.
        In that case bodily injury to an occupant is adjudicated under the
        liability coverages of the base wording."""),
        p("""4.3 Business activity conducted from the described dwelling is
        incidental, and is not excluded, where the annual gross receipts of the
        activity do not exceed five thousand dollars ($5,000) and the activity
        involves no visit by a customer or client to the dwelling."""),

        h("5. CONDITIONS"),
        p("""5.1 The insured must maintain a record of all days on which any
        part of the dwelling was rented, and must produce that record on request
        following a loss. Failure to produce the record raises a presumption
        that the fourteen day allowance in Clause 4.1 has been exceeded."""),
    ],
}


# ==================================================================
# 5. HO-0710 - definitions. The completeness half of the bonus case.
# ==================================================================

HO_0710 = {
    "file": "HO-0710_definitions_general_conditions_ed_11-23.pdf",
    "form_number": "HO-0710",
    "edition_date": "11-23",
    "policy_line": "homeowners",
    "title": "Definitions and General Conditions Amendment",
    "effective": "November 1, 2023",
    "supersedes": "HO-0710 ed. 07-19",
    "blocks": [
        h("1. PURPOSE AND SCOPE"),
        p("""This endorsement replaces the definitions section of the base
        homeowners wording and supplies the meanings used by every other
        endorsement attached to this policy line. Where another endorsement uses
        a term defined here, the meaning given here controls, and any
        inconsistent definition in the base wording is deleted."""),

        h("2. DEFINITIONS"),
        p("""2.1 Sudden and accidental means an event which is both abrupt in
        onset and unintended by the insured, and which occurs at an identifiable
        point in time. An event is not sudden and accidental merely because its
        consequences were unexpected. A process which develops gradually over a
        period of fourteen (14) days or more is not sudden and accidental
        however unintended its result, and is adjudicated as seepage."""),
        p("""2.2 Supply line means any pipe, hose, tube, fitting or connector
        which conveys water under mains pressure to a fixture, appliance or
        system within the described dwelling, up to and including the shut-off
        valve serving that fixture, appliance or system. A supply line does not
        include a waste, soil or drainage pipe, which is a drain line."""),
        p("""2.3 Seepage means the escape of water in small quantities over a
        continuous or repeated period, whether or not the escape is visible and
        whether or not the insured was aware of it. Seepage is distinguished
        from a sudden and accidental discharge by its duration and not by the
        volume of water escaping."""),
        p("""2.4 Cosmetic damage means physical damage to a surface which alters
        its appearance without reducing the ability of that surface to perform
        its intended function. In the case of roof surfacing, the intended
        function is the shedding of water."""),
        p("""2.5 Described dwelling means the building shown as the insured
        location in the declarations, including attached structures and
        permanently installed fixtures, but excluding other structures set apart
        from the dwelling by clear space."""),
        p("""2.6 Policy year means the twelve month period commencing on the
        inception date shown in the declarations, or on any anniversary of that
        date."""),

        h("3. GENERAL CONDITIONS"),
        p("""3.1 Where two or more endorsements attached to this policy address
        the same loss, the endorsement bearing the later edition date controls
        to the extent of the inconsistency."""),
        p("""3.2 Where an exclusion in one endorsement refers a loss to another
        form, coverage for that loss is determined solely under the form
        referred to, and the referring endorsement neither grants nor restricts
        coverage for it."""),
        p("""3.3 A deductible stated in an endorsement replaces the all-perils
        deductible for losses under that endorsement. Where a loss engages two
        endorsements carrying different deductibles, the higher deductible
        applies, and only once."""),
        p("""3.4 The burden of showing that a loss falls within a coverage grant
        rests on the insured. The burden of showing that an exclusion applies
        rests on us."""),
    ],
}


# ==================================================================
# 6. DP-0208 - a different policy_line, so the metadata filter has
#    something to actually change. Water language deliberately close
#    to HO-0304 so it competes for the same queries.
# ==================================================================

DP_0208 = {
    "file": "DP-0208_dwelling_fire_water_ed_05-24.pdf",
    "form_number": "DP-0208",
    "edition_date": "05-24",
    "policy_line": "dwelling_fire",
    "title": "Dwelling Fire - Water Damage Limitation (Tenant-Occupied)",
    "effective": "May 1, 2024",
    "supersedes": "DP-0208 ed. 10-21",
    "blocks": [
        h("1. PURPOSE AND SCOPE"),
        p("""This endorsement amends the water damage provisions of the dwelling
        fire policy wording issued in respect of tenant-occupied dwellings. It
        does not apply to any homeowners policy line, and the exclusion codes in
        the E-70 series used here are specific to the dwelling fire line. Where
        a dwelling is owner-occupied, Form HO-0304 applies instead."""),

        h("2. COVERAGE GRANT - SUDDEN AND ACCIDENTAL DISCHARGE"),
        p("""2.1 We cover direct physical loss to covered property caused by the
        sudden and accidental discharge, leakage or overflow of water or steam
        from a plumbing, heating or air conditioning system located within the
        described dwelling, subject to the exclusions in Clause 3. A supply line
        which ruptures abruptly is a sudden and accidental discharge for the
        purposes of this clause."""),
        p("""2.2 Coverage under this endorsement is conditional on the dwelling
        being occupied by a tenant under a written tenancy agreement at the date
        of loss. A dwelling between tenancies is treated as vacant from the
        sixty-first day after the previous tenancy ended."""),

        h("3. EXCLUSIONS APPLICABLE TO WATER DAMAGE"),
        p("""3.1 We do not cover loss described in the exclusion table below.
        Codes in the E-70 series apply only to the dwelling fire policy line."""),
        t(
            "EXCLUSION TABLE 3.1 - WATER DAMAGE EXCLUSIONS, DWELLING FIRE LINE",
            [
                ("E-70", "Flood, surface water or overflow of a body of water",
                 "Excluded absolutely"),
                ("E-71", "Constant or repeated seepage or leakage of water over fourteen (14) days or more",
                 "Excluded absolutely"),
                ("E-72", "Water damage from a plumbing system in a dwelling vacant more than 60 consecutive days",
                 "Excluded absolutely"),
                ("E-73", "Water damage caused deliberately or recklessly by a tenant or their guest",
                 "Excluded absolutely"),
                ("E-74", "Loss caused by freezing where the dwelling was not heated during the tenancy",
                 "Excluded absolutely"),
                ("E-75", "Cost of repairing the system or appliance from which the water escaped",
                 "Excluded absolutely"),
                ("E-76", "Mould, fungus or wet rot however caused",
                 "Excluded absolutely, no sublimit applies"),
                ("E-77", "Water damage occurring during a period in which rent was more than 60 days in arrears",
                 "Excluded absolutely"),
                ("E-78", "Sewer or drain back-up of any kind",
                 "Excluded absolutely, no buy-back available"),
                ("E-79", "Loss of rental income beyond twelve months following a water damage loss",
                 "Excluded absolutely"),
            ],
            note="""The dwelling fire line carries no mould sublimit. E-76
            excludes mould outright, which is the principal difference between
            this form and Form HO-0304 on the homeowners line.""",
        ),

        h("4. CONDITIONS"),
        p("""4.1 The insured must inspect the dwelling not less than once in
        every ninety (90) day period during which it is unoccupied, and must
        keep a record of those inspections."""),
        p("""4.2 The insured must give notice of a water damage loss within
        thirty (30) days of discovery."""),

        h("5. LIMIT AND DEDUCTIBLE"),
        p("""5.1 A deductible of five thousand dollars ($5,000) applies to each
        water damage loss under this endorsement, reflecting the elevated
        exposure of tenant-occupied property."""),
    ],
}


ENDORSEMENTS = [HO_0304, HO_0412, HO_0521, HO_0633, HO_0710, DP_0208]
