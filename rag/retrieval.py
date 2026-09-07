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

import time

import numpy as np
from rank_bm25 import BM25Okapi

from rag.chunk_types import (
    PROVENANCE_FIELDS,
    RetrievedChunk,
    format_pages,
    provenance_of,
    tokenize,
)
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
from rag.filters import SET_FILTERS, build_where, matches_filters
from rag.fusion import mmr_order
from rag.metadata import UNSPECIFIED
from rag.rerankers import get_reranker
from rag.trace_record import _Record, RetrievalTrace

RETRIEVAL_MODES = ("hybrid", "dense", "sparse")


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
