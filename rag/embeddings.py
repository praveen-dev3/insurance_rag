"""Embedding models, and the asymmetry most of them require.

The retrieval models that top the MTEB leaderboard are trained
*asymmetrically*: a query and a passage are encoded with different
prefixes, and dropping the prefix costs real accuracy. E5 wants
`query: ` / `passage: `; BGE wants an instruction on the query and
nothing on the passage; MiniLM wants neither.

Getting that wrong is silent — the vectors still come out, they are just
worse — so the prefixes live with the model definition rather than being
the caller's problem.

Why the encoder runs locally, and not through OpenAI or Cohere Embed
--------------------------------------------------------------------
The hosted models are good and would save a 130 MB download. They lose
here on three counts, none of them about quality:

  * insurance documents are personal data, and indexing means uploading
    the entire corpus to a third party;
  * a chunking sweep re-indexes the corpus once per variant — six full
    passes over the corpus at API prices to answer one question about
    chunk size;
  * every retrieval evaluation would need a network round trip per
    question, which is exactly what makes `evaluate.py retrieval` cheap
    enough to run before and after every change.

Running locally costs a one-off model download and some CPU. That is the
whole trade.
"""

import threading

import numpy as np
from sentence_transformers import SentenceTransformer

from rag.config import EMBEDDING_MODEL

# This exact sentence is the one BGE was trained with. It is not a
# description of intent that the model reads for meaning — it is a literal
# string from the training recipe, so paraphrasing it ("Find passages
# about: ") silently degrades retrieval instead of erroring.
BGE_QUERY_INSTRUCTION = (
    "Represent this sentence for searching relevant passages: "
)

# NOT REQUIRED BY W3-W6: only the default, "bge-small", is needed. The
# other four entries are kept as teaching material - they are the
# alternatives we rejected, and having them behind one key makes
# "does the encoder matter?" a measurable question rather than an opinion.
#
# Why bge-small is the default, over the two obvious rivals:
#
#   minilm    the usual first choice, and the same 384 dimensions, but it
#             scores materially lower on the MTEB retrieval benchmark and
#             truncates at 256 word pieces. It is kept as the fast
#             baseline, and as the model whose 256-token ceiling the
#             220-token CHUNK_SIZE is set below - so no chunk is silently
#             half-embedded whichever encoder is selected.
#   bge-base  better again, but 768 dimensions and roughly three times the
#             encode cost, for a corpus where hit-rate@3 is already 0.969.
#             Bigger encoder is the wrong place to spend on this corpus.
#
# `dimensions` and `max_tokens` are properties of the published model, not
# knobs: they are recorded here so index code can size vectors and so the
# chunker's token budget can be checked against the encoder actually in
# use, rather than assumed.
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
        """Load once, lazily, and only in one thread.

        Lazily, because importing rag must not pull a few hundred MB of
        weights off disk - the evaluator's retrieval-only mode and the
        indexing utilities both import this module, and a CLI that spends
        four seconds loading a model before printing --help is a bad CLI.

        The double check around the lock is not paranoia: FastAPI runs
        sync handlers on a threadpool, so two requests really can arrive
        here at once, and loading the same SentenceTransformer twice costs
        the memory twice for no benefit.
        """

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
    """One embedder per model key, shared across the process.

    A registry rather than a plain module-level singleton, because the
    evaluator's sweeps compare encoders inside one process: keying on the
    model name lets two encoders coexist without either one reloading on
    every question.
    """

    key = key or EMBEDDING_MODEL

    with _registry_lock:

        if key not in _embedders:
            _embedders[key] = TextEmbedder(key)

        return _embedders[key]
