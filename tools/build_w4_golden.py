"""Build eval/golden_set.jsonl - 12 adjuster questions with chunk_ids.

The questions are written here as (question, anchor) pairs. The anchor is
a literal line of the endorsement that carries the answer; the chunk_id is
then *resolved* from it against the pinned index rather than typed in by
hand. Two reasons:

  * a hand-copied chunk_id is a transcription with no error detection. If
    it is wrong, hit-rate@3 is measured against a chunk that does not
    answer the question and the whole run is quietly meaningless.
  * resolving it means the label can be rebuilt after any re-index, and
    the script fails loudly if an anchor stops matching exactly one chunk.

Ground truth is at chunk level here, unlike Week 3, which labelled pages
on purpose because chunk ids move when the chunker changes. Week 4 pins
the chunker and varies only the retriever, so chunk ids are stable across
every run in this experiment - which makes the stricter label safe, and
it is what the brief asks for.

Usage:  python tools/build_w4_golden.py
"""

import json
import sys
from pathlib import Path

import chromadb

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prepare_corpus import prepare  # noqa: E402

from rag.config import CHROMA_PATH  # noqa: E402
from rag.indexing import build_collection  # noqa: E402

OUTPUT = Path("eval/golden_set.jsonl")

# Pinned for the whole experiment. The chunker is NOT a variable in
# Week 4 - it was settled in Week 3 - and pinning it is what lets chunk
# ids carry the ground truth.
COLLECTION = "week4"
CHUNK_STRATEGY = "structure"


# Written as adjuster phrasing rather than as clean search queries: these
# are the questions as they would actually arrive, abbreviations and all.
# Six of the twelve carry an exact token that dense retrieval is
# structurally bad at - an exclusion code, a form number, or an edition -
# against a required minimum of four.
QUESTIONS = [
    {
        "id": "w01",
        "form": "HO-0304",
        "question": "Does exclusion E-17 apply under form HO-0304 ed. 03-24 when a supply line bursts?",
        "anchor": "Constant or repeated seepage or leakage of water occurring over a period of fourteen",
        "exact_tokens": ["E-17", "HO-0304", "ed. 03-24"],
        "answer_contains": ["E-17"],
        "known_answer": "No. E-17 covers seepage over 14+ days; a burst supply line is a sudden and accidental discharge under Clause 2.1 and stays covered.",
    },
    {
        "id": "w02",
        "form": "HO-0412",
        "question": "Insured is claiming hail dents that did not puncture the shingles. Does E-34 on HO-0412 knock it out?",
        "anchor": "Cosmetic damage to roof surfacing that does not compromise the water-shedding function of",
        "exact_tokens": ["E-34", "HO-0412"],
        "answer_contains": ["E-34"],
        "known_answer": "Yes. E-34 excludes cosmetic damage absolutely where the water-shedding function is intact.",
    },
    {
        "id": "w03",
        "form": "HO-0521",
        "question": "Sump pump had no service records at all. Which exclusion code on HO-0521 do I cite?",
        "anchor": "Back-up or overflow caused by the failure of the insured to maintain, service or test the",
        "exact_tokens": ["HO-0521"],
        "answer_contains": ["E-44"],
        "known_answer": "E-44 - back-up or overflow caused by failure to maintain, service or test the sump pump to the manufacturer schedule.",
    },
    {
        "id": "w04",
        "form": "HO-0633",
        "question": "Guest hurt during a short-let stay. Does E-53 bite if they only rented the place 10 days that year?",
        "anchor": "Bodily injury to a home-sharing occupant however caused",
        "exact_tokens": ["E-53"],
        "answer_contains": ["E-53"],
        "known_answer": "No. Clause 4.2 disapplies E-53 within the 14-day allowance in Clause 4.1.",
    },
    {
        "id": "w05",
        "form": "DP-0208",
        "question": "What does E-72 exclude on DP-0208 ed. 05-24?",
        "anchor": "Water damage from a plumbing system in a dwelling vacant more than 60",
        "exact_tokens": ["E-72", "DP-0208", "ed. 05-24"],
        "answer_contains": ["E-72"],
        "known_answer": "Water damage from a plumbing system in a dwelling vacant more than 60 consecutive days. Excluded absolutely.",
    },
    {
        "id": "w06",
        "form": "HO-0710",
        "question": "Under HO-0710 ed. 11-23, what counts as a supply line?",
        "anchor": "Supply line means any pipe, hose, tube, fitting or connector",
        "exact_tokens": ["HO-0710", "ed. 11-23"],
        "answer_contains": ["supply line"],
        "known_answer": "Any pipe, hose, tube, fitting or connector conveying water under mains pressure to a fixture, up to and including its shut-off valve. Not a waste or drain pipe.",
    },
    {
        "id": "w07",
        "form": "HO-0304",
        "question": "Is water damage from a burst pipe covered on a homeowners policy?",
        "anchor": "2.1 We cover direct physical loss to covered property caused by the sudden and accidental",
        "exact_tokens": [],
        "answer_contains": [],
        "known_answer": "Yes, as a sudden and accidental discharge, subject to the Clause 3 exclusions and the Clause 5 limits.",
    },
    {
        "id": "w08",
        "form": "HO-0304",
        "question": "How much will we pay out for mould after a covered water loss?",
        "anchor": "Our total liability for mould, fungus or wet rot",
        "exact_tokens": [],
        "answer_contains": ["10,000"],
        "known_answer": "$10,000 in any one policy year, part of and not in addition to the Coverage A limit.",
    },
    {
        "id": "w09",
        "form": "HO-0412",
        "question": "What deductible applies on a wind claim?",
        "anchor": "two percent (2%) of the Coverage A limit",
        "exact_tokens": [],
        "answer_contains": [["2%", "2 percent", "two percent"]],
        "known_answer": "2% of the Coverage A limit per loss, minimum $1,000, replacing the all-perils deductible.",
    },
    {
        "id": "w10",
        "form": "HO-0412",
        "question": "Roof is 18 years old. Do we settle replacement cost or actual cash value?",
        "anchor": "2.2 Where the roof surfacing is more than fifteen (15) years old at the date of loss",
        "exact_tokens": [],
        "answer_contains": ["actual cash value"],
        "known_answer": "Actual cash value, because the roof surfacing is more than fifteen years old.",
    },
    {
        "id": "w11",
        "form": "HO-0521",
        "question": "Is there a cap on sewer backup claims per year?",
        "anchor": "twenty-five thousand dollars ($25,000) in the aggregate",
        "exact_tokens": [],
        "answer_contains": ["25,000"],
        "known_answer": "$25,000 aggregate for all back-up losses in any one policy year.",
    },
    {
        "id": "w12",
        "form": "HO-0710",
        "question": "If two endorsements both cover the same loss and they disagree, which one wins?",
        "anchor": "3.1 Where two or more endorsements attached to this policy address the same loss",
        "exact_tokens": [],
        "answer_contains": [],
        "known_answer": "The endorsement with the later edition date controls, to the extent of the inconsistency.",
    },
]


def build_index(client):
    """Index the pinned corpus under the pinned chunker."""

    files = prepare(verbose=False)

    print(f"Indexing {len(files)} documents under '{CHUNK_STRATEGY}'...")

    return build_collection(
        client,
        name=COLLECTION,
        strategy=CHUNK_STRATEGY,
        pdf_files=files,
    )


def resolve_anchor(collection, anchor, form):
    """
    Find the one chunk of `form` whose text contains this anchor line.

    Ambiguity is an error, not something to resolve by picking the first
    match: two chunks containing the same anchor means the ground truth
    would be arbitrary, and hit-rate@3 would depend on which one the
    builder happened to choose.
    """

    payload = collection.get(include=["documents", "metadatas"])

    matches = [
        {
            "chunk_id": chunk_id,
            "text": text,
            "metadata": metadata or {},
        }
        for chunk_id, text, metadata in zip(
            payload["ids"],
            payload.get("documents") or [],
            payload.get("metadatas") or [],
        )
        if anchor in (text or "")
        and (metadata or {}).get("form_number") == form
    ]

    if len(matches) != 1:
        raise SystemExit(
            f"Anchor {anchor!r} on {form} matched {len(matches)} chunks; expected "
            f"exactly 1. Matches: {[m['chunk_id'] for m in matches]}"
        )

    return matches[0]


def main():

    client = chromadb.PersistentClient(path=CHROMA_PATH)

    collection = build_index(client)

    rows = []

    print(f"\nResolving {len(QUESTIONS)} anchors to chunk ids...\n")

    for entry in QUESTIONS:

        match = resolve_anchor(collection, entry["anchor"], entry["form"])
        metadata = match["metadata"]

        row = {
            "id": entry["id"],
            "question": entry["question"],
            "chunk_id": match["chunk_id"],
            "form_number": metadata.get("form_number"),
            "edition_date": metadata.get("edition_date"),
            "policy_line": metadata.get("policy_line"),
            "clause": metadata.get("clause_label"),
            "source_file": metadata.get("source_file"),
            "pages": [metadata.get("page_start"), metadata.get("page_end")],
            "exact_tokens": entry["exact_tokens"],
            "has_exact_token": bool(entry["exact_tokens"]),
            "answer_contains": entry["answer_contains"],
            "known_answer": entry["known_answer"],
            "anchor": entry["anchor"],
            "answerable": True,
        }

        rows.append(row)

        print(
            f"  {row['id']}  {'[exact]' if row['has_exact_token'] else '       '}  "
            f"{row['form_number']:<9} {row['clause']:<22} {row['chunk_id']}"
        )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    exact = sum(1 for row in rows if row["has_exact_token"])

    print(f"\nWrote {len(rows)} questions to {OUTPUT}")
    print(f"  with an exact token dense retrieval is bad at: {exact}/12")
    print(f"  distinct chunk ids: {len({row['chunk_id'] for row in rows})}")


if __name__ == "__main__":
    main()
