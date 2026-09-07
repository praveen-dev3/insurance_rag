"""Week 4 Task Set D: label the failures, buy back hit-rate@3 with ONE change.

Two arms over the same 12 questions and the same index:

    BEFORE   dense vectors only
    AFTER    dense + BM25, fused with Reciprocal Rank Fusion (k=60)

Exactly one variable moves. Everything else is pinned and pinned loudly:

  * the chunker is `structure`, fixed in Week 3 and not a variable here;
  * the corpus is the seven documents in eval/corpus/;
  * the cross-encoder is OFF IN BOTH ARMS. It is the other change the
    brief offers, and enabling it alongside fusion would make the delta
    unattributable. It is measured separately at the end, as information,
    not as part of the before/after;
  * the reranker score floor is disabled in both arms, so top-3 always
    holds three candidates and hit-rate@3 is not silently confounded by
    a refusal mechanism;
  * MMR is off in both arms, and is the bonus.

Latency is retrieval only - the time to produce a ranking - because that
is what the change alters. Generation latency is dominated by the LLM and
would bury a 20 ms retrieval difference under 2 s of network.

Usage:
    python tools/run_week4.py              # full run, includes generation
    python tools/run_week4.py retrieval    # skip the LLM labelling pass
"""

import json
import statistics
import time
from collections import Counter
from pathlib import Path

from _runner import chroma_client, make_saver, positional_stage

from build_w4_golden import COLLECTION, build_index

from rag.diagnostics import TASK_LABELS, classify_by_chunk_id
from rag.evaluation import latency_summary
from rag.generation import generate_answer, is_generation_error
from rag.indexing import open_collection
from rag.rerankers import get_reranker
from rag.retrieval import HybridRetriever

GOLDEN_SET = Path("eval/golden_set.jsonl")
OUTPUT_DIR = Path("eval/results/week4")

K = 3

# Disables the score floor. Both arms get the same value, so it is not a
# variable; it is removed from the experiment rather than held constant
# at a value that could drop a candidate in one arm and not the other.
NO_FLOOR = -1e9


def common_options():
    """Everything held fixed across both arms."""

    return {
        "top_k": K,
        "use_mmr": False,
        "min_score": NO_FLOOR,
        "reranker": get_reranker("none"),
    }


ARMS = {
    "before": {"label": "dense only", "mode": "dense"},
    "after": {"label": "dense + BM25, RRF k=60", "mode": "hybrid"},
}


def load_cases():

    return [
        json.loads(line)
        for line in GOLDEN_SET.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


# ============================================================
# ONE ARM
# ============================================================

def run_arm(retriever, cases, arm, generate=True):
    """Retrieve (timed), answer, and label every question."""

    options = common_options()
    options["mode"] = ARMS[arm]["mode"]

    # One throwaway query so model loading and first-call overhead are not
    # charged to the first question's latency.
    retriever.search("warm up the encoders", **options)

    rows = []
    latencies = []

    for case in cases:

        started = time.perf_counter()
        chunks, trace = retriever.search(case["question"], **options)
        elapsed = (time.perf_counter() - started) * 1000

        latencies.append(elapsed)

        top = trace.final[:K]
        top_ids = [chunk.id for chunk in top]

        hit = case["chunk_id"] in top_ids
        rank = top_ids.index(case["chunk_id"]) + 1 if hit else None

        answer = None

        if generate:
            answer = generate_answer(case["question"], chunks)

            if is_generation_error(answer):
                raise RuntimeError(
                    f"Generation failed on {case['id']}: {answer}"
                )

        diagnosis = classify_by_chunk_id(
            trace,
            answer,
            case["chunk_id"],
            k=K,
            answerable=case["answerable"],
            answer_contains=case["answer_contains"] if generate else [],
        )

        rows.append({
            "id": case["id"],
            "question": case["question"],
            "has_exact_token": case["has_exact_token"],
            "expected_chunk_id": case["chunk_id"],
            "expected_form": case["form_number"],
            "expected_clause": case["clause"],
            "hit_at_3": hit,
            "rank": rank,
            "latency_ms": round(elapsed, 1),
            "label": diagnosis.label,
            "task_label": diagnosis.task_label,
            "evidence": diagnosis.reason,
            "diagnosis_evidence": diagnosis.evidence,
            "answer": answer,
            "top_3": [
                {
                    "rank": position,
                    "chunk_id": chunk.id,
                    "form_number": chunk.form_number,
                    "clause": chunk.clause_label,
                    "rrf_score": round(chunk.rrf_score, 6),
                    "dense_rank": chunk.dense_rank,
                    "sparse_rank": chunk.sparse_rank,
                    "is_expected": chunk.id == case["chunk_id"],
                }
                for position, chunk in enumerate(top, start=1)
            ],
        })

    hits = sum(1 for row in rows if row["hit_at_3"])

    return {
        "arm": arm,
        "label": ARMS[arm]["label"],
        "mode": ARMS[arm]["mode"],
        "k": K,
        "hit_at_3": hits,
        "of": len(rows),
        "hit_rate_at_3": round(hits / len(rows), 4),
        "latency_ms": latency_summary(latencies),
        "tally": dict(Counter(row["task_label"] for row in rows)),
        "rows": rows,
    }


# ============================================================
# BONUS: MMR
# ============================================================

def top3_diversity(rows):
    """
    How much of the top-3 is actually different material?

    Two numbers, because they fail differently. Distinct forms catches
    "three editions of the same exclusion"; distinct clauses catches
    "three consecutive slices of one table", which is the failure mode
    the structure chunker makes more likely, not less.
    """

    forms = [len({item["form_number"] for item in row["top_3"]}) for row in rows]
    clauses = [
        len({(item["form_number"], item["clause"]) for item in row["top_3"]})
        for row in rows
    ]

    return {
        "distinct_forms_in_top3": round(statistics.fmean(forms), 3),
        "distinct_clauses_in_top3": round(statistics.fmean(clauses), 3),
    }


def run_mmr_sweep(retriever, cases, lambdas=(0.3, 0.5, 0.7, 0.9)):
    """MMR over the fused candidate list, at several lambdas."""

    results = []

    for value in lambdas:

        options = common_options()
        options["mode"] = "hybrid"
        options["use_mmr"] = True
        options["mmr_lambda"] = value

        retriever.search("warm up", **options)

        rows = []
        latencies = []

        for case in cases:

            started = time.perf_counter()
            _, trace = retriever.search(case["question"], **options)
            latencies.append((time.perf_counter() - started) * 1000)

            top = trace.final[:K]
            top_ids = [chunk.id for chunk in top]

            rows.append({
                "id": case["id"],
                "hit_at_3": case["chunk_id"] in top_ids,
                "top_3": [
                    {
                        "chunk_id": chunk.id,
                        "form_number": chunk.form_number,
                        "clause": chunk.clause_label,
                    }
                    for chunk in top
                ],
            })

        hits = sum(1 for row in rows if row["hit_at_3"])

        results.append({
            "mmr_lambda": value,
            "hit_at_3": hits,
            "of": len(rows),
            "latency_ms": latency_summary(latencies),
            "diversity": top3_diversity(rows),
            "misses": [row["id"] for row in rows if not row["hit_at_3"]],
        })

        print(
            f"  lambda={value}  hit@3={hits}/{len(rows)}  "
            f"forms/top3={results[-1]['diversity']['distinct_forms_in_top3']}  "
            f"clauses/top3={results[-1]['diversity']['distinct_clauses_in_top3']}  "
            f"p50={results[-1]['latency_ms']['p50']}ms"
        )

    return results


# ============================================================
# THE OTHER CHANGE, MEASURED BUT NOT SHIPPED IN THIS DELTA
# ============================================================

def run_cross_encoder_arm(retriever, cases):
    """
    Hybrid + cross-encoder, for information only.

    Reported separately and explicitly NOT folded into the before/after,
    because a delta produced by two simultaneous changes says nothing
    about which one earned it.
    """

    options = common_options()
    options["mode"] = "hybrid"
    options["reranker"] = get_reranker("ms-marco")

    retriever.search("warm up", **options)

    rows = []
    latencies = []

    for case in cases:

        started = time.perf_counter()
        _, trace = retriever.search(case["question"], **options)
        latencies.append((time.perf_counter() - started) * 1000)

        top_ids = [chunk.id for chunk in trace.final[:K]]

        rows.append({
            "id": case["id"],
            "hit_at_3": case["chunk_id"] in top_ids,
        })

    hits = sum(1 for row in rows if row["hit_at_3"])

    return {
        "label": "dense + BM25 + cross-encoder",
        "hit_at_3": hits,
        "of": len(rows),
        "latency_ms": latency_summary(latencies),
        "misses": [row["id"] for row in rows if not row["hit_at_3"]],
    }


# ============================================================

def measure_latency(retriever, cases, repeats=7):
    """
    Retrieval latency for both arms, repeated and interleaved.

    A single pass over 12 questions gives 12 samples per arm, and on a
    laptop those swing by 2x between runs on background load alone - the
    first draft of this experiment reported p50 33.6ms and p50 59.1ms for
    the *same* configuration on two consecutive runs. Reporting either as
    "the" latency would be reporting noise as a result.

    Two mitigations: repeat, and interleave. Interleaving matters more -
    running arm A's 84 samples and then arm B's 84 samples charges any
    drift in machine load to whichever arm ran during it, whereas
    alternating question by question splits that drift across both.
    """

    samples = {arm: [] for arm in ARMS}

    for arm in ARMS:
        options = common_options()
        options["mode"] = ARMS[arm]["mode"]
        retriever.search("warm up the encoders", **options)

    for _ in range(repeats):

        for case in cases:

            for arm in ARMS:

                options = common_options()
                options["mode"] = ARMS[arm]["mode"]

                started = time.perf_counter()
                retriever.search(case["question"], **options)
                samples[arm].append((time.perf_counter() - started) * 1000)

    return {
        arm: {
            **latency_summary(values),
            "repeats": repeats,
            "questions": len(cases),
        }
        for arm, values in samples.items()
    }


def compare_arms(before, after):
    """Per-question fixed / unfixed / still-broken / regressed."""

    after_by_id = {row["id"]: row for row in after["rows"]}

    verdicts = []

    for row in before["rows"]:

        later = after_by_id[row["id"]]

        if not row["hit_at_3"] and later["hit_at_3"]:
            verdict = "FIXED"
        elif not row["hit_at_3"] and not later["hit_at_3"]:
            verdict = "STILL BROKEN"
        elif row["hit_at_3"] and not later["hit_at_3"]:
            verdict = "REGRESSED"
        else:
            verdict = "already passing"

        verdicts.append({
            "id": row["id"],
            "has_exact_token": row["has_exact_token"],
            "before_rank": row["rank"],
            "after_rank": later["rank"],
            "before_label": row["task_label"],
            "after_label": later["task_label"],
            "verdict": verdict,
        })

    return verdicts


save = make_saver(OUTPUT_DIR)


def main():

    stage = positional_stage()
    generate = stage != "retrieval"

    cases = load_cases()

    print(
        f"{len(cases)} questions, "
        f"{sum(1 for c in cases if c['has_exact_token'])} with an exact token."
    )

    client = chroma_client()

    try:
        collection = open_collection(client, COLLECTION)
        print(f"Using existing '{COLLECTION}' ({collection.count()} chunks).")
    except Exception:
        collection = build_index(client)

    retriever = HybridRetriever(collection)

    print("\n=== BEFORE: dense only ===")
    before = run_arm(retriever, cases, "before", generate=generate)

    for row in before["rows"]:
        print(
            f"  {row['id']}  hit@3={'Y' if row['hit_at_3'] else 'N'}  "
            f"rank={row['rank'] or '-'}  {row['task_label']:<14} "
            f"{row['latency_ms']:>6.1f}ms"
        )

    print(
        f"  => {before['hit_at_3']}/{before['of']}  "
        f"p50={before['latency_ms']['p50']}ms  tally={before['tally']}"
    )

    print("\n=== AFTER: dense + BM25, RRF k=60 (ONE change) ===")
    after = run_arm(retriever, cases, "after", generate=generate)

    for row in after["rows"]:
        print(
            f"  {row['id']}  hit@3={'Y' if row['hit_at_3'] else 'N'}  "
            f"rank={row['rank'] or '-'}  {row['task_label']:<14} "
            f"{row['latency_ms']:>6.1f}ms"
        )

    print(
        f"  => {after['hit_at_3']}/{after['of']}  "
        f"p50={after['latency_ms']['p50']}ms  tally={after['tally']}"
    )

    print("\n=== Latency, interleaved and repeated ===")
    latency = measure_latency(retriever, cases)

    for arm, stats in latency.items():
        print(
            f"  {ARMS[arm]['label']:<24} p50={stats['p50']:>7.1f}ms  "
            f"mean={stats['mean']:>7.1f}ms  p95={stats['p95']:>7.1f}ms  "
            f"n={stats['n']}"
        )

    before["latency_measured"] = latency["before"]
    after["latency_measured"] = latency["after"]

    verdicts = compare_arms(before, after)

    print("\n=== Per-question verdict ===")
    for verdict in verdicts:
        print(
            f"  {verdict['id']}  {'[exact]' if verdict['has_exact_token'] else '       '}  "
            f"{str(verdict['before_rank'] or '-'):>3} -> "
            f"{str(verdict['after_rank'] or '-'):<3}  {verdict['verdict']}"
        )

    print("\n=== BONUS: MMR over the fused list ===")
    mmr = run_mmr_sweep(retriever, cases)

    print("\n=== For information only: + cross-encoder (NOT the shipped delta) ===")
    cross = run_cross_encoder_arm(retriever, cases)
    print(
        f"  hit@3={cross['hit_at_3']}/{cross['of']}  "
        f"p50={cross['latency_ms']['p50']}ms  misses={cross['misses']}"
    )

    save({
        "k": K,
        "before": before,
        "after": after,
        "verdicts": verdicts,
        "mmr_sweep": mmr,
        "cross_encoder_reference": cross,
        "baseline_diversity": top3_diversity(after["rows"]),
    }, "week4.json")

    print("\nSummary")
    print("-------")
    print(
        f"  hit-rate@3   {before['hit_at_3']}/12 -> {after['hit_at_3']}/12"
    )
    print(
        f"  p50 latency  {latency['before']['p50']}ms -> "
        f"{latency['after']['p50']}ms  "
        f"({latency['before']['n']} samples per arm)"
    )


if __name__ == "__main__":
    main()
