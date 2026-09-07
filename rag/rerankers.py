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
own default relevance floor. A single global threshold would be silently
wrong for two of the three, and "silently" is the problem: nothing errors,
answers just get worse.

Is the stage worth its latency? Measured, not assumed. On the Week 4
sweep, hybrid fusion alone scored 0.875 hit@1 and hybrid + this
cross-encoder scored 0.969 — +0.094 for about a second of CPU on a
20-candidate shortlist. That is why `none` is a first-class option here:
the control arm is what turns the claim into a number.

Why a cross-encoder rather than simply raising TOP_K: handing the LLM ten
chunks instead of three does raise the chance the answer is somewhere in
the prompt, but it also dilutes it, and this corpus is full of passages
that are near-identical apart from which policy line they scope. Precision
at the top is the thing that matters, and only a model that reads the
question and the passage together can supply it.
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

    NOT REQUIRED BY W3-W6. Kept to show the alternative we rejected and
    why. Cohere Rerank is, on average, the better model — and it is a paid
    API call on every query, and another copy of the corpus leaving the
    machine, which is the same objection that ruled out hosted embeddings.
    A local 90 MB cross-encoder that runs on CPU wins on cost, privacy and
    offline-ability, and loses a little accuracy. Wiring both up behind one
    interface is what makes that a choice rather than an assumption.

    Called over plain HTTP so the project does not grow a dependency for
    an optional, key-gated path.
    """

    key = "cohere"

    # Cohere returns a calibrated 0-1 relevance, not a logit, so the floor
    # is on a completely different scale to the -8.0 used for ms-marco.
    # 0.05 is Cohere's own suggested "almost certainly irrelevant" cutoff
    # rather than something tuned on this corpus - honest caveat, since the
    # path is key-gated and has not been run against the golden set.
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
            # Reranking sits in the middle of a user-facing query, so a
            # hung connection must fail rather than hold the request open.
            # 30s is generous for a payload of 20 short passages; it is a
            # ceiling on the pathological case, not an expected duration.
            timeout=30.0,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "query": question,
                "documents": texts,
                # Ask for every candidate back, not the top few. The caller
                # owns truncation and the floor, and it also needs a score
                # for the candidates that lost, so the trace can show what
                # was dropped and why.
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
            # The relevance floor, and the number with the best paper trail
            # in this repo. It is what produces "I don't know": below it a
            # candidate is treated as a non-answer even if it was the best
            # of a bad pool.
            #
            # -8.0 was chosen against a measured trade, not picked to look
            # round. Question q27 asks for a vehicle make and model; the
            # right chunk is BM25 rank #1 and the cross-encoder scores it
            # -8.36, just under the floor, so the question is missed.
            # Dropping the floor to -12 recovers it:
            #
            #   floor  hit@3   out-of-scope questions with surviving context
            #   -8     0.969   3 / 6
            #   -12    1.000   6 / 6
            #
            # So -12 buys one question and loses the refusal guarantee on
            # three others - it puts plausible-looking noise into the prompt
            # for questions the corpus cannot answer. On an insurance
            # assistant that is the wrong side of the trade, and the honest
            # fix for q27 is a parser or a reranker that handles tabular
            # text, not a lower bar.
            default_min_score=-8.0,
        )

    if key == "bge":
        return LocalCrossEncoder(
            "bge",
            "BAAI/bge-reranker-base",
            # NOT REQUIRED BY W3-W6: wired up as the experiment for the one
            # known ms-marco failure - q27's bare key/value table, which is
            # not the sentence-shaped text ms-marco was trained on.
            #
            # BGE rerankers emit logits on a different scale to ms-marco;
            # roughly, anything under -5 is unrelated. Unlike -8.0 above,
            # this is a rule-of-thumb for the model family and has NOT been
            # swept against this golden set.
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
