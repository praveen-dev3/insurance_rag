"""The facade the CLI, the HTTP server and the evaluator all talk to."""

import threading

import chromadb

from rag.chunking import CHUNK_STRATEGIES
from rag.config import (
    CHROMA_PATH,
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    CHUNK_STRATEGY,
    DEFAULT_MODE,
    EMBEDDING_MODEL,
    LLM_MODEL,
    MIN_RERANK_SCORE,
    MMR_LAMBDA,
    MMR_POOL,
    RERANKER,
    TOP_K,
    USE_HYDE,
    USE_MMR,
    USE_QUERY_REWRITE,
)
from rag.diagnostics import classify_with_judge
from rag.embeddings import EMBEDDING_MODELS, get_embedder
from rag.generation import NO_ANSWER, generate_answer, stream_answer
from rag.indexing import load_or_build_collection
from rag.query import transform
from rag.rerankers import RERANKERS, get_reranker
from rag.retrieval import (
    RETRIEVAL_MODES,
    HybridRetriever,
    RetrievalTrace,
    RetrievedChunk,
    format_pages,
)

__all__ = [
    "RagEngine",
    "RetrievedChunk",
    "RetrievalTrace",
    "RETRIEVAL_MODES",
    "NO_ANSWER",
    "format_pages",
]


class RagEngine:
    """
    Owns the index and the retriever for the life of the process.

    A single instance is shared across requests. The lock serialises the
    retrieval stages, because neither the Chroma client nor the local
    encoders are guaranteed safe to drive from several threads, and
    FastAPI hands each request to a different worker thread.
    """

    def __init__(self, force_reindex=False, on_progress=None):

        self._lock = threading.Lock()

        self.chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)

        self.collection = load_or_build_collection(
            self.chroma_client,
            force_reindex=force_reindex,
            on_progress=on_progress
        )

        self.retriever = HybridRetriever(self.collection)

    # --------------------------------------------------------

    @property
    def chunk_count(self):
        return self.retriever.size

    def stats(self):
        """
        Everything the UI needs to describe and drive the pipeline.

        Deliberately verbose: it carries not just the current settings
        but the available options (`embedding_models`, `rerankers`,
        `strategies`, `sources`, `page_range`), so the front end never
        has to hardcode a list that could drift out of step with the
        server.
        """

        embedder = get_embedder()
        reranker = get_reranker()
        page_start, page_end = self.retriever.page_range()

        return {
            "chunks": self.chunk_count,
            "collection": self.collection.name,
            "llm_model": LLM_MODEL,
            "modes": list(RETRIEVAL_MODES),
            "top_k": TOP_K,
            "sources": self.retriever.sources(),
            "policy_lines": self.retriever.policy_lines(),
            "forms": self.retriever.forms(),
            "page_range": [page_start, page_end],
            "embedding": embedder.describe(),
            "embedding_models": sorted(EMBEDDING_MODELS),
            "reranker": reranker.describe(),
            "rerankers": list(RERANKERS),
            "chunking": {
                "strategy": CHUNK_STRATEGY,
                "strategies": list(CHUNK_STRATEGIES),
                "chunk_size": CHUNK_SIZE,
                "overlap": CHUNK_OVERLAP,
            },
            "defaults": {
                "mode": DEFAULT_MODE,
                "use_mmr": USE_MMR,
                "mmr_lambda": MMR_LAMBDA,
                "mmr_pool": MMR_POOL,
                "use_query_rewrite": USE_QUERY_REWRITE,
                "use_hyde": USE_HYDE,
                "reranker": RERANKER,
                "embedding_model": EMBEDDING_MODEL,
                "min_rerank_score": (
                    MIN_RERANK_SCORE
                    if MIN_RERANK_SCORE is not None
                    else reranker.min_score
                ),
            },
        }

    def reindex(self, on_progress=None):
        """Rebuild the vector index and the BM25 index from the PDFs."""

        with self._lock:

            self.collection = load_or_build_collection(
                self.chroma_client,
                force_reindex=True,
                on_progress=on_progress
            )

            self.retriever = HybridRetriever(self.collection)

        return self.stats()

    # --------------------------------------------------------
    # Retrieval
    # --------------------------------------------------------

    def retrieve(self, question, mode=None, top_k=TOP_K, filters=None,
                 search_query=None, dense_query=None, use_mmr=None,
                 mmr_lambda=MMR_LAMBDA, mmr_pool=MMR_POOL, reranker=None):
        """
        Run retrieval only. Returns (chunks, trace).

        No LLM is involved, which is what lets the evaluator measure
        retrieval quality without spending tokens or waiting on a
        network round trip per question.
        """

        with self._lock:

            return self.retriever.search(
                question,
                mode=mode or DEFAULT_MODE,
                top_k=top_k,
                filters=filters,
                search_query=search_query,
                dense_query=dense_query,
                use_mmr=use_mmr,
                mmr_lambda=mmr_lambda,
                mmr_pool=mmr_pool,
                min_score=MIN_RERANK_SCORE,
                reranker=(
                    get_reranker(reranker) if isinstance(reranker, str)
                    else reranker
                ),
            )

    def prepare(self, question, history=None, mode=None, top_k=TOP_K,
                filters=None, use_rewrite=None, use_hyde=None, use_mmr=None,
                mmr_lambda=MMR_LAMBDA, mmr_pool=MMR_POOL, reranker=None):
        """
        Transform the question, then retrieve.

        Split out from answering so the server can push the sources and
        the trace to the browser before the slower generation starts.
        """

        queries = transform(
            question,
            history=history,
            use_rewrite=USE_QUERY_REWRITE if use_rewrite is None else use_rewrite,
            use_hyde=USE_HYDE if use_hyde is None else use_hyde,
        )

        chunks, trace = self.retrieve(
            queries["condensed"],
            mode=mode,
            top_k=top_k,
            filters=filters,
            search_query=queries["search_query"],
            dense_query=queries["dense_query"],
            use_mmr=use_mmr,
            mmr_lambda=mmr_lambda,
            mmr_pool=mmr_pool,
            reranker=reranker,
        )

        trace.question = question
        trace.config["queries"] = queries

        return queries, chunks, trace

    # --------------------------------------------------------
    # Answering
    # --------------------------------------------------------

    def ask(self, question, history=None, diagnose=False, **options):
        """
        The whole pipeline, answer included, in one blocking call.

        Used by the CLI's one-shot mode and by the evaluator. The trace
        is returned alongside the answer rather than discarded, because
        the caller almost always wants to know *why* it got that answer —
        and re-running retrieval to find out would be both slower and
        potentially different.
        """

        queries, chunks, trace = self.prepare(
            question,
            history=history,
            **options
        )

        answer = generate_answer(
            queries["search_query"],
            chunks,
            history=history
        )

        result = {
            "question": question,
            "queries": queries,
            "standalone_question": queries["condensed"],
            "answer": answer,
            "chunks": chunks,
            "trace": trace,
        }

        if diagnose:
            result["diagnosis"] = classify_with_judge(
                queries["search_query"],
                trace,
                answer
            )

        return result

    def stream(self, question, history=None, **options):
        """
        Yield ("sources", …) then ("trace", …) then ("token", text)…

        Sources first because they are what the user can start reading
        while the answer is still being written.
        """

        queries, chunks, trace = self.prepare(
            question,
            history=history,
            **options
        )

        yield "sources", {
            "standalone_question": queries["condensed"],
            "queries": queries,
            "chunks": [chunk.to_dict() for chunk in chunks],
        }

        yield "trace", trace.to_dict()

        for delta in stream_answer(
            queries["search_query"],
            chunks,
            history=history
        ):
            yield "token", delta
