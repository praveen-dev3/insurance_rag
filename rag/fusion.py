"""Candidate re-ordering: Maximal Marginal Relevance.

The other half of "fusion" — Reciprocal Rank Fusion — lives with the
retriever in `rag/retrieval.py: HybridRetriever.fuse`, because it needs
the two ranked lists as they come off the retrievers. The one thing worth
repeating here is *why* RRF and not a score blend, because it is the
mistake the Week 4 brief names by name:

    α·cosine + (1−α)·bm25

looks like a tunable dial and is not one. A cosine distance lives in a
bounded, corpus-dependent range; a BM25 score is unbounded and scales with
document length and corpus statistics. They were never on the same scale,
so averaging them means averaging two different units, and min-max
normalising per query only makes the blend depend on how bad the worst
result happened to be. **RRF fuses RANKS, not scores** — `1/(60 + rank)`,
summed over the lists a chunk appears in — precisely so that no scale has
to be reconciled and there is no α to re-tune per corpus.

MMR, below, is the stage after that.
"""

import numpy as np

from rag.config import MMR_LAMBDA


# ============================================================
# MMR
# ============================================================

# NOT REQUIRED BY W3-W6, and USE_MMR defaults to off — kept to show the
# alternative we rejected, and why, because "we measured it and it lost" is
# a more useful thing for a learner to read than an unused switch.
#
# MMR does exactly what it promises, and on THIS corpus that is not worth
# it. Sweeping λ over the fused candidates (Week 4, cross-encoder off):
#
#   config          hit@3   distinct forms in top-3   p50
#   no MMR          11/12   1.583                     34.4 ms
#   MMR λ=0.9        9/12   2.000                     59.5 ms
#   MMR λ=0.7        7/12   2.417                     55.9 ms
#   MMR λ=0.5        6/12   2.583                     54.7 ms
#
# Diversity rises monotonically as λ falls, and hit-rate collapses with it.
# The reason is that MMR's premise does not hold here: it is built for a
# top-3 that is the same clause repeated across three form editions, and
# this index has one edition of each form, with the structure chunker
# already stamping form and clause on every chunk. The redundancy MMR
# removes had been removed by chunking. What it does instead is push a
# *correct* chunk out of the window to make room for a different form —
# which is exactly the risk the brief warns about, and it happens at every
# λ tested. Turn it on the day multiple editions of one form are indexed.

def mmr_order(query_vector, vectors, lambda_multiplier=MMR_LAMBDA, top_k=None):
    """
    Maximal Marginal Relevance: pick the next item that is relevant to
    the query *and* unlike what has already been picked.

        score(d) = λ · sim(d, q) − (1 − λ) · max sim(d, s)
                                            s ∈ selected

    With overlapping chunks, the top of a similarity ranking is often
    three views of the same paragraph. That wastes the prompt budget on
    one fact; MMR spends it on three.

    Vectors are assumed L2-normalised, so a dot product is the cosine.
    """

    if len(vectors) == 0:
        return []

    # Greedy selection, O(n²) in the candidate count. Fine because the pool
    # is MMR_POOL (10) out of at most RERANK_CANDIDATES (20) — the exact
    # subset-selection problem MMR approximates is NP-hard, and greedy is
    # the standard approximation, not a shortcut taken here.

    top_k = len(vectors) if top_k is None else min(top_k, len(vectors))

    matrix = np.asarray(vectors, dtype=np.float32)
    query = np.asarray(query_vector, dtype=np.float32)

    # Dot products, not a cosine call: both the encoder and the index
    # normalise, so a dot product IS the cosine, and the whole selection
    # collapses into two small matrix multiplies.
    relevance = matrix @ query
    similarity = matrix @ matrix.T

    selected = []
    remaining = list(range(len(matrix)))

    while remaining and len(selected) < top_k:

        if not selected:
            best = max(remaining, key=lambda index: relevance[index])
        else:
            def mmr_score(index):
                redundancy = max(similarity[index][chosen] for chosen in selected)
                return (
                    lambda_multiplier * relevance[index]
                    - (1.0 - lambda_multiplier) * redundancy
                )

            best = max(remaining, key=mmr_score)

        selected.append(best)
        remaining.remove(best)

    return selected
