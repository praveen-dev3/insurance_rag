"""Week 3 Task Set D: run every measurement and dump the raw evidence.

Produces four artefacts under eval/results/task_d/ which results.md is
then written from:

  chunking_hit5.json    the two hit-in-top-5 numbers, plus the full
                        search-only dump for all 8 questions under both
                        strategies - every rank, every score, every
                        chunk_id, and whether it was a hit.
  filter_demo.json      one query run unfiltered and filtered on
                        policy_line, both result lists with scores.
  answers.json          3 answerable questions generated with citations,
                        each citation checked against the index.
  refusals.json         3 out-of-corpus questions and what came back.

Usage:
    python tools/run_task_d.py            # everything
    python tools/run_task_d.py retrieval  # skip the LLM stages
"""

import json
import sys
from pathlib import Path

import chromadb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.config import CHROMA_PATH  # noqa: E402
from rag.engine import RagEngine  # noqa: E402
from rag.generation import (  # noqa: E402
    NO_ANSWER,
    is_generation_error,
    is_refusal,
    verify_citations,
)
from rag.indexing import build_collection  # noqa: E402
from rag.retrieval import HybridRetriever  # noqa: E402

GOLDEN_SET = Path("eval/endorsements_golden.json")
OUTPUT_DIR = Path("eval/results/task_d")

# The number the brief asks for is hit-in-top-5, so k is 5 here regardless
# of the TOP_K the app answers with.
K = 5

# The two strategies under comparison. Everything else - embedding model,
# retrieval mode, reranker, chunk size, overlap - is held fixed, because
# changing two things and reporting one number teaches nothing about
# which one moved it.
STRATEGIES = ("recursive", "structure")


def load_cases():

    payload = json.loads(GOLDEN_SET.read_text(encoding="utf-8"))

    cases = payload["cases"]

    return (
        [case for case in cases if case["answerable"]],
        [case for case in cases if not case["answerable"]],
    )


# ============================================================
# SCORING
# ============================================================

def is_hit(chunk, case):
    """
    Does this chunk actually contain the claim, from the right form?

    Both halves are required. A chunk from HO-0304 that does not contain
    the E-17 row is not a hit - it is the right document and the wrong
    text. A chunk containing seepage language from DP-0208 is not a hit
    either, even though it reads almost identically, because the
    disposition on the dwelling fire line is different.
    """

    if chunk.form_number != case["form_number"]:
        return False

    return any(
        anchor in line
        for anchor in case["anchors"]
        for line in chunk.text.splitlines()
    )


def dump_row(chunk, rank, case):
    """One line of the search-only dump."""

    return {
        "rank": rank,
        "hit": is_hit(chunk, case),
        "chunk_id": chunk.id,
        "form_number": chunk.form_number,
        "edition_date": chunk.edition_date,
        "policy_line": chunk.policy_line,
        "clause": chunk.clause_label,
        "pages": [chunk.page_start, chunk.page_end],
        "rerank_score": (
            round(chunk.rerank_score, 4)
            if chunk.rerank_score is not None else None
        ),
        "rrf_score": round(chunk.rrf_score, 6),
        "dense_rank": chunk.dense_rank,
        "sparse_rank": chunk.sparse_rank,
        "text": chunk.text.strip(),
    }


# ============================================================
# 1. CHUNKING COMPARISON
# ============================================================

def run_chunking_comparison(client, cases):
    """
    Index the corpus under each strategy and run the same 8 questions.

    A throwaway collection per strategy, because a collection holding
    chunks from two chunkers cannot answer "which chunker retrieved
    this?" - and that is the entire question.
    """

    results = {}

    for strategy in STRATEGIES:

        collection_name = f"task_d_{strategy}"

        print(f"\n=== Indexing under '{strategy}' ===")

        collection = build_collection(
            client,
            name=collection_name,
            strategy=strategy,
        )

        retriever = HybridRetriever(collection)

        rows = []
        hits = 0

        print(f"--- Searching ({strategy}), k={K} ---")

        for case in cases:

            _, trace = retriever.search(case["question"], top_k=K)

            # The reranked list is the system's ranking. The score floor
            # that trims it lives downstream and is a refusal mechanism,
            # not a ranking one, so it is reported but not applied here.
            ranked = trace.reranked[:K]

            dump = [
                dump_row(chunk, rank, case)
                for rank, chunk in enumerate(ranked, start=1)
            ]

            hit_ranks = [row["rank"] for row in dump if row["hit"]]
            hit = bool(hit_ranks)
            hits += int(hit)

            print(
                f"  {case['id']}  hit@{K}={'Y' if hit else 'N'}  "
                f"first_hit_rank={hit_ranks[0] if hit_ranks else '-'}  "
                f"{case['form_number']}/{case['clause']}"
            )

            rows.append({
                "id": case["id"],
                "question": case["question"],
                "expected_form": case["form_number"],
                "expected_clause": case["clause"],
                "exclusion_code": case.get("exclusion_code"),
                "tags": case["tags"],
                "hit_at_5": hit,
                "first_hit_rank": hit_ranks[0] if hit_ranks else None,
                "results": dump,
            })

        results[strategy] = {
            "strategy": strategy,
            "k": K,
            "chunks_indexed": retriever.size,
            "hit_at_5": hits,
            "of": len(cases),
            "rows": rows,
        }

        print(f"  => {strategy}: {hits}/{len(cases)} hit-in-top-{K}")

        try:
            client.delete_collection(collection_name)
        except Exception:
            pass

    return results


# ============================================================
# 2. METADATA FILTER DEMONSTRATION
# ============================================================

# Chosen because the two policy lines say nearly the same thing in nearly
# the same words: HO-0304 E-12 and DP-0208 E-72 both exclude water damage
# in a dwelling vacant more than 60 days. Only the form differs, so an
# unfiltered search has no way to prefer the right one.
FILTER_QUERY = (
    "water damage from a plumbing system while the dwelling "
    "was vacant for more than 60 days"
)

FILTER_ON = {"policy_lines": ["homeowners"]}


def run_filter_demo(client):

    collection = build_collection(client, name="task_d_filter", strategy="structure")
    retriever = HybridRetriever(collection)

    print("\n=== Metadata filter demonstration ===")

    output = {"query": FILTER_QUERY, "filter": FILTER_ON, "runs": {}}

    for label, filters in (("unfiltered", None), ("filtered", FILTER_ON)):

        _, trace = retriever.search(FILTER_QUERY, top_k=K, filters=filters)

        rows = [
            {
                "rank": rank,
                "chunk_id": chunk.id,
                "form_number": chunk.form_number,
                "edition_date": chunk.edition_date,
                "policy_line": chunk.policy_line,
                "clause": chunk.clause_label,
                "pages": [chunk.page_start, chunk.page_end],
                "rerank_score": (
                    round(chunk.rerank_score, 4)
                    if chunk.rerank_score is not None else None
                ),
                "rrf_score": round(chunk.rrf_score, 6),
                "text": chunk.text.strip(),
            }
            for rank, chunk in enumerate(trace.reranked[:K], start=1)
        ]

        output["runs"][label] = rows

        top = rows[0] if rows else None

        print(
            f"  {label:<11} top-1: "
            f"{top['form_number'] if top else '-'} "
            f"[{top['policy_line'] if top else '-'}] "
            f"score={top['rerank_score'] if top else '-'}"
        )

    try:
        client.delete_collection("task_d_filter")
    except Exception:
        pass

    return output


# ============================================================
# 3. CITED ANSWERS AND REFUSALS
# ============================================================

def run_generation(cases, refusals):
    """
    Answer three questions with citations, and refuse three without.

    Uses the live index rather than a throwaway one, because this is the
    behaviour of the shipping app and not an experiment.
    """

    engine = RagEngine()

    print("\n=== Cited answers ===")

    answered = []

    for case in cases[:3]:

        result = engine.ask(case["question"], top_k=3)

        # An outage would otherwise be recorded as "0 citations", which is
        # indistinguishable from a prompt that stopped working. Stop.
        if is_generation_error(result["answer"]):
            raise RuntimeError(
                f"Generation failed on {case['id']}, so no answer quality "
                f"can be measured: {result['answer']}"
            )

        verification = verify_citations(result["answer"], result["chunks"])

        print(
            f"  {case['id']}: {len(verification['cited'])} citation(s), "
            f"all resolve = {verification['all_resolve']}"
        )

        answered.append({
            "id": case["id"],
            "question": case["question"],
            "expected_form": case["form_number"],
            "expected_clause": case["clause"],
            "known_answer": case["known_answer"],
            "answer": result["answer"],
            "verification": verification,
            "retrieved": [
                {
                    "chunk_id": chunk.id,
                    "citation": chunk.citation,
                    "form_number": chunk.form_number,
                    "clause": chunk.clause_label,
                    "text": chunk.text.strip(),
                }
                for chunk in result["chunks"]
            ],
        })

    print("\n=== Refusals ===")

    refused = []

    for case in refusals:

        result = engine.ask(case["question"], top_k=3)

        if is_generation_error(result["answer"]):
            raise RuntimeError(
                f"Generation failed on {case['id']}: {result['answer']}"
            )

        refusal = is_refusal(result["answer"])

        print(f"  {case['id']}: refused = {refusal}")

        refused.append({
            "id": case["id"],
            "question": case["question"],
            "answer": result["answer"],
            "is_refusal": refusal,
            "expected_sentence": NO_ANSWER,
            "retrieved": [
                {
                    "chunk_id": chunk.id,
                    "citation": chunk.citation,
                    "rerank_score": (
                        round(chunk.rerank_score, 4)
                        if chunk.rerank_score is not None else None
                    ),
                }
                for chunk in result["chunks"]
            ],
            "dropped_below_floor": len(result["trace"].dropped_below_floor),
        })

    return answered, refused


# ============================================================

def save(payload, name):

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    path = OUTPUT_DIR / name
    path.write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8"
    )

    print(f"  wrote {path}")

    return path


def main():

    stage = sys.argv[1] if len(sys.argv) > 1 else "all"

    cases, refusals = load_cases()

    print(
        f"{len(cases)} answerable questions "
        f"({sum(1 for c in cases if 'exclusion-row' in c['tags'])} "
        f"depend on an exclusions-table row), "
        f"{len(refusals)} out-of-corpus questions."
    )

    client = chromadb.PersistentClient(path=CHROMA_PATH)

    comparison = run_chunking_comparison(client, cases)
    save(comparison, "chunking_hit5.json")

    filter_demo = run_filter_demo(client)
    save(filter_demo, "filter_demo.json")

    if stage != "retrieval":
        answered, refused = run_generation(cases, refusals)
        save(answered, "answers.json")
        save(refused, "refusals.json")

    print("\nSummary")
    print("-------")

    for strategy, result in comparison.items():
        print(
            f"  {strategy:<11} {result['hit_at_5']}/{result['of']} "
            f"hit-in-top-{K}   ({result['chunks_indexed']} chunks indexed)"
        )


if __name__ == "__main__":
    main()
