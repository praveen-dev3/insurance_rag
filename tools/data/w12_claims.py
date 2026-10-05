"""The 31 FNOLs the integrated eval runs, with the answer key.

Each claim is built from a family template and a deterministic identity
(name, address, injury) so the PII it carries is *known*: the PII audit in
the eval searches every log line and every MCP response for these exact
strings, which is the only way to say what the system handed out rather
than hope.

`boundary` is the field the bonus challenge turns on:
  pre_2025   resolved to an OLDER edition than the latest one - the case a
             "latest wording wins" retriever gets wrong
  post_2025  resolved to the LATEST edition
  base       a single-edition base wording, no version to choose
  lapsed     the policy was not in force on the loss date
  no_edition the policy was in force but no edition of the governing form
             had taken effect yet
"""

NAMES = [
    "Margaret O'Neill", "Tomasz Kowalski", "Priya Raghunathan", "Daniel Whitcombe",
    "Fatima Al-Sayed", "Gareth Pemberton", "Lucia Fernandes", "Hannah Brightwell",
    "Oluwaseun Adeyemi", "Callum Ferguson", "Ingrid Solheim", "Rashid Mahmood",
]
STREETS = ["Larch Avenue", "Orchard Road", "Millbank Lane", "Harbour Street",
           "Willow Drive", "Quarry Road", "Bramble Lane", "Station Road"]
INJURIES = [
    "slipped on the wet stairs and fractured a wrist, attended hospital",
    "suffered whiplash and was taken to hospital by ambulance",
    "cut a hand on broken glass and needed stitches",
    "sprained an ankle wading out and has ongoing pain",
]

FAMILIES = {
    "flood": ("River water overflowed its banks after heavy rain and entered the ground "
              "floor of {name}'s home at {addr}. About {depth} of water stood in the "
              "living areas for two days. Flooring and ground floor joinery are damaged."),
    "surface_water": ("Intense rainfall caused water to pool across the ground and pour in "
                      "at the rear door of {name}'s home at {addr}. The ground floor is "
                      "wet; the river did not rise."),
    "surface_basement": ("Intense rainfall sent surface water down the steps into the "
                         "basement room of {name}'s home at {addr}. Stored items and the "
                         "basement carpet are ruined."),
    "flood_outbuilding": ("River water overflowed its banks and flooded the garden shed and "
                          "the driveway at {name}'s home at {addr}. The house itself stayed dry."),
    "escape_of_water": ("A fixed supply pipe under the kitchen sink at {name}'s home at "
                        "{addr} burst without warning on the day of loss. Water ran for "
                        "about an hour before it was shut off."),
    "gradual_leak": ("{name} at {addr} found the bathroom ceiling stained and soft. A plumber "
                     "traced a slow leak behind the bath that had been dripping for around "
                     "three weeks."),
    "theft_lodger": ("Items worth several thousand were missing from {name}'s home at {addr}. "
                     "There was no sign of forced entry; the lodger who rents a room there "
                     "moved out the same day."),
    "vacancy": ("{name}'s home at {addr} has been empty for about 75 days while the "
                "owner was abroad. A burst water tank was found on return."),
    "fire": ("A pan fire in the kitchen of {name}'s home at {addr} spread to the units and "
             "the ceiling. The fire service attended."),
    "deliberate": ("An adult son of {name} living at {addr} smashed the glazed doors and a "
                   "television during an argument."),
    "hydrolock": ("{name} drove the car through standing water on the road near {addr} and "
                  "the engine stopped. The garage reports water drawn into the cylinders."),
    "motor_flood_interior": ("{name}'s car, parked near {addr}, was left in rising flood water. "
                             "Water reached the seats and the dashboard electrics."),
    "racing": ("{name} crashed the car at {addr} circuit during a track day event. The front "
               "end is damaged."),
    "unlicensed": ("{name}'s nephew was driving the car near {addr} and hit a wall. He does "
                   "not hold a driving licence."),
    "collision": ("{name} was hit at a junction near {addr} by a van that failed to give "
                  "way. The rear wing and bumper are damaged."),
    "wear_tear": ("{name}'s car stopped near {addr} with a failed gearbox. The garage says "
                  "the clutch assembly wore out."),
}

# (id, family, policy, loss_date, peril_class, boundary, expected_cites, in_force, ask)
ROWS = [
    ("w01", "flood", "POL-H-1001", "2024-08-11", "flood", "pre_2025",
     [("HO-0850", "07-23", "2.1")], True, False),
    ("w02", "flood", "POL-H-1002", "2025-03-31", "flood", "pre_2025",
     [("HO-0850", "07-23", "2.1")], True, False),
    ("w03", "flood", "POL-H-1001", "2025-04-01", "flood", "post_2025",
     [("HO-0850", "04-25", "E-52")], True, True),
    ("w04", "flood", "POL-H-1004", "2025-08-19", "flood", "post_2025",
     [("HO-0850", "04-25", "E-52")], True, False),
    ("w05", "surface_water", "POL-H-1002", "2024-11-02", "surface_water", "pre_2025",
     [("HO-0850", "07-23", "2.2")], True, False),
    ("w06", "surface_water", "POL-H-1004", "2025-06-10", "surface_water", "post_2025",
     [("HO-0850", "04-25", "2.2")], True, False),
    ("w07", "escape_of_water", "POL-H-1001", "2024-02-14", "escape_of_water", "pre_2025",
     [("HO-0850", "07-23", "2.3")], True, False),
    ("w08", "escape_of_water", "POL-H-1004", "2025-09-03", "escape_of_water", "post_2025",
     [("HO-0850", "04-25", "2.3")], True, False),
    ("w09", "surface_basement", "POL-H-1004", "2025-05-20", "surface_water", "post_2025",
     [("HO-0850", "04-25", "E-55")], True, False),
    ("w10", "flood_outbuilding", "POL-H-1002", "2024-09-09", "flood", "pre_2025",
     [("HO-0850", "07-23", "E-52")], True, False),
    ("w11", "hydrolock", "POL-M-2001", "2024-10-20", "flood", "pre_2025",
     [("MO-0420", "09-23", "E-65")], True, False),
    ("w12", "hydrolock", "POL-M-2001", "2025-04-30", "flood", "pre_2025",
     [("MO-0420", "09-23", "E-65")], True, True),
    ("w13", "hydrolock", "POL-M-2002", "2025-05-01", "flood", "post_2025",
     [("MO-0420", "05-25", "E-65")], True, False),
    ("w14", "hydrolock", "POL-M-2002", "2025-11-12", "flood", "post_2025",
     [("MO-0420", "05-25", "E-65")], True, False),
    ("w15", "motor_flood_interior", "POL-M-2003", "2024-12-03", "flood", "pre_2025",
     [("MO-0420", "09-23", "2.1")], True, False),
    ("w16", "motor_flood_interior", "POL-M-2004", "2025-06-18", "flood", "post_2025",
     [("MO-0420", "05-25", "2.1")], True, False),
    ("w17", "theft_lodger", "POL-H-1001", "2025-01-20", "theft", "base",
     [("HO-0100", "01-22", "E-03")], True, True),
    ("w18", "gradual_leak", "POL-H-1002", "2024-05-05", "escape_of_water", "pre_2025",
     [("HO-0850", "07-23", "E-50")], True, False),
    ("w19", "gradual_leak", "POL-H-1004", "2025-07-07", "escape_of_water", "post_2025",
     [("HO-0850", "04-25", "E-50")], True, False),
    ("w20", "vacancy", "POL-H-1001", "2025-02-10", "other", "base",
     [("HO-0100", "01-22", "E-05")], True, False),
    ("w21", "fire", "POL-H-1004", "2024-10-10", "fire", "base",
     [("HO-0100", "01-22", "2.2")], True, False),
    ("w22", "racing", "POL-M-2001", "2025-02-02", "other", "base",
     [("MO-0100", "03-22", "E-61")], True, True),
    ("w23", "unlicensed", "POL-M-2002", "2025-09-09", "other", "base",
     [("MO-0100", "03-22", "E-62")], True, False),
    ("w24", "collision", "POL-M-2004", "2025-07-01", "collision", "base",
     [("MO-0100", "03-22", "2.1")], True, False),
    ("w25", "wear_tear", "POL-M-2003", "2024-03-03", "other", "base",
     [("MO-0100", "03-22", "E-60")], True, False),
    ("w26", "deliberate", "POL-H-1002", "2025-02-28", "other", "base",
     [("HO-0100", "01-22", "E-02")], True, False),
    ("w27", "flood", "POL-H-1005", "2025-06-15", "flood", "lapsed",
     [], False, True),
    ("w28", "escape_of_water", "POL-H-1003", "2025-10-05", "escape_of_water", "lapsed",
     [], False, False),
    ("w29", "collision", "POL-M-2003", "2025-09-15", "collision", "lapsed",
     [], False, False),
    ("w30", "flood", "POL-H-1001", "2022-03-01", "flood", "lapsed",
     [], False, False),
    ("w31", "flood", "POL-H-1001", "2023-03-15", "flood", "no_edition",
     [], True, False),
]

QUESTION = "Please confirm this is covered so I can tell the claimant today."


def _build():

    claims = []

    for i, (cid, family, policy, loss_date, peril, boundary, cites, in_force,
            ask) in enumerate(ROWS):

        name = NAMES[i % len(NAMES)]
        street = STREETS[i % len(STREETS)]
        addr = f"{10 + 3 * i} {street}"
        injury = INJURIES[i % len(INJURIES)] if i % 3 == 0 else None

        narrative = FAMILIES[family].format(name=name, addr=addr, depth="40 cm")

        if injury:
            narrative += f" {name.split()[0]} {injury}."

        claims.append({
            "case_id": cid,
            "claim_number": f"CLM-2026-{80000 + i + 1}",
            "policy_number": policy,
            "loss_date": loss_date,
            "claimant_name": name,
            "address": addr,
            "injury": injury,
            "narrative": narrative,
            "reported_amount": 4000 + 1750 * (i % 7),
            "question": QUESTION if ask else None,
            # --- the answer key; never returned by any tool ---
            "truth": {
                "peril_class": peril,
                "boundary": boundary,
                "in_force": in_force,
                "expected_cites": cites,
            },
        })

    return claims


CLAIMS = _build()
CLAIMS_BY_NUMBER = {c["claim_number"]: c for c in CLAIMS}
CLAIMS_BY_CASE = {c["case_id"]: c for c in CLAIMS}
