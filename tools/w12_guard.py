"""The output guard: the system never states a coverage decision.

Compliance's rule, from a regulator's finding: nothing automated may state
a coverage decision; it may only surface wording and facts for an adjuster
to decide on. A prompt that says so is a request. This is the enforcement:
a check in code on every sentence the model authored, run before the
referral leaves the process, whose verdict the eval asserts independently.

What is checked and what is not. The model authors the referral `summary`
and each citation's `relevance`; those are scanned. The verbatim wording
excerpt attached to each citation is *quoted from the policy by the
system*, is labelled as such, and is not scanned - a contract that says
"We do not cover loss described below" is evidence for the adjuster, not
the assistant announcing a decision. Scanning the quote would force the
system to hide the very wording it exists to surface.

On a violation the model's prose is discarded and replaced with a
templated summary built only from structured fields. Rewriting the model's
sentence ("covered" -> "within scope") would be the system editing a
decision into a different decision; discarding it is the only repair that
cannot leave one behind. The trigger is recorded, because a guard that
fires silently is a failure mode that has been hidden rather than fixed.
"""

import re

# A decision is not only the word "covered". "Excluded", "payable",
# "declined" and "we will pay" all state one, as do their negations, so the
# list is by meaning and the negated forms are caught by the same stems.
DECISION_PATTERNS = [
    # "coverage" on its own is procedure vocabulary ("coverage-in-force
    # check") and is allowed; the decision constructions around it are not.
    r"\bcover(?:ed|s)?\b",
    r"\buncovered\b",
    r"\bno coverage\b",
    r"\bcoverage (?:applies|applied|exists|is (?:available|excluded|denied|confirmed)|does not)\b",
    r"\b(?:full|partial|no|any) cover\b",
    r"\bexclud(?:ed|es|e|ing)\b",
    r"\bexclusion applies\b",
    r"\bpayable\b",
    r"\bwe (?:will|shall|can|would) (?:pay|settle|reimburse|indemnify)\b",
    r"\b(?:is|are|will be|would be|should be) (?:approved|accepted|paid|settled)\b",
    r"\b(?:declin|den)(?:ed|y|ial|ied)\b",
    r"\b(?:entitled|eligible) to\b",
    r"\bclaim (?:is|was|should be) (?:valid|invalid|rejected|accepted)\b",
    r"\bnot (?:eligible|entitled|payable)\b",
]

DECISION_RE = re.compile("|".join(DECISION_PATTERNS), re.IGNORECASE)


def scan_prose(text):
    """Every decision-language match in a piece of model-authored text."""

    return [m.group(0) for m in DECISION_RE.finditer(text or "")]


def referral_prose(referral):
    """The model-authored strings of a referral, labelled by where they sit."""

    items = [("summary", referral.get("summary", ""))]

    for index, citation in enumerate(referral.get("citations", [])):
        items.append((f"citations[{index}].relevance", citation.get("relevance", "")))

    return items


def safe_summary(referral):
    """A summary built only from structured fields - no model-authored words."""

    in_force = referral.get("in_force")
    state = ("in force on the loss date" if in_force
             else "not shown as in force on the loss date")

    parts = [f"Policy {state} ({referral.get('loss_date')})."]

    cites = referral.get("citations", [])

    if cites:
        listed = "; ".join(
            f"{c['form_number']} ed. {c['edition_date']} clause {c['clause']}"
            for c in cites
        )
        parts.append(f"Wording retrieved as at the loss date: {listed}.")

    parts.append("This assistant does not decide claims. Referred to an adjuster.")

    return " ".join(parts)


def guard_referral(referral):
    """
    Enforce the rule on a referral dict, in place. Returns the guard record.

    The record is stored on the referral as `guard`, so the log shows both
    that the check ran and what it caught, whether or not it caught anything.
    """

    hits = []

    for where, text in referral_prose(referral):
        found = scan_prose(text)
        if found:
            hits.append({"field": where, "matches": found, "text": text[:240]})

    record = {"checked": True, "triggered": bool(hits), "hits": hits}

    if hits:
        referral["summary"] = safe_summary(referral)

        for citation in referral.get("citations", []):
            if scan_prose(citation.get("relevance", "")):
                citation["relevance"] = "See wording excerpt."

    referral["guard"] = record

    return record
