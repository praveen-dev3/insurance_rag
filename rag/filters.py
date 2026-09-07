"""Metadata filtering, for the dense (Chroma) and sparse (BM25) halves.

Filtering happens *inside* each retriever, before fusion - not by throwing
away results after the top-k has been chosen. Post-filtering is simpler to
write and wrong in a specific way: ask for three chunks, filter two out,
and the prompt gets one chunk instead of three, with no signal that it
happened. Pre-filtering means each retriever fills its slots from the
documents the caller actually asked about.
"""


# ============================================================
# METADATA FILTERING
# ============================================================

# Metadata fields that accept a list of accepted values. All are exact
# string matches: a policy line is drawn from a controlled vocabulary, not
# free text, so substring matching would only create false positives
# ("motor" matching "motorhome").
SET_FILTERS = {
    "sources": "source",
    "policy_lines": "policy_line",
    "form_numbers": "form_number",
    "edition_dates": "edition_date",
}


def build_where(filters):
    """
    Translate a filter dict into a Chroma `where` clause.

    Supported keys: `sources`, `policy_lines`, `form_numbers` and
    `edition_dates` (each a list of accepted values), plus `page_min` and
    `page_max`. Page bounds match any chunk whose page range *overlaps*
    the requested window, so a chunk spanning pages 3-4 is returned for
    a "page 4 only" filter. Overlap rather than containment, because the
    chunker deliberately lets a clause straddle a page break rather than
    cutting it in half - demanding containment would hide exactly those
    chunks, which are the ones most likely to be a whole clause.

    The page clauses below are the standard interval-overlap test written
    out: two ranges overlap when each starts at or before the other one
    ends, which is why `page_min` is compared against `page_end` and
    `page_max` against `page_start` rather than the other way round.

    Filtering on policy_line is not a convenience. The exclusion codes are
    scoped per line - E-71 on the dwelling fire line and E-17 on the
    homeowners line say nearly the same thing in nearly the same words,
    and their dispositions differ. An unfiltered search over both lines
    retrieves the wrong form's answer with high confidence, which is worse
    than retrieving nothing.
    """

    if not filters:
        return None

    clauses = []

    for key, field_name in SET_FILTERS.items():

        values = filters.get(key)

        if values:
            clauses.append({field_name: {"$in": list(values)}})

    if filters.get("page_min") is not None:
        clauses.append({"page_end": {"$gte": int(filters["page_min"])}})

    if filters.get("page_max") is not None:
        clauses.append({"page_start": {"$lte": int(filters["page_max"])}})

    if not clauses:
        return None

    if len(clauses) == 1:
        return clauses[0]

    return {"$and": clauses}


def matches_filters(record, filters):
    """
    The same predicate as build_where, for the in-memory BM25 side.

    Kept deliberately parallel to build_where. A filter applied to the
    dense half of a hybrid search but not the sparse half does not fail
    loudly - it quietly leaks the filtered-out documents back in through
    fusion, and the result looks like a retrieval quality problem rather
    than a filtering bug.
    """

    if not filters:
        return True

    for key, field_name in SET_FILTERS.items():

        values = filters.get(key)

        if values and getattr(record, field_name, None) not in values:
            return False

    page_min = filters.get("page_min")

    if page_min is not None and record.page_end < int(page_min):
        return False

    page_max = filters.get("page_max")

    if page_max is not None and record.page_start > int(page_max):
        return False

    return True
