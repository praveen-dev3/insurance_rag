"""Dates, editions and limits - the deterministic half of the capstone.

Everything here is plain Python over the tables in data/w12_wordings.py, no
model and no index. That is deliberate: "which wording was in force on the
loss date" and "was the policy in force on the loss date" are questions
with exactly one right answer, so they are answered by code that can be
unit-checked rather than by a retriever that can be argued with. The
retriever is then *constrained* by these answers (see w12_retrieval.py),
not asked to rediscover them.

Edition ranges are half-open, [from, to): a loss on the day an edition
takes effect belongs to it, and a loss on the day before belongs to its
predecessor. The capstone's bonus case ("one loss dated the day before it
took effect") is exactly that boundary.
"""

from datetime import date

from data.w12_wordings import (
    EDITIONS,
    LIMIT_FORM,
    LIMITS,
    PERIL_CLASSES,
    POLICIES,
    PRODUCT_FORMS,
)


def parse_date(value):
    """ISO date string -> date; raises ValueError on anything else."""

    if isinstance(value, date):
        return value

    return date.fromisoformat(str(value))


def edition_in_force(form_number, loss_date):
    """The edition of one form in force on a date, or None if there is none."""

    day = parse_date(loss_date)

    for row in EDITIONS.get(form_number, []):
        if row["from"] <= day and (row["to"] is None or day < row["to"]):
            return row["edition"]

    return None


def effective_range(form_number, edition):
    for row in EDITIONS[form_number]:
        if row["edition"] == edition:
            return (row["from"].isoformat(),
                    row["to"].isoformat() if row["to"] else None)

    raise KeyError((form_number, edition))


def editions_for_product(product, loss_date):
    """{form_number: edition or None} for every form of a product."""

    return {
        form: edition_in_force(form, loss_date)
        for form in PRODUCT_FORMS[product]
    }


def policy_in_force(policy_number, loss_date):
    """
    (in_force, matching_range, reason).

    The range is [start, end): a policy that ends on 2025-04-01 is not in
    force *on* 2025-04-01 - the same half-open convention as editions, so
    one rule governs both and an off-by-one cannot be right for one and
    wrong for the other.
    """

    policy = POLICIES.get(policy_number)

    if policy is None:
        return False, None, "unknown_policy"

    day = parse_date(loss_date)

    for start, end in policy["ranges"]:
        if start <= day < end:
            return True, (start.isoformat(), end.isoformat()), "in_force"

    return False, None, "loss_date_outside_in_force_ranges"


def limits_for(policy_number, loss_date, peril_class):
    """
    Deductible, sub-limit and policy limit - three numbers, kept apart.

    The policy limit comes from the policy (a sum insured); the deductible
    and the sub-limit come from the edition of the relevant form in force
    on the loss date. They are returned under separate keys so that nothing
    downstream has to guess which of two dollar figures is which.
    """

    policy = POLICIES.get(policy_number)

    if policy is None:
        return {"error": f"unknown policy {policy_number!r}"}

    product = policy["product"]

    if peril_class not in PERIL_CLASSES[product]:
        return {"error": (f"peril_class {peril_class!r} is not valid for a {product} "
                          f"policy; valid: {', '.join(PERIL_CLASSES[product])}")}

    form = LIMIT_FORM[(product, peril_class)]
    edition = edition_in_force(form, loss_date)

    if edition is None:
        return {"error": (f"no edition of {form} was in force on {loss_date}; the "
                          "limits table has nothing to apply. Refer this to an adjuster.")}

    row = LIMITS[(form, edition, peril_class)]

    return {
        "form_number": form,
        "edition_date": edition,
        "peril_class": peril_class,
        "deductible": row["deductible"],
        "sub_limit": row["sub_limit"],
        "policy_limit": policy["policy_limit"],
    }
