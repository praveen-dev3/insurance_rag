"""Week 12 capstone corpus: versioned wordings, in-force table, limits table.

The capstone's point is that a loss must be decided against the wording in
force *on the loss date*, and that the flood wording was rewritten in 2025.
So the same form exists twice here - HO-0850 (household flood and escape of
water) in editions 07-23 and 04-25, MO-0420 (motor water and flood) in
09-23 and 05-25 - with the *same exclusion codes* meaning different things
in each edition, which is what makes "retrieve whichever ranks best" wrong
rather than merely untidy. HO-0100 and MO-0100 are base wordings with a
single edition each, so most perils are edition-independent and the date
filter has something to leave alone.

The numbers in the wording text are generated from LIMITS, never typed
twice: a deductible that reads $1,000 in the PDF and $750 in the table
would be a defect in the corpus rather than in the system under test.

Synthetic, as the whole repo's corpus is. Not the brief's 500 claim files.
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from endorsement_content import h, p, t  # noqa: E402

# ------------------------------------------------------------------
# Effective dates. [from, to) - `to` is the day the NEXT edition takes
# effect, so a loss on `to` belongs to the next edition and the day before
# it belongs to this one. That boundary is the bonus challenge's case.
# ------------------------------------------------------------------

EDITIONS = {
    "HO-0100": [{"edition": "01-22", "from": date(2022, 1, 1), "to": None}],
    "HO-0850": [
        {"edition": "07-23", "from": date(2023, 7, 1), "to": date(2025, 4, 1)},
        {"edition": "04-25", "from": date(2025, 4, 1), "to": None},
    ],
    "MO-0100": [{"edition": "03-22", "from": date(2022, 3, 1), "to": None}],
    "MO-0420": [
        {"edition": "09-23", "from": date(2023, 9, 1), "to": date(2025, 5, 1)},
        {"edition": "05-25", "from": date(2025, 5, 1), "to": None},
    ],
}

PRODUCT_FORMS = {
    "household": ["HO-0100", "HO-0850"],
    "motor": ["MO-0100", "MO-0420"],
}

POLICY_LINE = {"household": "homeowners", "motor": "motor"}

# ------------------------------------------------------------------
# Limits: (form, edition, peril_class) -> deductible and sub-limit.
# Three different numbers, kept apart: the policy limit lives on the
# policy (a sum insured), the deductible and sub-limit live here.
# ------------------------------------------------------------------

LIMITS = {
    ("HO-0850", "07-23", "flood"): {"deductible": 1000, "sub_limit": 15000},
    ("HO-0850", "07-23", "surface_water"): {"deductible": 1000, "sub_limit": 15000},
    ("HO-0850", "07-23", "escape_of_water"): {"deductible": 500, "sub_limit": None},
    ("HO-0850", "04-25", "flood"): {"deductible": 2500, "sub_limit": None},
    ("HO-0850", "04-25", "surface_water"): {"deductible": 2500, "sub_limit": 5000},
    ("HO-0850", "04-25", "escape_of_water"): {"deductible": 750, "sub_limit": None},
    ("HO-0100", "01-22", "theft"): {"deductible": 500, "sub_limit": 5000},
    ("HO-0100", "01-22", "fire"): {"deductible": 500, "sub_limit": None},
    ("HO-0100", "01-22", "other"): {"deductible": 500, "sub_limit": None},
    ("MO-0420", "09-23", "flood"): {"deductible": 750, "sub_limit": 8000},
    ("MO-0420", "05-25", "flood"): {"deductible": 1000, "sub_limit": 6000},
    ("MO-0100", "03-22", "collision"): {"deductible": 500, "sub_limit": None},
    ("MO-0100", "03-22", "other"): {"deductible": 500, "sub_limit": None},
}

# Which form carries the limits for a peril class, per product.
LIMIT_FORM = {
    ("household", "flood"): "HO-0850",
    ("household", "surface_water"): "HO-0850",
    ("household", "escape_of_water"): "HO-0850",
    ("household", "theft"): "HO-0100",
    ("household", "fire"): "HO-0100",
    ("household", "other"): "HO-0100",
    ("motor", "flood"): "MO-0420",
    ("motor", "collision"): "MO-0100",
    ("motor", "other"): "MO-0100",
}

PERIL_CLASSES = {
    "household": ["flood", "surface_water", "escape_of_water", "theft", "fire", "other"],
    "motor": ["flood", "collision", "other"],
}


def money(amount):
    return f"${amount:,}"


def _lim(form, edition, peril, key):
    return money(LIMITS[(form, edition, peril)][key])


# ------------------------------------------------------------------
# The wordings.
# ------------------------------------------------------------------

HO_0100 = {
    "file": "HO-0100_household_base_wording_ed_01-22.pdf",
    "form_number": "HO-0100",
    "edition_date": "01-22",
    "policy_line": "homeowners",
    "title": "Household Policy - Base Wording",
    "effective": "January 1, 2022",
    "supersedes": "None - new form",
    "blocks": [
        h("1. PURPOSE AND SCOPE"),
        p("""This base wording sets out the general conditions and the general
        exclusions that apply to every household policy. Perils that need their
        own terms - flood, surface water and escape of water - are dealt with in
        Form HO-0850, and the edition of that form in force on the date of loss
        governs the loss."""),

        h("2. THEFT AND FIRE"),
        p(f"""2.1 Theft of contents following forced entry to the described
        dwelling is subject to a deductible of {_lim('HO-0100', '01-22', 'theft', 'deductible')} and a theft sub-limit of
        {_lim('HO-0100', '01-22', 'theft', 'sub_limit')} for any single item or set of items."""),
        p(f"""2.2 Fire loss to the described dwelling and its contents is subject
        to a deductible of {_lim('HO-0100', '01-22', 'fire', 'deductible')}. There is no fire sub-limit."""),

        h("3. GENERAL EXCLUSIONS"),
        p("""3.1 We do not cover loss described in the exclusion table below. Codes
        in the E-0 series are general exclusions and apply to every peril."""),
        t(
            "EXCLUSION TABLE 3.1 - HOUSEHOLD GENERAL EXCLUSIONS",
            [
                ("E-01", "Wear and tear, gradual deterioration, rust, rot and corrosion",
                 "Excluded absolutely"),
                ("E-02", "Loss deliberately caused by the insured or a member of the household",
                 "Excluded absolutely"),
                ("E-03", "Theft or attempted theft by a person lawfully living in the described dwelling, including a lodger or tenant",
                 "Excluded absolutely"),
                ("E-04", "Mould, fungus or wet rot not resulting from an insured peril",
                 "Excluded absolutely"),
                ("E-05", "Loss while the described dwelling has been unoccupied for more than sixty (60) consecutive days",
                 "Excluded absolutely"),
                ("E-06", "Loss caused by war, invasion, civil commotion or terrorism",
                 "Excluded absolutely"),
            ],
            note="""Codes in the E-0 series are not edition dependent. Where a
            code in Form HO-0850 or another endorsement addresses the same loss,
            the endorsement edition in force on the date of loss controls to
            the extent of the inconsistency.""",
        ),

        h("4. POLICY LIMIT"),
        p("""4.1 The most we will pay for all loss to the described dwelling in
        any one policy year is the buildings sum insured shown in the
        declarations (the policy limit). A deductible or a sub-limit does not
        reduce the policy limit and is not a substitute for it."""),
    ],
}

HO_0850_2023 = {
    "file": "HO-0850_flood_escape_of_water_ed_07-23.pdf",
    "form_number": "HO-0850",
    "edition_date": "07-23",
    "policy_line": "homeowners",
    "title": "Flood, Surface Water and Escape of Water",
    "effective": "July 1, 2023",
    "supersedes": "HO-0850 ed. 03-20",
    "blocks": [
        h("1. PURPOSE AND SCOPE"),
        p("""This endorsement applies to loss caused by flood, by surface water and
        by escape of water from fixed plumbing, and applies to a loss occurring
        on or after July 1, 2023 and before April 1, 2025."""),

        h("2. COVERAGE BASIS"),
        p(f"""2.1 Flood means rising water from a river, stream, lake or the sea
        overflowing its normal banks. Direct physical loss to the described
        dwelling caused by flood is within this endorsement, subject to the flood
        sub-limit of {_lim('HO-0850', '07-23', 'flood', 'sub_limit')} and a flood deductible of
        {_lim('HO-0850', '07-23', 'flood', 'deductible')}."""),
        p(f"""2.2 Surface water means water from intense rainfall that flows or
        pools on the ground before entering the dwelling. Loss caused by surface
        water is subject to the same sub-limit of {_lim('HO-0850', '07-23', 'surface_water', 'sub_limit')} and deductible of
        {_lim('HO-0850', '07-23', 'surface_water', 'deductible')} as flood."""),
        p(f"""2.3 Escape of water means the sudden and accidental discharge of water
        from fixed plumbing, heating or appliance supply lines. It is subject to
        a deductible of {_lim('HO-0850', '07-23', 'escape_of_water', 'deductible')} and has no sub-limit."""),

        h("3. EXCLUSIONS APPLICABLE TO WATER LOSS"),
        p("""3.1 We do not cover loss described in the exclusion table below. Codes
        in the E-50 series are specific to this endorsement."""),
        t(
            "EXCLUSION TABLE 3.1 - WATER LOSS EXCLUSIONS (EDITION 07-23)",
            [
                ("E-50", "Water escaping gradually over fourteen (14) days or more, including seepage and constant leakage",
                 "Excluded absolutely"),
                ("E-51", "Water entering through an opening the insured left unsealed, including an open window or door",
                 "Excluded absolutely"),
                ("E-52", "Flood loss to outbuildings, fences, gardens, driveways and landscaping",
                 "Excluded absolutely"),
                ("E-53", "Loss caused by subsidence or landslip following flood",
                 "Excluded absolutely"),
                ("E-54", "Loss to the dwelling by flood where the dwelling is not the insured's main residence",
                 "Excluded above $10,000"),
            ],
            note="""In this edition flood loss to the dwelling itself is within
            Clause 2.1. E-52 removes only outbuildings and landscaping.""",
        ),
    ],
}

HO_0850_2025 = {
    "file": "HO-0850_flood_escape_of_water_ed_04-25.pdf",
    "form_number": "HO-0850",
    "edition_date": "04-25",
    "policy_line": "homeowners",
    "title": "Flood, Surface Water and Escape of Water",
    "effective": "April 1, 2025",
    "supersedes": "HO-0850 ed. 07-23",
    "blocks": [
        h("1. PURPOSE AND SCOPE"),
        p("""This endorsement applies to loss caused by flood, by surface water and
        by escape of water from fixed plumbing, and applies to a loss occurring
        on or after April 1, 2025. It replaces edition 07-23 for such losses."""),

        h("2. COVERAGE BASIS"),
        p("""2.1 Flood means rising water from a river, stream, lake or the sea
        overflowing its normal banks. This endorsement does not provide cover for
        loss caused by flood; see Exclusion E-52."""),
        p(f"""2.2 Surface water means water from intense rainfall that flows or
        pools on the ground before entering the dwelling. Direct physical loss to
        the described dwelling caused by surface water is subject to a surface
        water sub-limit of {_lim('HO-0850', '04-25', 'surface_water', 'sub_limit')} and a deductible of
        {_lim('HO-0850', '04-25', 'surface_water', 'deductible')}."""),
        p(f"""2.3 Escape of water means the sudden and accidental discharge of water
        from fixed plumbing, heating or appliance supply lines. It is subject to
        a deductible of {_lim('HO-0850', '04-25', 'escape_of_water', 'deductible')} and has no sub-limit."""),

        h("3. EXCLUSIONS APPLICABLE TO WATER LOSS"),
        p("""3.1 We do not cover loss described in the exclusion table below. Codes
        in the E-50 series are specific to this endorsement."""),
        t(
            "EXCLUSION TABLE 3.1 - WATER LOSS EXCLUSIONS (EDITION 04-25)",
            [
                ("E-50", "Water escaping gradually over fourteen (14) days or more, including seepage and constant leakage",
                 "Excluded absolutely"),
                ("E-51", "Water entering through an opening the insured left unsealed, including an open window or door",
                 "Excluded absolutely"),
                ("E-52", "Flood: rising water from a river, stream, lake or the sea overflowing its normal banks, to any property including the dwelling",
                 "Excluded absolutely"),
                ("E-53", "Loss caused by subsidence or landslip following flood or surface water",
                 "Excluded absolutely"),
                ("E-55", "Surface water loss to a basement or any room below ground level",
                 "Excluded absolutely"),
            ],
            note="""Edition 04-25 rewrote E-52. It now excludes flood loss to the
            dwelling itself, which edition 07-23 did not. Surface water from
            intense rainfall is not flood for the purposes of E-52.""",
        ),
    ],
}

MO_0100 = {
    "file": "MO-0100_motor_base_wording_ed_03-22.pdf",
    "form_number": "MO-0100",
    "edition_date": "03-22",
    "policy_line": "motor",
    "title": "Private Motor Policy - Base Wording",
    "effective": "March 1, 2022",
    "supersedes": "None - new form",
    "blocks": [
        h("1. PURPOSE AND SCOPE"),
        p("""This base wording sets out the general conditions and the general
        exclusions that apply to every private motor policy. Water, flood and
        weather damage to the vehicle is dealt with in Form MO-0420, and the
        edition of that form in force on the date of loss governs the loss."""),

        h("2. OWN DAMAGE"),
        p(f"""2.1 Accidental collision damage to the insured vehicle is subject to a
        deductible of {_lim('MO-0100', '03-22', 'collision', 'deductible')}. There is no collision sub-limit."""),

        h("3. GENERAL EXCLUSIONS"),
        p("""3.1 We do not cover loss described in the exclusion table below. Codes
        in the E-6 series are general motor exclusions and apply to every peril."""),
        t(
            "EXCLUSION TABLE 3.1 - MOTOR GENERAL EXCLUSIONS",
            [
                ("E-60", "Wear and tear, mechanical or electrical breakdown and failure of any part",
                 "Excluded absolutely"),
                ("E-61", "Loss while the vehicle is used for racing, pace-making, rallying or on a track day",
                 "Excluded absolutely"),
                ("E-62", "Loss while the vehicle is driven by a person who does not hold a licence valid for that class of vehicle",
                 "Excluded absolutely"),
                ("E-63", "Loss deliberately caused by the insured or by a person driving with the insured's consent",
                 "Excluded absolutely"),
                ("E-64", "Loss while the driver is over the legal alcohol or drug limit",
                 "Excluded absolutely"),
            ],
            note="""Codes in the E-6 series other than E-65 are not edition
            dependent.""",
        ),

        h("4. POLICY LIMIT"),
        p("""4.1 The most we will pay for loss to the insured vehicle is its market
        value immediately before the loss, up to the sum insured shown in the
        declarations (the policy limit). A deductible or a sub-limit does not
        change the policy limit."""),
    ],
}

MO_0420_2023 = {
    "file": "MO-0420_motor_water_flood_ed_09-23.pdf",
    "form_number": "MO-0420",
    "edition_date": "09-23",
    "policy_line": "motor",
    "title": "Motor Water, Flood and Weather Damage",
    "effective": "September 1, 2023",
    "supersedes": "MO-0420 ed. 02-19",
    "blocks": [
        h("1. PURPOSE AND SCOPE"),
        p("""This endorsement applies to loss to the insured vehicle caused by
        flood, standing water and weather, for a loss occurring on or after
        September 1, 2023 and before May 1, 2025."""),

        h("2. COVERAGE BASIS"),
        p(f"""2.1 Water damage to the interior, electrics and bodywork of the
        insured vehicle caused by flood or standing water is within this
        endorsement, subject to a flood sub-limit of {_lim('MO-0420', '09-23', 'flood', 'sub_limit')} and a flood
        deductible of {_lim('MO-0420', '09-23', 'flood', 'deductible')}."""),

        h("3. EXCLUSIONS APPLICABLE TO WATER LOSS"),
        p("""3.1 We do not cover loss described in the exclusion table below. The
        code E-65 is specific to this endorsement."""),
        t(
            "EXCLUSION TABLE 3.1 - MOTOR WATER LOSS EXCLUSIONS (EDITION 09-23)",
            [
                ("E-65", "Engine damage caused by the engine drawing in water after the vehicle was driven into standing water",
                 "Excluded above $5,000"),
                ("E-66", "Loss to a vehicle left in a location the insured had been warned was subject to flooding",
                 "Excluded absolutely"),
            ],
            note="""In this edition engine damage from driving into standing
            water is excluded only to the extent it exceeds $5,000.""",
        ),
    ],
}

MO_0420_2025 = {
    "file": "MO-0420_motor_water_flood_ed_05-25.pdf",
    "form_number": "MO-0420",
    "edition_date": "05-25",
    "policy_line": "motor",
    "title": "Motor Water, Flood and Weather Damage",
    "effective": "May 1, 2025",
    "supersedes": "MO-0420 ed. 09-23",
    "blocks": [
        h("1. PURPOSE AND SCOPE"),
        p("""This endorsement applies to loss to the insured vehicle caused by
        flood, standing water and weather, for a loss occurring on or after
        May 1, 2025. It replaces edition 09-23 for such losses."""),

        h("2. COVERAGE BASIS"),
        p(f"""2.1 Water damage to the interior, electrics and bodywork of the
        insured vehicle caused by flood or standing water is within this
        endorsement, subject to a flood sub-limit of {_lim('MO-0420', '05-25', 'flood', 'sub_limit')} and a flood
        deductible of {_lim('MO-0420', '05-25', 'flood', 'deductible')}."""),

        h("3. EXCLUSIONS APPLICABLE TO WATER LOSS"),
        p("""3.1 We do not cover loss described in the exclusion table below. The
        code E-65 is specific to this endorsement."""),
        t(
            "EXCLUSION TABLE 3.1 - MOTOR WATER LOSS EXCLUSIONS (EDITION 05-25)",
            [
                ("E-65", "Engine damage caused by the engine drawing in water (hydrolock) after the vehicle was driven into standing water",
                 "Excluded absolutely"),
                ("E-66", "Loss to a vehicle left in a location the insured had been warned was subject to flooding",
                 "Excluded absolutely"),
                ("E-67", "Water damage to a vehicle parked below ground level during a declared flood warning",
                 "Excluded absolutely"),
            ],
            note="""Edition 05-25 rewrote E-65: engine damage from driving into
            standing water is now excluded absolutely, not only above $5,000.""",
        ),
    ],
}

DOCUMENTS = [HO_0100, HO_0850_2023, HO_0850_2025, MO_0100, MO_0420_2023, MO_0420_2025]


# ------------------------------------------------------------------
# Policies: policy number -> product, tier-free sum insured, in-force
# ranges. A policy with two ranges has a gap, which is a lapse.
# ------------------------------------------------------------------

POLICIES = {
    "POL-H-1001": {"product": "household", "policy_limit": 350000,
                   "ranges": [(date(2022, 6, 1), date(2026, 6, 1))]},
    "POL-H-1002": {"product": "household", "policy_limit": 500000,
                   "ranges": [(date(2023, 1, 1), date(2026, 1, 1))]},
    "POL-H-1003": {"product": "household", "policy_limit": 280000,
                   "ranges": [(date(2023, 9, 1), date(2025, 9, 1)),
                              (date(2025, 11, 1), date(2026, 11, 1))]},
    "POL-H-1004": {"product": "household", "policy_limit": 420000,
                   "ranges": [(date(2024, 2, 1), date(2026, 2, 1))]},
    "POL-H-1005": {"product": "household", "policy_limit": 310000,
                   "ranges": [(date(2021, 4, 1), date(2025, 4, 1))]},
    "POL-M-2001": {"product": "motor", "policy_limit": 28000,
                   "ranges": [(date(2023, 3, 1), date(2026, 3, 1))]},
    "POL-M-2002": {"product": "motor", "policy_limit": 45000,
                   "ranges": [(date(2024, 5, 1), date(2026, 5, 1))]},
    "POL-M-2003": {"product": "motor", "policy_limit": 19000,
                   "ranges": [(date(2022, 8, 1), date(2025, 8, 1))]},
    "POL-M-2004": {"product": "motor", "policy_limit": 60000,
                   "ranges": [(date(2025, 1, 1), date(2026, 1, 1))]},
}
