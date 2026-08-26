"""Hybrid retrieval: dense vectors + BM25, fused with RRF, optionally
diversified with MMR, then reranked.

    query
      │
      ├── dense  (embeddings, HNSW)  ─┐
      │                               ├── RRF fusion ── MMR ── rerank ── top-k
      └── sparse (BM25 Okapi)        ─┘

Dense search alone misses exact policy vocabulary ("Section II-1(ii)",
"TN06BJ2206", "co-insurance"); BM25 alone misses paraphrase. Fusing the
ranks rather than the scores avoids having to reconcile a cosine
distance with a BM25 score, which live on unrelated scales.

Every stage records what it saw and what it passed on, into a
RetrievalTrace. That trace is what makes a retrieval failure diagnosable
rather than merely annoying.
"""

import re
import time
from dataclasses import dataclass, field

import numpy as np
from rank_bm25 import BM25Okapi

from rag.config import (
    DENSE_TOP_K,
    MMR_LAMBDA,
    MMR_POOL,
    RERANK_CANDIDATES,
    RRF_K,
    SPARSE_TOP_K,
    TOP_K,
    USE_MMR,
)
from rag.embeddings import get_embedder
from rag.metadata import UNSPECIFIED
from rag.rerankers import get_reranker

RETRIEVAL_MODES = ("hybrid", "dense", "sparse")


# ============================================================
# BM25 TOKENISATION
# ============================================================

# Keeps alphanumerics together so "4b", "155" and "tn06bj2206" survive,
# and splits on everything else.
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")

# Only the highest-frequency function words. BM25's IDF already discounts
# common terms; this list exists so that a question like "what is the
# waiting period" is not dominated by its first three words.
_STOPWORDS = frozenset("""
a an the and or of to in on for is are was were be been being
this that these those it its as at by with from if then than
what which who whom whose when where why how do does did done
i you he she they we my your our their there here about into
""".split())


def tokenize(text):
    """Lowercase, split on non-alphanumerics, drop stopwords."""

    tokens = _TOKEN_PATTERN.findall(text.lower())

    return [token for token in tokens if token not in _STOPWORDS]


# ============================================================
# CHUNK RECORDS
# ============================================================

# The four provenance fields the ingest is required to carry, plus the
# citation extras. Pulled out so the three places that turn a stored row
# back into an object cannot drift apart on what a chunk knows about
# itself.
PROVENANCE_FIELDS = (
    "source_file",
    "form_number",
    "policy_line",
    "edition_date",
    "clause",
    "clause_label",
    "document_title",
)


def provenance_of(metadata, source):
    """
    Read the provenance fields off a stored metadata dict.

    `source_file` falls back to the chunk's source rather than to
    UNSPECIFIED: an unattributable chunk is the one failure mode the
    ingest is supposed to make unreachable, so it is not reintroduced on
    the read path.
    """

    metadata = metadata or {}

    fields = {
        field: metadata.get(field, UNSPECIFIED)
        for field in PROVENANCE_FIELDS
    }

    fields["source_file"] = metadata.get("source_file") or source

    codes = metadata.get("exclusion_codes") or ""

    fields["exclusion_codes"] = [
        code for code in codes.split(",") if code
    ]

    return fields


@dataclass
class RetrievedChunk:
    """
    One candidate chunk plus every score that touched it.

    Keeping the per-stage ranks means the UI can show *why* a chunk
    surfaced — vector match, keyword match, or both — and where it was
    dropped if it did not survive.
    """

    id: str
    text: str
    source: str
    page_start: int
    page_end: int

    source_file: str = UNSPECIFIED
    form_number: str = UNSPECIFIED
    policy_line: str = UNSPECIFIED
    edition_date: str = UNSPECIFIED
    clause: str = UNSPECIFIED
    clause_label: str = UNSPECIFIED
    document_title: str = UNSPECIFIED
    exclusion_codes: list = field(default_factory=list)

    distance: float | None = None
    dense_rank: int | None = None

    bm25_score: float | None = None
    sparse_rank: int | None = None

    rrf_score: float = 0.0
    fused_rank: int | None = None

    mmr_rank: int | None = None
    rerank_score: float | None = None
    final_rank: int | None = None

    @property
    def cross_score(self):
        """Backwards-compatible alias for the reranker's score."""

        return self.rerank_score

    @property
    def matched_by(self):

        matched = []

        if self.dense_rank is not None:
            matched.append("dense")

        if self.sparse_rank is not None:
            matched.append("bm25")

        return matched

    @property
    def citation(self):
        """
        The reference an answer prints for this chunk.

        Every component is read from the index, never composed by the
        model: the chunk_id resolves to exactly one stored row, and the
        form number and clause are the ones that row was ingested with.
        A citation is therefore checkable by lookup rather than by
        rereading the answer and hoping.
        """

        parts = []

        if self.form_number != UNSPECIFIED:
            parts.append(f"{self.form_number} ed. {self.edition_date}")
        else:
            parts.append(self.source_file)

        if self.clause_label != UNSPECIFIED:
            parts.append(self.clause_label)

        parts.append(f"p. {format_pages(self)}")
        parts.append(f"chunk_id={self.id}")

        return ", ".join(parts)

    def to_dict(self):

        return {
            "id": self.id,
            "text": self.text,
            "source": self.source,
            "source_file": self.source_file,
            "form_number": self.form_number,
            "policy_line": self.policy_line,
            "edition_date": self.edition_date,
            "clause": self.clause,
            "clause_label": self.clause_label,
            "document_title": self.document_title,
            "exclusion_codes": self.exclusion_codes,
            "citation": self.citation,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "pages": format_pages(self),
            "distance": self.distance,
            "dense_rank": self.dense_rank,
            "bm25_score": self.bm25_score,
            "sparse_rank": self.sparse_rank,
            "rrf_score": self.rrf_score,
            "fused_rank": self.fused_rank,
            "mmr_rank": self.mmr_rank,
            "rerank_score": self.rerank_score,
            "cross_score": self.rerank_score,
            "final_rank": self.final_rank,
            "matched_by": self.matched_by,
        }


def format_pages(chunk):
    """
    Human-readable page reference for a chunk.

    Accepts a RetrievedChunk or the plain dicts used during indexing.
    """

    if isinstance(chunk, dict):
        page_start = chunk["page_start"]
        page_end = chunk["page_end"]
    else:
        page_start = chunk.page_start
        page_end = chunk.page_end

    if page_start == page_end:
        return str(page_start)

    return f"{page_start}-{page_end}"


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


# ============================================================
# METADATA FILTERING
# ============================================================

# Metadata fields that accept a list of accepted values. All are exact
# string matches: a policy line is drawn from a controlled vocabulary, not
# free text, so substring matching would only create false positives
# ("motor" matching "motorhome").
SET_FILTERS = {
    "sources": "source",
    "policy_lines": "policy_line",
    "form_numbers": "form_number",
    "edition_dates": "edition_date",
}


def build_where(filters):
    """
    Translate a filter dict into a Chroma `where` clause.

    Supported keys: `sources`, `policy_lines`, `form_numbers` and
    `edition_dates` (each a list of accepted values), plus `page_min` and
    `page_max`. Page bounds match any chunk whose page range *overlaps*
    the requested window, so a chunk spanning pages 3-4 is returned for
    a "page 4 only" filter.

    Filtering on policy_line is not a convenience. The exclusion codes are
    scoped per line - E-71 on the dwelling fire line and E-17 on the
    homeowners line say nearly the same thing in nearly the same words,
    and their dispositions differ. An unfiltered search over both lines
    retrieves the wrong form's answer with high confidence, which is worse
    than retrieving nothing.
    """

    if not filters:
        return None

    clauses = []

    for key, field_name in SET_FILTERS.items():

        values = filters.get(key)

        if values:
            clauses.append({field_name: {"$in": list(values)}})

    if filters.get("page_min") is not None:
        clauses.append({"page_end": {"$gte": int(filters["page_min"])}})

    if filters.get("page_max") is not None:
        clauses.append({"page_start": {"$lte": int(filters["page_max"])}})

    if not clauses:
        return None

    if len(clauses) == 1:
        return clauses[0]

    return {"$and": clauses}


def matches_filters(record, filters):
    """
    The same predicate as build_where, for the in-memory BM25 side.

    Kept deliberately parallel to build_where. A filter applied to the
    dense half of a hybrid search but not the sparse half does not fail
    loudly - it quietly leaks the filtered-out documents back in through
    fusion, and the result looks like a retrieval quality problem rather
    than a filtering bug.
    """

    if not filters:
        return True

    for key, field_name in SET_FILTERS.items():

        values = filters.get(key)

        if values and getattr(record, field_name, None) not in values:
            return False

    page_min = filters.get("page_min")

    if page_min is not None and record.page_end < int(page_min):
        return False

    page_max = filters.get("page_max")

    if page_max is not None and record.page_start > int(page_max):
        return False

    return True


# ============================================================
# MMR
# ============================================================

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

    top_k = len(vectors) if top_k is None else min(top_k, len(vectors))

    matrix = np.asarray(vectors, dtype=np.float32)
    query = np.asarray(query_vector, dtype=np.float32)

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


# ============================================================
# HYBRID RETRIEVER
# ============================================================

class HybridRetriever:
    """
    Dense + sparse retrieval over one Chroma collection.

    The BM25 index is built in memory from the chunks already persisted
    in Chroma, so there is no second store to keep in sync — the vector
    index remains the single source of truth for what is indexed.
    """

    def __init__(self, collection, embedder=None, reranker=None):

        self.collection = collection
        self.embedder = embedder or get_embedder()
        self.reranker = reranker or get_reranker()

        self.records = {}
        self._order = []
        self._bm25 = None
        self._matrix = None

        self._build_sparse_index()

    # --------------------------------------------------------
    # Index construction
    # --------------------------------------------------------

    def _build_sparse_index(self):

        stored = self.collection.get(
            include=["documents", "metadatas", "embeddings"]
        )

        ids = stored.get("ids") or []
        documents = stored.get("documents") or []
        metadatas = stored.get("metadatas") or []
        embeddings = stored.get("embeddings")

        if embeddings is None:
            embeddings = []

        self.records = {}
        self._order = []

        for position, chunk_id in enumerate(ids):

            metadata = (
                metadatas[position] if position < len(metadatas) else {}
            ) or {}

            text = (
                documents[position] if position < len(documents) else ""
            ) or ""

            vector = (
                np.asarray(embeddings[position], dtype=np.float32)
                if position < len(embeddings)
                else None
            )

            source = metadata.get("source", "unknown")

            record = _Record(
                id=chunk_id,
                text=text,
                source=source,
                page_start=metadata.get("page_start", 0),
                page_end=metadata.get("page_end", 0),
                tokens=tokenize(text),
                vector=vector,
                **provenance_of(metadata, source),
            )

            self.records[chunk_id] = record
            self._order.append(chunk_id)

        corpus = [self.records[chunk_id].tokens for chunk_id in self._order]

        # BM25Okapi divides by the average document length, which is
        # undefined for an empty corpus.
        self._bm25 = BM25Okapi(corpus) if corpus else None

        print(f"BM25 index built over {len(self._order)} chunks.")

    def refresh(self):
        """Rebuild the sparse index after the corpus was re-indexed."""

        self._build_sparse_index()

    @property
    def size(self):
        return len(self._order)

    def sources(self):
        """Distinct document names in the index, for the filter UI."""

        return sorted({record.source for record in self.records.values()})

    def policy_lines(self):
        """Distinct policy lines in the index, for the filter UI."""

        return sorted({
            record.policy_line
            for record in self.records.values()
            if record.policy_line != UNSPECIFIED
        })

    def forms(self):
        """Distinct form numbers in the index, newest edition first."""

        forms = {
            (record.form_number, record.edition_date)
            for record in self.records.values()
            if record.form_number != UNSPECIFIED
        }

        return [
            {"form_number": form, "edition_date": edition}
            for form, edition in sorted(forms)
        ]

    def page_range(self):

        if not self.records:
            return (0, 0)

        return (
            min(record.page_start for record in self.records.values()),
            max(record.page_end for record in self.records.values()),
        )

    def _vector_for(self, chunk_id):
        """Fall back to encoding on the fly if the store had no vector."""

        record = self.records[chunk_id]

        if record.vector is None:
            record.vector = self.embedder.embed_passages([record.text])[0]

        return record.vector

    # --------------------------------------------------------
    # Stage 1a: dense retrieval
    # --------------------------------------------------------

    def dense_search(self, query_text, top_k=DENSE_TOP_K, filters=None):
        """
        Semantic nearest neighbours.

        The query is embedded here, with the model's query prefix, rather
        than handed to Chroma as text — see rag/embeddings.py for why
        that distinction matters.
        """

        if not self._order:
            return []

        query_vector = self.embedder.embed_query(query_text)

        results = self.collection.query(
            query_embeddings=[query_vector.tolist()],
            n_results=min(top_k, len(self._order)),
            where=build_where(filters),
        )

        ids = (results.get("ids") or [[]])[0]
        distances = (results.get("distances") or [[]])[0]
        documents = (results.get("documents") or [[]])[0]
        metadatas = (results.get("metadatas") or [[]])[0]

        hits = []

        for position, chunk_id in enumerate(ids):

            # A chunk added to Chroma after this retriever was built is
            # still a legitimate hit; adopt it rather than dropping it.
            if chunk_id not in self.records:

                metadata = (
                    metadatas[position] if position < len(metadatas) else {}
                ) or {}

                text = (
                    documents[position] if position < len(documents) else ""
                ) or ""

                source = metadata.get("source", "unknown")

                self.records[chunk_id] = _Record(
                    id=chunk_id,
                    text=text,
                    source=source,
                    page_start=metadata.get("page_start", 0),
                    page_end=metadata.get("page_end", 0),
                    tokens=tokenize(text),
                    **provenance_of(metadata, source),
                )

            distance = (
                distances[position] if position < len(distances) else None
            )

            hits.append((chunk_id, distance))

        return hits

    # --------------------------------------------------------
    # Stage 1b: sparse retrieval
    # --------------------------------------------------------

    def sparse_search(self, question, top_k=SPARSE_TOP_K, filters=None):
        """
        BM25 keyword match.

        Zero-scoring chunks are dropped: a chunk sharing no query term
        with the question is not a keyword hit and must not consume a
        fusion slot just because the list was short.
        """

        if self._bm25 is None:
            return []

        query_tokens = tokenize(question)

        if not query_tokens:
            return []

        scores = self._bm25.get_scores(query_tokens)

        ranked = sorted(
            enumerate(scores),
            key=lambda pair: pair[1],
            reverse=True
        )

        hits = []

        for position, score in ranked:

            if score <= 0 or len(hits) >= top_k:
                break

            chunk_id = self._order[position]

            if not matches_filters(self.records[chunk_id], filters):
                continue

            hits.append((chunk_id, float(score)))

        return hits

    # --------------------------------------------------------
    # Stage 2: reciprocal rank fusion
    # --------------------------------------------------------

    def fuse(self, dense_hits, sparse_hits, limit=RERANK_CANDIDATES):
        """
        Merge two ranked lists into one.

        RRF scores a chunk as the sum of 1 / (RRF_K + rank) over the
        lists it appears in, so a chunk ranked well by both retrievers
        outranks one that only a single retriever loved. Ranks are
        1-based.
        """

        candidates = {}

        def candidate_for(chunk_id):

            if chunk_id not in candidates:

                record = self.records[chunk_id]

                candidates[chunk_id] = RetrievedChunk(
                    id=record.id,
                    text=record.text,
                    source=record.source,
                    page_start=record.page_start,
                    page_end=record.page_end,
                    source_file=record.source_file,
                    form_number=record.form_number,
                    policy_line=record.policy_line,
                    edition_date=record.edition_date,
                    clause=record.clause,
                    clause_label=record.clause_label,
                    document_title=record.document_title,
                    exclusion_codes=list(record.exclusion_codes),
                )

            return candidates[chunk_id]

        for rank, (chunk_id, distance) in enumerate(dense_hits, start=1):

            candidate = candidate_for(chunk_id)
            candidate.distance = distance
            candidate.dense_rank = rank
            candidate.rrf_score += 1.0 / (RRF_K + rank)

        for rank, (chunk_id, score) in enumerate(sparse_hits, start=1):

            candidate = candidate_for(chunk_id)
            candidate.bm25_score = score
            candidate.sparse_rank = rank
            candidate.rrf_score += 1.0 / (RRF_K + rank)

        fused = sorted(
            candidates.values(),
            key=lambda chunk: chunk.rrf_score,
            reverse=True
        )

        for rank, chunk in enumerate(fused, start=1):
            chunk.fused_rank = rank

        return fused[:limit]

    # --------------------------------------------------------
    # Stage 3: MMR
    # --------------------------------------------------------

    def diversify(self, query_text, candidates, pool=MMR_POOL,
                  lambda_multiplier=MMR_LAMBDA):
        """
        Re-order the fused candidates with MMR.

        Candidate vectors are read back from the index rather than
        recomputed — they were stored at indexing time, so diversity
        costs one query encode plus some dot products, not a full
        re-encode of the shortlist.
        """

        if not candidates:
            return []

        query_vector = self.embedder.embed_query(query_text)

        vectors = [self._vector_for(chunk.id) for chunk in candidates]

        order = mmr_order(
            query_vector,
            vectors,
            lambda_multiplier=lambda_multiplier,
            top_k=pool
        )

        selected = []

        for rank, index in enumerate(order, start=1):
            candidates[index].mmr_rank = rank
            selected.append(candidates[index])

        return selected

    # --------------------------------------------------------
    # Stage 4: reranking
    # --------------------------------------------------------

    def rerank(self, question, candidates, top_k=TOP_K, min_score=None,
               reranker=None):
        """
        Rescore candidates with the reranker and keep the best.

        Returns (kept, dropped) so the caller can distinguish "nothing
        was relevant" from "nothing was retrieved" — different failures
        with different fixes.
        """

        if not candidates:
            return [], []

        reranker = reranker or self.reranker

        scores = reranker.score(question, [chunk.text for chunk in candidates])

        for chunk, score in zip(candidates, scores):
            chunk.rerank_score = float(score)

        ranked = sorted(
            candidates,
            key=lambda chunk: chunk.rerank_score,
            reverse=True
        )

        floor = reranker.min_score if min_score is None else min_score

        selected = ranked[:top_k]

        if floor is None:
            kept, dropped = selected, []
        else:
            kept = [chunk for chunk in selected if chunk.rerank_score >= floor]
            dropped = [chunk for chunk in selected if chunk.rerank_score < floor]

        for rank, chunk in enumerate(kept, start=1):
            chunk.final_rank = rank

        return kept, dropped

    # --------------------------------------------------------
    # Full pipeline
    # --------------------------------------------------------

    def search(self, question, mode="hybrid", top_k=TOP_K, filters=None,
               search_query=None, dense_query=None, use_mmr=None,
               mmr_lambda=MMR_LAMBDA, mmr_pool=MMR_POOL, min_score=None,
               reranker=None):
        """
        Run the whole pipeline and return (chunks, trace).
        """

        if mode not in RETRIEVAL_MODES:
            raise ValueError(
                f"Unknown retrieval mode '{mode}'. "
                f"Expected one of {RETRIEVAL_MODES}."
            )

        use_mmr = USE_MMR if use_mmr is None else use_mmr
        reranker = reranker or self.reranker

        search_query = search_query or question
        dense_query = dense_query or search_query

        trace = RetrievalTrace(
            question=question,
            search_query=search_query,
            dense_query=dense_query,
            mode=mode,
            filters=filters or {},
            config={
                "top_k": top_k,
                "dense_top_k": DENSE_TOP_K,
                "sparse_top_k": SPARSE_TOP_K,
                "rrf_k": RRF_K,
                "rerank_candidates": RERANK_CANDIDATES,
                "embedding_model": self.embedder.key,
                "reranker": reranker.key,
                "use_mmr": bool(use_mmr),
                "mmr_lambda": mmr_lambda,
                "mmr_pool": mmr_pool,
            },
        )

        started = time.perf_counter()

        dense_hits = (
            self.dense_search(dense_query, filters=filters)
            if mode in ("hybrid", "dense")
            else []
        )

        trace.timings_ms["dense"] = round(
            (time.perf_counter() - started) * 1000, 1
        )

        started = time.perf_counter()

        sparse_hits = (
            self.sparse_search(search_query, filters=filters)
            if mode in ("hybrid", "sparse")
            else []
        )

        trace.timings_ms["sparse"] = round(
            (time.perf_counter() - started) * 1000, 1
        )

        fused = self.fuse(dense_hits, sparse_hits)

        trace.dense = [
            chunk for chunk in fused if chunk.dense_rank is not None
        ]
        trace.sparse = [
            chunk for chunk in fused if chunk.sparse_rank is not None
        ]
        trace.fused = fused

        candidates = fused

        if use_mmr and fused:

            started = time.perf_counter()

            candidates = self.diversify(
                dense_query,
                fused,
                pool=max(mmr_pool, top_k),
                lambda_multiplier=mmr_lambda
            )

            trace.timings_ms["mmr"] = round(
                (time.perf_counter() - started) * 1000, 1
            )

            trace.mmr = candidates

        started = time.perf_counter()

        kept, dropped = self.rerank(
            search_query,
            candidates,
            top_k=top_k,
            min_score=min_score,
            reranker=reranker
        )

        trace.timings_ms["rerank"] = round(
            (time.perf_counter() - started) * 1000, 1
        )

        trace.reranked = sorted(
            candidates,
            key=lambda chunk: (
                chunk.rerank_score
                if chunk.rerank_score is not None
                else float("-inf")
            ),
            reverse=True
        )

        trace.final = kept
        trace.dropped_below_floor = dropped

        return kept, trace
