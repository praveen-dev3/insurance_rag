"""Structural audit of a chunking strategy over the endorsement pack.

Answers three questions that "the chunks look better" cannot:

  intact       is every exclusion row present in some chunk with its
               disposition still attached?
  attributed   does the chunk carrying a row name the form that scopes it?
  located      does the chunk carry the clause the row sits under?

A row can be intact and still useless. E-17 with its disposition but
without "HO-0304" is a rule with no scope - the same code on DP-0208 has a
different disposition, so an unattributed row cannot be acted on. That is
why attribution is counted separately from intactness.

Usage:  python tools/chunk_report.py [strategy ...]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.chunking import _parse_units, create_chunks  # noqa: E402
from rag.indexing import load_documents  # noqa: E402

STRATEGIES = ("fixed", "recursive", "sentence", "structure")


def endorsement_files():
    """The six-form drop, excluding the base wording."""

    return [
        path for path in sorted(Path("insurance_docs").glob("*.pdf"))
        if path.name != "policy.pdf"
    ]


def canonical_rows(documents):
    """
    Every exclusion row as the parser sees it, keyed by form and code.

    This is the ground truth a chunker is measured against: the row text
    that ought to survive chunking, taken from the document itself rather
    than from any chunker's output.
    """

    by_source = {}

    for document in documents:
        by_source.setdefault(document["source"], []).append(document)

    rows = {}

    for source, pages in by_source.items():

        pages = sorted(pages, key=lambda page: page["page"])
        metadata = pages[0]["metadata"]

        for unit in _parse_units(pages):

            if unit.kind != "row":
                continue

            rows[(metadata["form_number"], unit.codes[0])] = {
                "form_number": metadata["form_number"],
                "code": unit.codes[0],
                "text": unit.text,
                "lines": [
                    line.strip() for line in unit.text.splitlines()
                    if line.strip()
                ],
            }

    return rows


def audit(strategy, documents, rows):
    """Score one strategy against the canonical rows."""

    chunks = create_chunks(documents, strategy=strategy)

    intact = 0
    attributed = 0
    located = 0
    missing = []

    for (form, code), row in sorted(rows.items()):

        # A row is intact in a chunk when every one of its lines appears
        # in that one chunk. Line-wise rather than whole-string, because
        # the strategies differ in how they re-join line breaks.
        holder = None

        for chunk in chunks:

            if all(line in chunk["text"] for line in row["lines"]):
                holder = chunk
                break

        if holder is None:
            missing.append(f"{form}/{code}")
            continue

        intact += 1

        if form in holder["text"]:
            attributed += 1

        if holder.get("clause", "unspecified") != "unspecified":
            located += 1

    return {
        "strategy": strategy,
        "chunks": len(chunks),
        "rows": len(rows),
        "intact": intact,
        "attributed": attributed,
        "located": located,
        "split": missing,
    }


def main():

    strategies = sys.argv[1:] or list(STRATEGIES)

    documents = load_documents(endorsement_files())
    rows = canonical_rows(documents)

    print(f"\n{len(rows)} exclusion rows across the endorsement pack.\n")

    results = [audit(strategy, documents, rows) for strategy in strategies]

    header = (
        f"{'strategy':<11} {'chunks':>7} {'rows intact':>12} "
        f"{'form named':>11} {'clause known':>13}"
    )

    print("\n" + header)
    print("-" * len(header))

    for result in results:
        print(
            f"{result['strategy']:<11} {result['chunks']:>7} "
            f"{result['intact']:>7}/{result['rows']:<4} "
            f"{result['attributed']:>7}/{result['rows']:<3} "
            f"{result['located']:>9}/{result['rows']:<3}"
        )

    for result in results:
        if result["split"]:
            print(
                f"\n{result['strategy']}: rows split across chunks "
                f"({len(result['split'])}): {', '.join(result['split'])}"
            )


if __name__ == "__main__":
    main()
