"""Rerankers — the precision stage.

Recall-stage retrievers (vectors, BM25) score a chunk without ever
looking at the question and the chunk together: the chunk's
representation is computed once, offline, and compared to the query's.
A cross-encoder reads the pair jointly and can therefore tell "the
policy covers X" from "the policy does not cover X", which a bi-encoder
frequently cannot.

Three implementations are wired up, all behind one interface:

  ms-marco  local cross-encoder, the default. Fast, no API key.
  bge       BAAI/bge-reranker — stronger, larger download.
  cohere    hosted Cohere Rerank. Needs COHERE_API_KEY.

Scores are NOT comparable across rerankers — ms-marco and BGE emit
unbounded logits, Cohere emits 0-1 relevance — so each one carries its
own default relevance floor.
"""

import threading

import httpx

from rag.config import (
    COHERE_API_KEY,
    COHERE_RERANK_MODEL,
    CROSS_ENCODER_MODEL,
    MIN_RERANK_SCORE,
    RERANKER,
)

RERANKERS = ("none", "ms-marco", "bge", "cohere")


class BaseReranker:
    """
    The interface every reranker implements: score(question, texts).

    Scoring returns a list parallel to `texts` rather than a sorted
    result, so the caller keeps ownership of ordering and can attach each
    score back to the chunk it belongs to for the trace.
    """

    key = "none"
    default_min_score = None

    @property
    def min_score(self):
        """An explicit config override wins over the per-model default."""

        if MIN_RERANK_SCORE is not None:
            return MIN_RERANK_SCORE

        return self.default_min_score

    def score(self, question, texts):
        """Relevance of each text to the question, in the input order."""

        raise NotImplementedError

    def describe(self):

        return {
            "key": self.key,
            "min_score": self.min_score,
        }


class NullReranker(BaseReranker):
    """
    Keeps fusion order untouched.

    Useful as the control arm when measuring what reranking actually buys.
    """

    key = "none"

    def score(self, question, texts):
        # Descending so the existing sort preserves the incoming order.
        return [float(-index) for index in range(len(texts))]


class LocalCrossEncoder(BaseReranker):
    """A sentence-transformers CrossEncoder, loaded on first use."""

    def __init__(self, key, model_id, default_min_score):

        self.key = key
        self.model_id = model_id
        self.default_min_score = default_min_score
        self._model = None
        self._lock = threading.Lock()

    def _load(self):

        if self._model is None:

            with self._lock:

                if self._model is None:
                    from sentence_transformers import CrossEncoder

                    print(f"Loading reranker '{self.model_id}'...")
                    self._model = CrossEncoder(self.model_id)

        return self._model

    def score(self, question, texts):

        if not texts:
            return []

        pairs = [[question, text] for text in texts]

        return [float(score) for score in self._load().predict(pairs)]

    def describe(self):

        return {**super().describe(), "model_id": self.model_id}


class CohereReranker(BaseReranker):
    """
    Hosted Cohere Rerank.

    Called over plain HTTP so the project does not grow a dependency for
    an optional, key-gated path.
    """

    key = "cohere"
    default_min_score = 0.05

    ENDPOINT = "https://api.cohere.com/v2/rerank"

    def __init__(self, model=None, api_key=None):

        self.model = model or COHERE_RERANK_MODEL
        self.api_key = api_key or COHERE_API_KEY

    def score(self, question, texts):

        if not texts:
            return []

        if not self.api_key:
            raise ValueError(
                "RERANKER=cohere requires COHERE_API_KEY to be set."
            )

        response = httpx.post(
            self.ENDPOINT,
            timeout=30.0,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "query": question,
                "documents": texts,
                "top_n": len(texts),
            },
        )

        response.raise_for_status()

        # Cohere returns only the ranked subset, in relevance order; put
        # the scores back in the caller's original order.
        scores = [0.0] * len(texts)

        for result in response.json().get("results", []):
            scores[result["index"]] = float(result["relevance_score"])

        return scores

    def describe(self):

        return {
            **super().describe(),
            "model_id": self.model,
            "configured": bool(self.api_key),
        }


def _build(key):

    if key == "none":
        return NullReranker()

    if key == "ms-marco":
        return LocalCrossEncoder(
            "ms-marco",
            CROSS_ENCODER_MODEL,
            default_min_score=-8.0,
        )

    if key == "bge":
        return LocalCrossEncoder(
            "bge",
            "BAAI/bge-reranker-base",
            # BGE rerankers emit logits on a different scale to
            # ms-marco; roughly, anything under -5 is unrelated.
            default_min_score=-5.0,
        )

    if key == "cohere":
        return CohereReranker()

    raise ValueError(
        f"Unknown reranker '{key}'. Expected one of {RERANKERS}."
    )


_instances = {}
_registry_lock = threading.Lock()


def get_reranker(key=None):
    """One reranker per key, shared across the process."""

    key = key or RERANKER

    with _registry_lock:

        if key not in _instances:
            _instances[key] = _build(key)

        return _instances[key]
