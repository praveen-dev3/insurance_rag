"""PII for the capstone: what is redacted, and how the audit finds a leak.

The brief's line is "claimant names, addresses and injuries out of the
logs and out of anything your MCP server returns". Three different things,
so three different mechanisms, and one audit that does not trust any of
them:

  names      replaced by exact match against the claimant record (the same
             registry idea as rag/tracing.py: exact where the identifier is
             known, never a regex hope)
  addresses  replaced by exact match, then by a street-pattern backstop
  injuries   cannot be matched by name - they are free text - so the
             sentence is *dropped*, not rewritten, on a lexicon of injury
             words. Rewriting an injury sentence leaves the injury in.

`find_pii` is the audit: it searches any text for the claim data the
system is known to hold. It is run over every MCP response at the server
boundary (the wire guard) and over every log line by the eval, so "what
did your MCP server hand over" is answered by a search, not by a promise.
"""

import re

from data.w12_claims import CLAIMS

INJURY_WORDS = re.compile(
    r"\b(injur\w*|fractur\w*|whiplash|stitches|sprain\w*|ambulance|hospital|"
    r"bruis\w*|burn(?:s|ed|t)?|broke(?:n)?|ongoing pain|concussion)\b",
    re.IGNORECASE,
)

STREET_PATTERN = re.compile(
    r"\b\d{1,4}\s+[A-Z][a-z]+\s+(?:Avenue|Road|Lane|Street|Drive)\b"
)


def _name_parts(name):
    return [part for part in re.split(r"[\s-]+", name) if len(part) >= 4]


# claim_number -> list of literal strings that must never leave the system
def _registry():

    registry = {}

    for claim in CLAIMS:

        literals = {claim["claimant_name"], claim["address"]}
        literals.update(_name_parts(claim["claimant_name"]))

        if claim["injury"]:
            literals.add(claim["injury"])

        registry[claim["claim_number"]] = sorted(literals, key=len, reverse=True)

    return registry


REGISTRY = _registry()
ALL_LITERALS = sorted({lit for lits in REGISTRY.values() for lit in lits},
                      key=len, reverse=True)


def find_pii(text):
    """Every known PII literal (and injury word) present in `text`."""

    hits = []
    lowered = text.lower()

    for literal in ALL_LITERALS:
        if literal.lower() in lowered:
            hits.append(literal)

    for match in INJURY_WORDS.finditer(text):
        hits.append(match.group(0))

    return hits


def redact_narrative(claim):
    """
    The redacted view of one FNOL narrative.

    Sentence-level on purpose. Injury sentences are removed whole, because
    "[CLAIMANT] suffered [INJURY]" still states an injury; names and
    addresses are then substituted, and the street-pattern backstop catches
    an address that was typed differently from the one on record.
    """

    sentences = re.split(r"(?<=[.!?])\s+", claim["narrative"])
    kept = [s for s in sentences if not INJURY_WORDS.search(s)]
    text = " ".join(kept)

    text = text.replace(claim["address"], "the insured address")

    for literal in sorted(
        {claim["claimant_name"], *_name_parts(claim["claimant_name"])},
        key=len, reverse=True,
    ):
        text = re.sub(re.escape(literal), "the insured", text, flags=re.IGNORECASE)

    text = STREET_PATTERN.sub("the insured address", text)

    return text
