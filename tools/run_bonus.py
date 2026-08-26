"""Bonus: where precision beats completeness, and loses.

The hypothesis the brief proposes is that a structure-aware chunker can
retrieve *better* and answer *worse*. A tight exclusion-row chunk is a
precise retrieval target, and precisely because it is tight it carries
only the row - not the definitions clause on another form that says what
the row's own escape hatch means.

The question below is built to need both halves:

    A supply line ruptured abruptly, but the leak was not discovered for
    twenty days. Does E-17 apply?

  * HO-0304 Exclusion Table 3.1 (E-17) excludes seepage lasting fourteen
    days or more, and disapplies itself for a sudden and accidental
    discharge under Clause 2.1. Reading only this row, twenty days looks
    decisive and the answer is "excluded".
  * HO-0710 Clause 2.1 defines sudden and accidental by ONSET - abrupt,
    at an identifiable point in time - not by duration. Reading this too,
    an abrupt rupture stays sudden and accidental however long it then
    ran, and E-17 does not apply.
  * HO-0304 Clause 2.3 then adds the real limit: a discharge the insured
    knew of or should have known of is not sudden and accidental.

So the correct answer needs at least two forms in the prompt. A chunker
that retrieves the E-17 row perfectly, and only the E-17 row, gets a
better rank and a worse answer.

Usage:  python tools/run_bonus.py
"""

import json
import sys
from pathlib import Path

import chromadb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.config import CHROMA_PATH  # noqa: E402
from rag.generation import generate_answer, is_generation_error  # noqa: E402
from rag.indexing import build_collection  # noqa: E402
from rag.retrieval import HybridRetriever  # noqa: E402

OUTPUT = Path("eval/results/task_d/bonus.json")

# Two probes, both reported, including the one that did not behave as
# predicted. Reporting only the probe that produced the effect would be
# choosing the evidence after seeing it, which is the same error as
# writing the eight questions after looking at what retrieval returned.
PROBES = {
    "probe_1_late_discovery": (
        "A supply line ruptured abruptly, but the leak was not discovered "
        "for twenty days. Does exclusion E-17 apply under HO-0304?"
    ),
    # The trap. Read alone, the E-17 row says it does not apply to a
    # sudden and accidental discharge, and the insured is asserting the
    # crack was sudden - so the row alone answers "not excluded". HO-0710
    # Clause 2.1 says a process developing over fourteen days or more is
    # NOT sudden and accidental regardless of intent, which reverses it.
    "probe_2_gradual_crack": (
        "Water seeped from a cracked fitting for twenty days. The insured "
        "says the crack appeared suddenly and was unintended. Does "
        "exclusion E-17 apply under HO-0304?"
    ),
}

# The two things a complete answer has to have seen.
NEEDED = {
    "E-17 row (HO-0304 Exclusion Table 3.1)": "Constant or repeated seepage",
    "definition of sudden and accidental (HO-0710 Clause 2.1)": (
        "abrupt in onset and unintended by the insured"
    ),
}

# Matches what the app answers with, not what the sweep measured at k=5.
TOP_K = 3

STRATEGIES = ("recursive", "structure")


def run(client, strategy, question, retriever=None):

    chunks, trace = retriever.search(question, top_k=TOP_K)

    prompt_text = "\n".join(chunk.text for chunk in chunks)

    coverage = {
        label: anchor in prompt_text
        for label, anchor in NEEDED.items()
    }

    answer = generate_answer(question, chunks)

    if is_generation_error(answer):
        raise RuntimeError(answer)

    # Where the E-17 row itself landed in the ranking, which is the
    # "retrieval win" half of the claim.
    row_rank = next(
        (
            rank
            for rank, chunk in enumerate(trace.reranked, start=1)
            if NEEDED["E-17 row (HO-0304 Exclusion Table 3.1)"] in chunk.text
        ),
        None,
    )

    return {
        "strategy": strategy,
        "question": question,
        "e17_row_rank": row_rank,
        "prompt_chunks": [
            {
                "rank": rank,
                "chunk_id": chunk.id,
                "form_number": chunk.form_number,
                "clause": chunk.clause_label,
                "rerank_score": (
                    round(chunk.rerank_score, 4)
                    if chunk.rerank_score is not None else None
                ),
                "text": chunk.text.strip(),
            }
            for rank, chunk in enumerate(chunks, start=1)
        ],
        "coverage": coverage,
        "complete_context": all(coverage.values()),
        "answer": answer,
    }


def main():

    client = chromadb.PersistentClient(path=CHROMA_PATH)

    results = {}

    for strategy in STRATEGIES:

        collection = build_collection(
            client, name=f"bonus_{strategy}", strategy=strategy
        )
        retriever = HybridRetriever(collection)

        for probe, question in PROBES.items():

            print(f"\n=== {probe} / {strategy} ===")

            result = run(client, strategy, question, retriever)
            results.setdefault(probe, {})[strategy] = result

            print(f"  E-17 row rank in ranking : {result['e17_row_rank']}")

            for label, present in result["coverage"].items():
                print(f"  in prompt: {'YES' if present else 'NO ':<4} {label}")

            print(f"  answer:\n{result['answer']}\n")

        try:
            client.delete_collection(f"bonus_{strategy}")
        except Exception:
            pass

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps({"probes": PROBES, "top_k": TOP_K, "runs": results},
                   indent=2, default=str),
        encoding="utf-8",
    )

    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
