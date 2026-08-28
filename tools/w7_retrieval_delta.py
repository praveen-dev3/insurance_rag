"""Prove the Week 5 prediction with a retrieval-only number.

    python tools/w7_retrieval_delta.py

prediction.txt (commit ad526e4) named the mode, the exact change, and a
falsifiable delta:

    "A claim summary currently issues ONE retrieval over the whole
    adjuster note with top_k=3 ... Change it to a two-part retrieval
    scoped to the form the claim file names ... deductible_numeric
    assertion pass rate: 0% -> at least 70%."

This script checks the retrieval half of that claim — whether the
deductible/excess clause is now IN the context handed to the model — on
the 25 cases in eval/w6_cases.json, OLD shape against NEW shape, with no
LLM call. Per CLAUDE.md: "Prove retrieval changes with a number ...
retrieval eval makes no LLM calls, so it is cheap." Whether the model then
extracts a numeric figure from a clause that is present is a separate,
paid question — measured downstream by tools/run_w6.py's assertions, and
NOT this script's job.

  OLD shape:  one retrieval over the notes, top_k=3, no form filter — what
              tools/run_w6.py did before this change. Reproduced through
              retrieve_for_claim itself (deductible_top_k=0 disables the
              second leg) rather than a hand-rolled second implementation
              that could quietly drift from what the app actually ran.
  NEW shape:  rag.claims.retrieve_for_claim() at its current defaults —
              the notes leg plus the deductible leg, form-filtered when
              the claim names one.

"Found a deductible clause" is a retrieval-side proxy, not the assertion
itself: does any retrieved chunk's clause label or text carry deductible/
excess vocabulary. It is deliberately looser than assert_deductible_numeric
(which requires a parsed number in the generated summary) because at this
stage nothing has been generated yet — the question is only whether the
clause reached the prompt at all.
"""

import re
from pathlib import Path

from _runner import read_json, write_json

from rag.claims import ClaimFile, retrieve_for_claim
from rag.config import DEFAULT_MODE
from rag.engine import RagEngine
from rag.tracing import Redactor

CASES_PATH = Path("eval/w6_cases.json")
OUT_PATH = Path("eval/w7/retrieval_delta.json")

OLD_TOP_K = 3

DEDUCTIBLE_WORDS = re.compile(
    r"\bdeductible\b|\bexcess\b|\blimit of liability\b|\bamount of insurance\b"
    r"|\bamount payable\b",
    re.IGNORECASE,
)


def carries_deductible(chunk):
    """Cheap, deterministic proxy: does this chunk look like the clause
    that states a deductible or excess amount, going only on what a
    retrieval-only check can see (clause label and chunk text — never the
    generated summary)."""

    haystack = f"{chunk.clause_label} {chunk.clause} {chunk.text}"

    return bool(DEDUCTIBLE_WORDS.search(haystack))


def wrong_line_chunks(chunks, claim):
    """Chunks whose policy_line does not match the claim's, and is known.

    Mirrors the `wrong_policy_line` field tools/run_w6.py already records
    on a generated summary row — computed here pre-generation, so mode 3
    ("comes back with the wrong product's wording") is checkable without
    spending a token either.
    """

    return sorted({
        chunk.policy_line for chunk in chunks
        if chunk.policy_line not in (claim.policy_line, "unspecified")
    })


def load_claims(path=CASES_PATH):

    payload = read_json(path)
    redactor = Redactor()

    claims = []

    for case in payload["cases"]:

        claim = ClaimFile(
            claim_id=case["id"],
            claim_number=case["claim_number"],
            claimant=case["claimant"],
            date_of_loss=case["date_of_loss"],
            policy_line=case["policy_line"],
            notes=case["notes"],
            form_number=case.get("form_number"),
        ).redacted(redactor)

        claims.append((case, claim))

    return claims


def run():

    engine = RagEngine()

    rows = []

    for case, claim in load_claims():

        # OLD shape, reproduced through the SAME function rather than a
        # second, separately-maintained retrieval path: one leg
        # (deductible_top_k=0 disables the second), no form filter, the
        # top_k the app used before this change. Routing both sides
        # through retrieve_for_claim is what makes this an honest
        # before/after — a hand-rolled "old" implementation could drift
        # from what the app actually ran without anyone noticing.
        _, old_chunks, _ = retrieve_for_claim(
            engine, claim,
            top_k=OLD_TOP_K, deductible_top_k=0, scope_to_form=False,
            mode=DEFAULT_MODE, reranker="ms-marco",
        )

        _, new_chunks, _ = retrieve_for_claim(
            engine, claim, mode=DEFAULT_MODE, reranker="ms-marco",
        )

        old_hit = any(carries_deductible(chunk) for chunk in old_chunks)
        new_hit = any(carries_deductible(chunk) for chunk in new_chunks)

        rows.append({
            "id": case["id"],
            "mode": case["mode"],
            "form_number": claim.form_number,
            "old": {
                "chunk_ids": [c.id for c in old_chunks],
                "deductible_found": old_hit,
                "wrong_policy_line": wrong_line_chunks(old_chunks, claim),
            },
            "new": {
                "chunk_ids": [c.id for c in new_chunks],
                "deductible_found": new_hit,
                "wrong_policy_line": wrong_line_chunks(new_chunks, claim),
            },
        })

        print(f"  {case['id']:<8} deductible: "
              f"{'FOUND' if old_hit else 'missing':<8} -> "
              f"{'FOUND' if new_hit else 'missing':<8}  "
              f"wrong-line: {len(wrong_line_chunks(old_chunks, claim))} -> "
              f"{len(wrong_line_chunks(new_chunks, claim))}")

    n = len(rows)
    old_rate = sum(r["old"]["deductible_found"] for r in rows) / n
    new_rate = sum(r["new"]["deductible_found"] for r in rows) / n

    old_contaminated = sum(bool(r["old"]["wrong_policy_line"]) for r in rows)
    new_contaminated = sum(bool(r["new"]["wrong_policy_line"]) for r in rows)

    summary = {
        "n": n,
        "deductible_found_rate": {"old": old_rate, "new": new_rate},
        "wrong_policy_line_count": {
            "old": old_contaminated, "new": new_contaminated,
        },
        "rows": rows,
    }

    print(f"\ndeductible_found_rate  old={old_rate:.1%}  new={new_rate:.1%}")
    print(f"wrong_policy_line      old={old_contaminated}/{n}  "
          f"new={new_contaminated}/{n}")
    print(
        "\nprediction.txt claimed deductible_numeric would clear 70% after "
        "the fix. This is the retrieval-side precondition for that claim, "
        "not the claim itself — run tools/run_w6.py to spend the tokens "
        "and check the assertion."
    )

    out = write_json(OUT_PATH, summary)
    print(f"\nSaved {out}")

    return summary


def main():

    run()


if __name__ == "__main__":
    main()
