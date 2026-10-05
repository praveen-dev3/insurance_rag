"""Loss-date-aware retrieval over the real RagEngine.

The capstone's live wound: a 2024 flood loss assessed against the 2025
flood exclusion, "because the newer document simply read better to whoever
searched it". A retriever ranks by relevance, and relevance has no idea
which edition was in force, so the fix cannot live in the ranking and
cannot live in the prompt. It lives here, as a filter this code builds
from the loss date and hands to the engine's metadata filter, and then
*re-checks* on the way out.

Two layers, deliberately:

  1. pre-filter - `form_numbers` and `edition_dates` go into the engine's
     `filters`, so each retriever fills its slots only from the in-force
     editions (rag/filters.py explains why pre- not post-filtering).
  2. post-check - the engine's two filters are independent sets, so a
     (form, edition) pair that is not in force can still slip through when
     two forms share an edition string. Every returned chunk is therefore
     checked against the exact in-force *pair*, and a leak is counted and
     dropped rather than trusted away.

`date_filter=False` is the "before": the same engine, scoped to the product
but blind to the date - which is what the unfiltered system did, and what
the bonus challenge's RED run uses.

This module must be the first thing in a process to import `rag`, because
rag.config reads DOCUMENTS_FOLDER / CHROMA_PATH / COLLECTION_NAME at import
time and the capstone corpus lives beside, not inside, the Week 3-10 one.
"""

import os
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ["DOCUMENTS_FOLDER"] = str(REPO_ROOT / "insurance_docs_w12")
os.environ["CHROMA_PATH"] = str(REPO_ROOT / "chroma_db_w12")
os.environ["COLLECTION_NAME"] = "w12_wordings"

from data.w12_wordings import EDITIONS, PRODUCT_FORMS  # noqa: E402
from w12_inforce import edition_in_force, effective_range, editions_for_product  # noqa: E402

_engine = None


def get_engine():
    """Build the engine once per process; construction costs seconds."""

    global _engine

    if _engine is None:
        # The engine prints index-progress lines to stdout. In an MCP server
        # stdout IS the protocol, so anything printed there corrupts the
        # JSON-RPC stream. Send it to stderr for the duration of the build.
        real_stdout = sys.stdout
        sys.stdout = sys.stderr

        try:
            from rag.engine import RagEngine
            _engine = RagEngine()
        finally:
            sys.stdout = real_stdout

    return _engine


def _chunk_view(chunk, loss_date):

    # Effective ranges come from the edition table, not from the PDF, so a
    # system with no date filter has no honest way to state them - and
    # stating them anyway would hand the "before" arm the answer.
    try:
        eff_from, eff_to = effective_range(chunk.form_number, chunk.edition_date)
    except KeyError:
        eff_from = eff_to = None

    if loss_date is None:
        eff_from = eff_to = None

    # What a citation can name. The chunk's own label ("Exclusion Table 3.1")
    # is a section heading, not something an adjuster can look up a clause
    # by, and a model handed only that cites it - so the citable ids are
    # listed outright: exclusion codes, plus numbered sub-clauses (2.1, 3.1).
    numbered = re.findall(r"(?m)(?:^|\s)(\d{1,2}\.\d{1,2})\s", chunk.text)
    cite_as = sorted(set(chunk.exclusion_codes) | set(numbered))

    return {
        "chunk_id": chunk.id,
        "form_number": chunk.form_number,
        "edition_date": chunk.edition_date,
        "effective_from": eff_from,
        "effective_to": eff_to,
        "section": chunk.clause_label or chunk.clause,
        "cite_as": cite_as,
        "exclusion_codes": list(chunk.exclusion_codes),
        "text": chunk.text[:1100],
        "rerank_score": (round(chunk.rerank_score, 3)
                         if chunk.rerank_score is not None else None),
        "resolved_for_loss_date": loss_date if loss_date else None,
    }


def _complete_pairs(kept, pairs, loss_date):
    """
    Add the coverage-basis chunk of every versioned edition the results touched.

    Why this exists (Week 12 failure, 3 of 25 integrated requests): a search
    for "flood exclusion" is answered by the exclusion-table chunks, which
    crowd the 2. COVERAGE BASIS chunk out of the top 3. The exclusion table's
    own note says "within Clause 2.1", so the model cites 2.1 - a clause it
    was never shown. Citing a clause that retrieval did not return is not a
    model-quality problem a better prompt fixes; the diagnosis from the
    logged context ids is one hop, and so is the fix: when the results touch
    a versioned endorsement edition, the edition's coverage-basis section
    travels with its exclusions. It costs one extra passage (~300 tokens) per
    versioned edition per search, which the cost report accounts for.
    """

    have = {(c.form_number, c.edition_date) for c in kept
            if (c.clause_label or "").startswith("2.")}
    added = []

    for form, edition in sorted({(c.form_number, c.edition_date) for c in kept}):

        if len(EDITIONS.get(form, [])) < 2 or (form, edition) in have:
            continue

        chunks, _ = get_engine().retrieve(
            "coverage basis sub-limit deductible", top_k=6,
            filters={"form_numbers": [form], "edition_dates": [edition]},
        )
        found = next((c for c in chunks if (c.clause_label or "").startswith("2.")
                      and (c.form_number, c.edition_date) in pairs), None)

        if found is not None:
            added.append(found)

    return added


def search_wording(query, product, loss_date, top_k=3, date_filter=True,
                   complete_pairs=True):
    """
    Search the wordings of one product, as at one loss date.

    Returns {matches, editions_in_force, notices, stats}. `notices` is for
    the model and the adjuster: when a form had no edition in force on the
    loss date it says so out loud, because an empty result for that form is
    otherwise indistinguishable from "searched and found nothing".
    """

    started = time.perf_counter()
    forms = PRODUCT_FORMS[product]
    in_force = editions_for_product(product, loss_date)
    notices = []

    if date_filter:

        pairs = {(f, e) for f, e in in_force.items() if e}

        for form, edition in in_force.items():
            if edition is None:
                notices.append(
                    f"no edition of {form} was in force on {loss_date}; "
                    f"nothing from {form} can be cited for this loss date."
                )

        if not pairs:
            return {"matches": [], "editions_in_force": in_force,
                    "notices": notices, "stats": {"leaked_dropped": 0, "ms": 0.0}}

        filters = {
            "form_numbers": sorted({f for f, _ in pairs}),
            "edition_dates": sorted({e for _, e in pairs}),
        }
    else:
        pairs = None
        filters = {"form_numbers": list(forms)}

    # Capped at 3: the agent loop re-sends every result on every later lap,
    # so each extra passage is paid for again per lap, and the corpus is
    # small enough that a fourth passage is rarely the one that matters.
    top_k = max(1, min(int(top_k), 3))

    # Over-fetch so that dropping a leaked chunk does not leave a hole.
    chunks, _trace = get_engine().retrieve(
        query, filters=filters, top_k=top_k + (4 if date_filter else 0)
    )

    leaked = 0
    kept = []

    for chunk in chunks:

        if date_filter and (chunk.form_number, chunk.edition_date) not in pairs:
            leaked += 1
            continue

        kept.append(chunk)

    kept = kept[:top_k]
    added = _complete_pairs(kept, pairs, loss_date) if (date_filter and complete_pairs) else []

    # With the filter off there is no date resolution to report, and saying
    # there was would be the system lying about what it did.
    stamp = loss_date if date_filter else None

    return {
        "matches": [_chunk_view(c, stamp) for c in kept + added],
        **({"editions_in_force": in_force} if date_filter else {}),
        "notices": notices,
        "stats": {
            "leaked_dropped": leaked,
            "pair_completion_added": len(added),
            "ms": round((time.perf_counter() - started) * 1000, 1),
        },
    }
