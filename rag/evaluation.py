"""Retrieval evaluation: hit-rate@k, recall@k, MRR, precision@k.

Eyeballing a handful of answers cannot tell you whether a change helped.
It cannot even tell you whether a change did anything. These metrics can,
because they are computed over a fixed question set with fixed ground
truth, so two runs differ only where the system differs.

Ground truth is at page level (see eval/golden_set.json for why), and a
retrieved chunk counts as relevant when its page range overlaps a
labelled page of the labelled source.

What each number means, for a single question:

  hit-rate@k   1 if any relevant chunk is in the top k, else 0.
               "Did the answer reach the prompt at all?"
  recall@k     share of the labelled pages covered by the top k.
               "How much of the answer reached the prompt?"
  precision@k  share of the top k that are relevant.
               "How much of the prompt was wasted?"
  MRR          1 / rank of the first relevant chunk.
               "How near the top was it?"

Averaged over the set, hit-rate@3 is the headline: with TOP_K=3 it is
literally the probability that the LLM was given something it could
answer from.
"""

import json
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path

from rag.chunking import CHUNK_STRATEGIES
from rag.config import GOLDEN_SET_PATH, TOP_K
from rag.indexing import build_collection
from rag.retrieval import HybridRetriever

STAGES = ("fused", "reranked", "final")


# ============================================================
# GOLDEN SET
# ============================================================

@dataclass
class EvalCase:
    """
    One labelled question.

    `relevant_pages` is the ground truth — the pages that actually answer
    the question. `answer_contains` holds strings the answer must quote
    to count as correct, and is left empty where no paraphrase-proof
    anchor exists. `answerable=False` marks a question the corpus cannot
    answer, where the correct behaviour is a refusal.
    """

    id: str
    question: str
    relevant_pages: list = field(default_factory=list)
    source: str | None = None
    answer_contains: list = field(default_factory=list)
    answerable: bool = True
    tags: list = field(default_factory=list)


def load_golden_set(path=None):
    """
    Read the labelled questions from disk.

    Missing file is a hard error rather than an empty set: silently
    evaluating zero questions would report a perfect score.
    """

    path = Path(path or GOLDEN_SET_PATH)

    if not path.exists():
        raise FileNotFoundError(
            f"Golden set not found at '{path}'. "
            "Author one, or pass --golden-set."
        )

    payload = json.loads(path.read_text(encoding="utf-8"))

    cases = [
        EvalCase(
            id=entry["id"],
            question=entry["question"],
            relevant_pages=entry.get("relevant_pages", []),
            source=entry.get("source"),
            answer_contains=entry.get("answer_contains", []),
            answerable=entry.get("answerable", True),
            tags=entry.get("tags", []),
        )
        for entry in payload["cases"]
    ]

    return cases


# ============================================================
# METRICS
# ============================================================

def is_relevant(chunk, case):
    """
    Does this chunk overlap a labelled page of the labelled document?

    Overlap, not containment: a chunk spanning pages 3-4 answers a
    question labelled to page 4, and demanding an exact page match would
    penalise the page-spanning chunking that exists precisely so a clause
    split by a page break stays whole.
    """

    if case.source and chunk.source != case.source:
        return False

    return any(
        chunk.page_start <= page <= chunk.page_end
        for page in case.relevant_pages
    )


def covered_pages(chunk, case):
    """Which labelled pages this chunk actually spans."""

    return {
        page
        for page in case.relevant_pages
        if chunk.page_start <= page <= chunk.page_end
    }


def score_ranking(chunks, case, k):
    """Every metric for one question against one ranked list."""

    top = chunks[:k]

    flags = [is_relevant(chunk, case) for chunk in top]

    first_relevant = next(
        (index + 1 for index, flag in enumerate(flags) if flag),
        None
    )

    found_pages = set()

    for chunk in top:
        found_pages |= covered_pages(chunk, case)

    total_pages = len(set(case.relevant_pages))

    return {
        "hit_rate": 1.0 if first_relevant else 0.0,
        "recall": (
            len(found_pages) / total_pages if total_pages else 0.0
        ),
        "precision": (sum(flags) / len(top)) if top else 0.0,
        "mrr": (1.0 / first_relevant) if first_relevant else 0.0,
        "first_relevant_rank": first_relevant,
        "retrieved": [
            {
                "id": chunk.id,
                "source": chunk.source,
                "pages": [chunk.page_start, chunk.page_end],
                "relevant": flag,
            }
            for chunk, flag in zip(top, flags)
        ],
    }


def _mean(values):
    return round(statistics.fmean(values), 4) if values else 0.0


def percentile(values, fraction):
    """
    Nearest-rank percentile over a small sample.

    numpy-style interpolation is not used, because on a 12-question set
    every percentile lands between two real measurements and interpolating
    invents a latency no query actually had.
    """

    if not values:
        return 0.0

    ordered = sorted(values)

    index = min(
        len(ordered) - 1,
        max(0, int(round(fraction * len(ordered) + 0.5)) - 1)
    )

    return round(ordered[index], 1)


def latency_summary(latencies):
    """
    p50 first, because it is the number that describes a typical query.

    On a set this small p95 is effectively the maximum - with 12 samples
    it is the 12th - so it reports the worst case, not the tail. Both are
    kept, but a change should be judged on p50 and the honest statement
    that p95 here is a single observation.
    """

    return {
        "p50": percentile(latencies, 0.50),
        "mean": round(_mean(latencies), 1),
        "p95": percentile(latencies, 0.95),
        "n": len(latencies),
    }


# ============================================================
# RETRIEVAL EVALUATION
# ============================================================

def evaluate_retrieval(retriever, cases, k=TOP_K, label="run",
                       transform=None, **search_options):
    """
    Run every answerable case through retrieval and aggregate.

    `transform` maps a question to (search_query, dense_query) — that is
    where query rewriting or HyDE plugs in, so their effect on retrieval
    can be measured on its own, without the generator in the way.

    No LLM is called unless `transform` calls one.
    """

    answerable = [case for case in cases if case.answerable]
    unanswerable = [case for case in cases if not case.answerable]

    rows = []
    latencies = []

    for case in answerable:

        search_query = dense_query = case.question

        if transform is not None:
            search_query, dense_query = transform(case.question)

        started = time.perf_counter()

        _, trace = retriever.search(
            case.question,
            search_query=search_query,
            dense_query=dense_query,
            top_k=k,
            **search_options
        )

        latencies.append((time.perf_counter() - started) * 1000)

        stage_scores = {
            "fused": score_ranking(trace.fused, case, k),
            "reranked": score_ranking(trace.reranked, case, k),
            "final": score_ranking(trace.final, case, k),
        }

        rows.append({
            "id": case.id,
            "question": case.question,
            "tags": case.tags,
            "expected_pages": case.relevant_pages,
            "search_query": search_query,
            "stages": stage_scores,
            # A case where the right chunk was fused but lost by the
            # reranker is a different bug from one never retrieved.
            "lost_in_rerank": (
                stage_scores["fused"]["hit_rate"] == 1.0
                and stage_scores["final"]["hit_rate"] == 0.0
            ),
        })

    # Unanswerable questions have no relevant page, so retrieval metrics
    # are undefined. What matters is whether the score floor rejected the
    # noise instead of handing it to the LLM.
    refusal_rows = []

    for case in unanswerable:

        search_query = dense_query = case.question

        if transform is not None:
            search_query, dense_query = transform(case.question)

        chunks, trace = retriever.search(
            case.question,
            search_query=search_query,
            dense_query=dense_query,
            top_k=k,
            **search_options
        )

        refusal_rows.append({
            "id": case.id,
            "question": case.question,
            "survivors": len(chunks),
            "dropped_below_floor": len(trace.dropped_below_floor),
            "best_score": (
                max(
                    (
                        chunk.rerank_score
                        for chunk in trace.reranked
                        if chunk.rerank_score is not None
                    ),
                    default=None
                )
            ),
        })

    metrics = {}

    for stage in STAGES:
        metrics[stage] = {
            f"hit_rate@{k}": _mean(
                [row["stages"][stage]["hit_rate"] for row in rows]
            ),
            f"recall@{k}": _mean(
                [row["stages"][stage]["recall"] for row in rows]
            ),
            f"precision@{k}": _mean(
                [row["stages"][stage]["precision"] for row in rows]
            ),
            "mrr": _mean([row["stages"][stage]["mrr"] for row in rows]),
        }

    return {
        "label": label,
        "k": k,
        "cases": len(answerable),
        "metrics": metrics,
        "headline": metrics["final"][f"hit_rate@{k}"],
        "latency_ms": latency_summary(latencies),
        "misses": [
            row["id"]
            for row in rows
            if row["stages"]["final"]["hit_rate"] == 0.0
        ],
        "lost_in_rerank": [
            row["id"] for row in rows if row["lost_in_rerank"]
        ],
        "out_of_scope": {
            "cases": len(unanswerable),
            "context_survived": sum(
                1 for row in refusal_rows if row["survivors"] > 0
            ),
            "rows": refusal_rows,
        },
        "rows": rows,
    }


# ============================================================
# ANSWER EVALUATION (retrieval + generation, with failure labels)
# ============================================================

def evaluate_answers(engine, cases, k=TOP_K, label="run", **options):
    """
    Generate an answer per case and label the failure kind.

    Costs one LLM call per case, which is why it is separate from
    retrieval evaluation — iterating on the retriever should not require
    paying for generation.
    """

    from rag.diagnostics import LABELS, classify_with_ground_truth

    rows = []
    counts = dict.fromkeys(LABELS, 0)

    for case in cases:

        result = engine.ask(case.question, top_k=k, **options)

        trace = result["trace"]
        answer = result["answer"]

        diagnosis = classify_with_ground_truth(
            trace,
            answer,
            relevant_pages=case.relevant_pages,
            source=case.source,
            answer_contains=case.answer_contains,
            answerable=case.answerable,
        )

        counts[diagnosis.label] += 1

        rows.append({
            "id": case.id,
            "question": case.question,
            "tags": case.tags,
            "answerable": case.answerable,
            "answer": answer,
            "label": diagnosis.label,
            "reason": diagnosis.reason,
            "retrieved": [
                {
                    "source": chunk.source,
                    "pages": [chunk.page_start, chunk.page_end],
                }
                for chunk in trace.final
            ],
        })

    total = len(rows) or 1

    return {
        "label": label,
        "k": k,
        "cases": len(rows),
        "counts": counts,
        "rates": {
            name: round(count / total, 4)
            for name, count in counts.items()
        },
        "rows": rows,
    }


# ============================================================
# SWEEPS
# ============================================================

def sweep_retrieval(retriever, cases, variants, k=TOP_K):
    """
    Compare retrieval settings on the existing index.

    Nothing is re-indexed, so this is the cheap sweep: modes, rerankers,
    MMR on/off.
    """

    results = []

    for variant in variants:

        name = variant.pop("label", None) or json.dumps(variant, sort_keys=True)

        print(f"\n--- {name} ---")

        results.append(
            evaluate_retrieval(retriever, cases, k=k, label=name, **variant)
        )

    return results


def sweep_chunking(chroma_client, cases, variants, k=TOP_K, **search_options):
    """
    Compare chunking settings, re-indexing the corpus for each.

    Each variant gets a throwaway collection so the live index is never
    disturbed, and the collection is deleted afterwards.
    """

    results = []

    for variant in variants:

        strategy = variant.get("strategy")
        chunk_size = variant.get("chunk_size")
        overlap = variant.get("overlap")

        if strategy and strategy not in CHUNK_STRATEGIES:
            raise ValueError(f"Unknown strategy '{strategy}'.")

        name = f"{strategy}/{chunk_size}/{overlap}"
        collection_name = (
            f"eval_{strategy}_{chunk_size}_{overlap}".replace("/", "_")
        )

        print(f"\n=== Indexing variant {name} ===")

        collection = build_collection(
            chroma_client,
            name=collection_name,
            strategy=strategy,
            chunk_size=chunk_size,
            overlap=overlap,
        )

        retriever = HybridRetriever(collection)

        result = evaluate_retrieval(
            retriever,
            cases,
            k=k,
            label=name,
            **search_options
        )

        result["chunks_indexed"] = retriever.size
        result["variant"] = variant

        results.append(result)

        try:
            chroma_client.delete_collection(collection_name)
        except Exception:
            pass

    return results


# ============================================================
# REPORTING
# ============================================================

def compare(before, after, k=TOP_K):
    """Before/after deltas for the headline metrics."""

    rows = []

    for stage in STAGES:

        for metric in (
            f"hit_rate@{k}", f"recall@{k}", f"precision@{k}", "mrr"
        ):
            old = before["metrics"][stage][metric]
            new = after["metrics"][stage][metric]

            rows.append({
                "stage": stage,
                "metric": metric,
                "before": old,
                "after": new,
                "delta": round(new - old, 4),
            })

    fixed = sorted(set(before["misses"]) - set(after["misses"]))
    broken = sorted(set(after["misses"]) - set(before["misses"]))
    still = sorted(set(before["misses"]) & set(after["misses"]))

    return {
        "before": before["label"],
        "after": after["label"],
        "rows": rows,
        "fixed": fixed,
        "regressed": broken,
        "still_failing": still,
    }


def format_table(results, k=TOP_K, stage="final"):
    """A fixed-width table of one metric block per result."""

    headers = [
        "configuration",
        f"hit@{k}",
        f"recall@{k}",
        f"prec@{k}",
        "mrr",
        "ms",
    ]

    rows = [
        [
            result["label"][:38],
            f"{result['metrics'][stage][f'hit_rate@{k}']:.3f}",
            f"{result['metrics'][stage][f'recall@{k}']:.3f}",
            f"{result['metrics'][stage][f'precision@{k}']:.3f}",
            f"{result['metrics'][stage]['mrr']:.3f}",
            f"{result['latency_ms']['mean']:.0f}",
        ]
        for result in results
    ]

    widths = [
        max(len(str(row[column])) for row in [headers] + rows)
        for column in range(len(headers))
    ]

    def render(values):
        return "  ".join(
            str(value).ljust(widths[index])
            for index, value in enumerate(values)
        )

    lines = [render(headers), "  ".join("-" * width for width in widths)]
    lines.extend(render(row) for row in rows)

    return "\n".join(lines)


def save_results(payload, path):
    """
    Write a run to disk so a later run can be diffed against it.

    `default=str` because the payload can contain dataclasses and numpy
    scalars, and a run that took minutes to produce should not be lost to
    a serialisation error.
    """

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8"
    )

    return path
