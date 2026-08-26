"""The criteria a regex can settle, taken back off the judge.

Every check in here used to be a line in the judge prompt (see
eval/judge_v0.txt). They were moved out for three reasons, in order of how
much they cost:

  * a model can be wrong about them. Asking gpt-oss whether "2026-02-11"
    is a parseable date introduces a failure rate into a question that has
    none;
  * they are the majority of the judge's output, so they dominate any
    aggregate "score" the judge produces, which means the number moves
    when formatting changes and not when reasoning does;
  * they cost a token per case per criterion, forever, to answer a
    question `re.fullmatch` answers for nothing.

What is left for the judge is the one thing a regex genuinely cannot do:
decide whether a sentence about coverage follows from the wording that was
retrieved. That is in rag/judge.py, and it is a single binary criterion.

Each assertion returns an Assertion rather than a bare bool, because "did
it pass" is not enough to act on. `detail` is what makes a failure
readable in a table without opening the summary.
"""

import re
from dataclasses import asdict, dataclass
from datetime import date

from rag.claims import coverage_position, parse_summary

# The claim number format the claims system issues and the summary is
# required to echo. Anchored, because "CLM-2026-044171" is not a claim
# number and a substring search would say it was.
CLAIM_NUMBER = re.compile(r"^CLM-\d{4}-\d{5}$")
CLAIM_NUMBER_ANYWHERE = re.compile(r"\bCLM-\d{4}-\d{5}\b")

# ISO first because that is what the prompt asks for, then the two forms
# the model reaches for when it paraphrases instead.
DATE_FORMATS = (
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), ("y", "m", "d")),
    (re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b"), ("d", "m", "y")),
)

MONTHS = {
    name.lower(): number
    for number, name in enumerate(
        ("January", "February", "March", "April", "May", "June", "July",
         "August", "September", "October", "November", "December"),
        start=1,
    )
}

LONG_DATE = re.compile(
    r"\b(\d{1,2})\s+([A-Z][a-z]+)\s+(\d{4})\b|"
    r"\b([A-Z][a-z]+)\s+(\d{1,2}),?\s+(\d{4})\b"
)

# A currency amount: optional symbol, digits with optional thousands
# separators, optional decimals. "2,500", "$2,500.00" and "2500" all pass;
# "UNKNOWN", "the Coverage A limit" and "2%" do not.
MONEY = re.compile(r"(?<![\d.])(?:\$\s?)?(\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{2})?\b")

# A percentage deductible is a real answer for HO-0412, whose deductible is
# 2% of Coverage A subject to a $1,000 minimum. Accepting it is not a
# loosening of the check: refusing it would fail the summaries that got
# that form exactly right.
PERCENT = re.compile(r"\b\d+(?:\.\d+)?\s?%")

EXCLUSION_CODE = re.compile(r"\bE-\d{2}\b")

# The chunk_id citation the summary prompt demands. Both the correct form
# (`source.pdf#hash`) and the truncated form the model sometimes emits are
# matched, so a truncated id is reported as an unresolved citation rather
# than silently missed.
CITATION = re.compile(r"\[\s*chunk_id\s*=\s*([^\|\]]+?)\s*(?:\|[^\]]*)?\]",
                      re.IGNORECASE)

NOT_STATED = {"unknown", "n/a", "na", "none", "not stated", "not provided",
              "unspecified", "not applicable", "-", ""}


@dataclass
class Assertion:
    """One deterministic check on one summary."""

    name: str
    passed: bool
    detail: str
    expected: str | None = None
    found: str | None = None

    def to_dict(self):
        return asdict(self)


def _normalise(value):
    return (value or "").strip().strip("*_`").strip()


def _is_not_stated(value):
    return _normalise(value).lower() in NOT_STATED


# ============================================================
# 1. CLAIM NUMBER ECHOED IN CLM-YYYY-NNNNN FORM
# ============================================================

def assert_claim_number(summary, claim):
    """
    The claim number is echoed, is well formed, and is the right one.

    All three, not just the format. A summary that invents a
    correctly-shaped claim number is worse than one that omits it: it
    routes the file to a claim that exists and belongs to someone else.
    """

    fields = parse_summary(summary)
    stated = _normalise(fields.get("Claim number"))

    if not stated or _is_not_stated(stated):

        # The field may be absent but the number present in the narrative.
        # Accept that: the requirement is that the summary echoes it, not
        # that it uses the layout.
        loose = CLAIM_NUMBER_ANYWHERE.search(summary or "")
        stated = loose.group(0) if loose else ""

    if not stated:
        return Assertion(
            "claim_number_echoed", False,
            "no claim number anywhere in the summary",
            expected=claim.claim_number, found=None,
        )

    token = CLAIM_NUMBER_ANYWHERE.search(stated)
    token = token.group(0) if token else stated

    if not CLAIM_NUMBER.fullmatch(token):
        return Assertion(
            "claim_number_echoed", False,
            f"'{token}' is not in CLM-YYYY-NNNNN form",
            expected=claim.claim_number, found=token,
        )

    if token != claim.claim_number:
        return Assertion(
            "claim_number_echoed", False,
            f"echoed '{token}' but the claim is '{claim.claim_number}'",
            expected=claim.claim_number, found=token,
        )

    return Assertion(
        "claim_number_echoed", True, "echoed and matches the claim record",
        expected=claim.claim_number, found=token,
    )


# ============================================================
# 2. DATE OF LOSS PRESENT AND PARSEABLE
# ============================================================

def parse_date(text):
    """
    First parseable date in the text, as a `date`, or None.

    Several formats are accepted because the requirement is that the date
    be *parseable*, not that the model obeyed the layout. Rejecting
    "11 February 2026" would fail a summary that stated the date of loss
    perfectly well, and the resulting number would be measuring
    formatting compliance under a label that says correctness.
    """

    text = text or ""

    for pattern, order in DATE_FORMATS:

        match = pattern.search(text)

        if match:
            parts = dict(zip(order, match.groups()))
            try:
                return date(int(parts["y"]), int(parts["m"]), int(parts["d"]))
            except ValueError:
                continue

    match = LONG_DATE.search(text)

    if match:

        if match.group(1):
            day, month_name, year = match.group(1, 2, 3)
        else:
            month_name, day, year = match.group(4, 5, 6)

        month = MONTHS.get((month_name or "").lower())

        if month:
            try:
                return date(int(year), month, int(day))
            except ValueError:
                return None

    return None


def assert_date_of_loss(summary, claim):
    """The date of loss is present, parses, and is the claim's date."""

    fields = parse_summary(summary)
    stated = _normalise(fields.get("Date of loss"))

    if not stated or _is_not_stated(stated):
        return Assertion(
            "date_of_loss_parseable", False,
            "no date of loss stated",
            expected=claim.date_of_loss, found=None,
        )

    parsed = parse_date(stated)

    if parsed is None:
        return Assertion(
            "date_of_loss_parseable", False,
            f"'{stated}' does not parse as a date",
            expected=claim.date_of_loss, found=stated,
        )

    expected = parse_date(claim.date_of_loss)

    if expected and parsed != expected:
        return Assertion(
            "date_of_loss_parseable", False,
            f"parsed {parsed.isoformat()} but the claim says "
            f"{expected.isoformat()}",
            expected=claim.date_of_loss, found=parsed.isoformat(),
        )

    return Assertion(
        "date_of_loss_parseable", True,
        f"parses to {parsed.isoformat()}",
        expected=claim.date_of_loss, found=parsed.isoformat(),
    )


# ============================================================
# 3. EXCESS / DEDUCTIBLE AMOUNT NUMERIC
# ============================================================

def assert_deductible_numeric(summary, claim=None):
    """
    The deductible field carries a number, not a description of one.

    "the deductible shown in the declarations" is not an amount, and a
    claims queue that routes on the figure cannot route on it. A
    percentage is accepted because two of the forms state their deductible
    that way.
    """

    fields = parse_summary(summary)
    stated = _normalise(fields.get("Deductible"))

    if not stated or _is_not_stated(stated):
        return Assertion(
            "deductible_numeric", False,
            "no deductible amount stated", found=None,
        )

    money = MONEY.search(stated)
    percent = PERCENT.search(stated)

    if not money and not percent:
        return Assertion(
            "deductible_numeric", False,
            f"'{stated[:60]}' states no numeric amount", found=stated[:60],
        )

    return Assertion(
        "deductible_numeric", True,
        f"numeric amount present: "
        f"{(money or percent).group(0)}",
        found=(money or percent).group(0),
    )


# ============================================================
# 4. EXCLUSION CLAUSE ID CITED WHENEVER A DENIAL IS STATED
# ============================================================

def assert_exclusion_cited_on_denial(summary, claim=None):
    """
    A denial names the exclusion it rests on.

    Conditional by design: this passes trivially where the position is not
    a denial, and that is correct. A denial without a clause id is the
    defect — it is the summary a regulator asks about and the file cannot
    answer.
    """

    position = coverage_position(summary)

    if position != "DENIED":
        return Assertion(
            "exclusion_cited_on_denial", True,
            f"not a denial (position={position or 'absent'}); "
            "criterion does not apply",
            found=position,
        )

    fields = parse_summary(summary)

    field_value = _normalise(fields.get("Exclusion relied on"))

    code = EXCLUSION_CODE.search(field_value)

    if not code:
        # Fall back to the narrative before failing: the requirement is
        # that the denial cites a code, not that it uses the field.
        code = EXCLUSION_CODE.search(summary or "")

    if not code:
        return Assertion(
            "exclusion_cited_on_denial", False,
            "denial stated with no exclusion code cited anywhere",
            found=field_value[:60] or None,
        )

    return Assertion(
        "exclusion_cited_on_denial", True,
        f"denial cites {code.group(0)}", found=code.group(0),
    )


# ============================================================
# 5. EVERY CITED chunk_id RESOLVES TO A RETRIEVED CHUNK
# ============================================================

def assert_citations_resolve(summary, claim=None, retrieved_ids=()):
    """
    Every chunk_id the summary cites was actually in its prompt.

    This is the check that turns a citation from decoration into
    something falsifiable, and it is pure set membership — exactly the
    kind of thing that has no business being asked of a model. A summary
    citing an id that was never retrieved has produced a reference that
    looks checkable and is not, which is the most expensive kind of wrong.
    """

    retrieved = set(retrieved_ids or ())

    cited = [match.group(1).strip() for match in CITATION.finditer(summary or "")]

    if not cited:
        return Assertion(
            "citations_resolve", False,
            "no chunk_id citation in the summary", found=None,
        )

    unresolved = sorted({c for c in cited if c not in retrieved})

    if unresolved:
        return Assertion(
            "citations_resolve", False,
            f"{len(unresolved)}/{len(set(cited))} cited chunk_id(s) were "
            f"not in the retrieved set: {unresolved[0][:40]}",
            found=", ".join(u[:40] for u in unresolved[:3]),
        )

    return Assertion(
        "citations_resolve", True,
        f"all {len(set(cited))} cited chunk_id(s) resolve",
        found=str(len(set(cited))),
    )


# ============================================================
# RUNNER
# ============================================================

ASSERTIONS = (
    "claim_number_echoed",
    "date_of_loss_parseable",
    "deductible_numeric",
    "exclusion_cited_on_denial",
    "citations_resolve",
)


def run_assertions(summary, claim, retrieved_ids=()):
    """
    Every deterministic check on one summary.

    Returns the list of Assertions and a bool for "all passed". No LLM is
    called, no network is touched, and the result is identical on every
    run — which is the entire argument for having moved them here.
    """

    results = [
        assert_claim_number(summary, claim),
        assert_date_of_loss(summary, claim),
        assert_deductible_numeric(summary, claim),
        assert_exclusion_cited_on_denial(summary, claim),
        assert_citations_resolve(summary, claim, retrieved_ids),
    ]

    return results, all(item.passed for item in results)
