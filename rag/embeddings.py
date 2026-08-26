"""Embedding models, and the asymmetry most of them require.

The retrieval models that top the MTEB leaderboard are trained
*asymmetrically*: a query and a passage are encoded with different
prefixes, and dropping the prefix costs real accuracy. E5 wants
`query: ` / `passage: `; BGE wants an instruction on the query and
nothing on the passage; MiniLM wants neither.

Getting that wrong is silent — the vectors still come out, they are just
worse — so the prefixes live with the model definition rather than being
the caller's problem.
"""

import threading

import numpy as np
from sentence_transformers import SentenceTransformer

from rag.config import EMBEDDING_MODEL

BGE_QUERY_INSTRUCTION = (
    "Represent this sentence for searching relevant passages: "
)

EMBEDDING_MODELS = {
    "minilm": {
        "model_id": "sentence-transformers/all-MiniLM-L6-v2",
        "query_prefix": "",
        "passage_prefix": "",
        "dimensions": 384,
        "max_tokens": 256,
        "note": "Fast baseline. Symmetric — no prefixes.",
    },
    "bge-small": {
        "model_id": "BAAI/bge-small-en-v1.5",
        "query_prefix": BGE_QUERY_INSTRUCTION,
        "passage_prefix": "",
        "dimensions": 384,
        "max_tokens": 512,
        "note": "Strong MTEB retrieval scores at MiniLM size.",
    },
    "bge-base": {
        "model_id": "BAAI/bge-base-en-v1.5",
        "query_prefix": BGE_QUERY_INSTRUCTION,
        "passage_prefix": "",
        "dimensions": 768,
        "max_tokens": 512,
        "note": "Higher quality, ~3x the encode cost of bge-small.",
    },
    "e5-small": {
        "model_id": "intfloat/e5-small-v2",
        "query_prefix": "query: ",
        "passage_prefix": "passage: ",
        "dimensions": 384,
        "max_tokens": 512,
        "note": "Asymmetric prefixes are mandatory for E5.",
    },
    "e5-base": {
        "model_id": "intfloat/e5-base-v2",
        "query_prefix": "query: ",
        "passage_prefix": "passage: ",
        "dimensions": 768,
        "max_tokens": 512,
        "note": "E5 at base size.",
    },
}


class TextEmbedder:
    """
    Encodes queries and passages with the right prefix for the model.

    Embeddings are produced here rather than by Chroma's built-in
    embedding function for two reasons: Chroma's cannot apply asymmetric
    prefixes, and MMR needs the candidate vectors anyway.
    """

    def __init__(self, key=None):

        self.key = key or EMBEDDING_MODEL

        if self.key not in EMBEDDING_MODELS:
            raise ValueError(
                f"Unknown embedding model '{self.key}'. "
                f"Expected one of {sorted(EMBEDDING_MODELS)}."
            )

        self.spec = EMBEDDING_MODELS[self.key]
        self._model = None
        self._lock = threading.Lock()

    @property
    def model_id(self):
        return self.spec["model_id"]

    @property
    def dimensions(self):
        return self.spec["dimensions"]

    def _load(self):
        """Load once, lazily, and only in one thread."""

        if self._model is None:

            with self._lock:

                if self._model is None:
                    print(f"Loading embedding model '{self.model_id}'...")
                    self._model = SentenceTransformer(self.model_id)

        return self._model

    def _encode(self, texts, prefix):

        if not texts:
            return []

        prefixed = [f"{prefix}{text}" for text in texts]

        vectors = self._load().encode(
            prefixed,
            # Cosine similarity on normalised vectors is a dot product,
            # which is what both Chroma's cosine space and MMR assume.
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )

        return np.asarray(vectors, dtype=np.float32)

    def embed_passages(self, texts):
        return self._encode(texts, self.spec["passage_prefix"])

    def embed_queries(self, texts):
        return self._encode(texts, self.spec["query_prefix"])

    def embed_query(self, text):
        return self.embed_queries([text])[0]

    def describe(self):

        return {
            "key": self.key,
            "model_id": self.model_id,
            "dimensions": self.dimensions,
            "max_tokens": self.spec["max_tokens"],
            "asymmetric": bool(
                self.spec["query_prefix"] or self.spec["passage_prefix"]
            ),
            "note": self.spec["note"],
        }


_embedders = {}
_registry_lock = threading.Lock()


def get_embedder(key=None):
    """One embedder per model key, shared across the process."""

    key = key or EMBEDDING_MODEL

    with _registry_lock:

        if key not in _embedders:
            _embedders[key] = TextEmbedder(key)

        return _embedders[key]
