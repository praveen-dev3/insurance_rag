"""The stored-chunk record and the per-stage retrieval trace.

Two similar-looking types live one file apart, and the difference is the
point. `_Record` is a chunk as the index holds it — no query has touched
it, so it has no scores and no ranks. `RetrievedChunk` (in
rag/chunk_types.py) is that chunk *as a candidate for one question*, and
carries every score the pipeline gave it. Merging them would mean a stored
row with mutable per-query score fields hanging off it, which is how one
question's rerank score ends up reported for another.
"""

from dataclasses import dataclass, field

from rag.metadata import UNSPECIFIED


# ============================================================
# STORED RECORD
# ============================================================

@dataclass
class _Record:
    """A chunk as stored in the index, before any query touches it."""

    id: str
    text: str
    source: str
    page_start: int
    page_end: int
    tokens: list = field(default_factory=list)
    vector: object = None

    source_file: str = UNSPECIFIED
    form_number: str = UNSPECIFIED
    policy_line: str = UNSPECIFIED
    edition_date: str = UNSPECIFIED
    clause: str = UNSPECIFIED
    clause_label: str = UNSPECIFIED
    document_title: str = UNSPECIFIED
    exclusion_codes: list = field(default_factory=list)


# ============================================================
# TRACE
# ============================================================

@dataclass
class RetrievalTrace:
    """
    What each stage saw and what it passed on.

    This is the raw material for the inspection view and for telling a
    retrieval failure apart from a generation failure: if the right chunk
    is absent here, no amount of prompt work will save the answer.

    A structured record of the candidate lists rather than log lines,
    because the trace has to be *queried*: the evaluator computes
    hit-rate@k per stage from `fused`, `reranked` and `final` separately,
    which is what turns "the reranker dropped the answer fusion had found"
    into a countable outcome rather than something noticed by eye. Log
    output cannot be diffed between two runs; this can.

    `dropped_below_floor` is kept apart from the stage lists on purpose. A
    chunk the relevance floor rejected is the mechanism behind every
    "I don't know", so a refusal has to be explainable as "these three
    candidates scored below the bar" rather than as an empty result.
    """

    question: str = ""
    search_query: str = ""
    dense_query: str = ""
    mode: str = "hybrid"
    filters: dict = field(default_factory=dict)
    config: dict = field(default_factory=dict)
    timings_ms: dict = field(default_factory=dict)

    dense: list = field(default_factory=list)
    sparse: list = field(default_factory=list)
    fused: list = field(default_factory=list)
    mmr: list = field(default_factory=list)
    reranked: list = field(default_factory=list)
    final: list = field(default_factory=list)

    dropped_below_floor: list = field(default_factory=list)

    def to_dict(self):

        def brief(chunks):
            return [chunk.to_dict() for chunk in chunks]

        return {
            "question": self.question,
            "search_query": self.search_query,
            "dense_query": self.dense_query,
            "mode": self.mode,
            "filters": self.filters,
            "config": self.config,
            "timings_ms": self.timings_ms,
            "stages": {
                "dense": brief(self.dense),
                "sparse": brief(self.sparse),
                "fused": brief(self.fused),
                "mmr": brief(self.mmr),
                "reranked": brief(self.reranked),
                "final": brief(self.final),
            },
            "dropped_below_floor": brief(self.dropped_below_floor),
        }
