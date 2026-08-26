"""Resolve a chunk_id printed in an answer back to the stored chunk.

This is what makes a citation checkable rather than decorative. Paste any
chunk_id from an answer and get back the exact text that was indexed under
it, with its form number, edition, policy line and clause.

    python tools/resolve_chunk.py HO-0304_water_damage_ed_03-24.pdf#ad1f3ac26ec308ef

Pass --contains to assert that the chunk really carries a claim, which is
the check a grader would run by hand:

    python tools/resolve_chunk.py <chunk_id> --contains "fourteen (14)"

Exits non-zero if the id does not resolve, or if --contains is not found,
so it can be used as a test rather than only read.
"""

import argparse
import sys
from pathlib import Path

import chromadb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.config import CHROMA_PATH, COLLECTION_NAME  # noqa: E402
from rag.indexing import open_collection  # noqa: E402

FIELDS = (
    "source_file",
    "form_number",
    "edition_date",
    "policy_line",
    "clause_label",
    "document_title",
    "exclusion_codes",
    "page_start",
    "page_end",
)


def resolve(chunk_id, collection_name=None):
    """Fetch one chunk by id, or None."""

    client = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = open_collection(client, collection_name or COLLECTION_NAME)

    payload = collection.get(ids=[chunk_id], include=["documents", "metadatas"])

    if not payload.get("ids"):
        return None

    return {
        "id": payload["ids"][0],
        "text": (payload.get("documents") or [""])[0],
        "metadata": (payload.get("metadatas") or [{}])[0] or {},
    }


def main():

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("chunk_id", help="The chunk_id to resolve.")
    parser.add_argument(
        "--contains",
        help="Assert the chunk contains this substring; exit 1 if not."
    )
    parser.add_argument("--collection", default=None)

    args = parser.parse_args()

    chunk = resolve(args.chunk_id, args.collection)

    if chunk is None:
        print(f"UNRESOLVED: no chunk with id {args.chunk_id!r} in the index.")
        return 1

    metadata = chunk["metadata"]

    print(f"chunk_id: {chunk['id']}")

    for name in FIELDS:
        if metadata.get(name) not in (None, ""):
            print(f"{name}: {metadata[name]}")

    print("-" * 72)
    print(chunk["text"])
    print("-" * 72)

    if args.contains:

        found = args.contains in chunk["text"]

        print(
            f"contains {args.contains!r}: "
            f"{'YES' if found else 'NO'}"
        )

        return 0 if found else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
