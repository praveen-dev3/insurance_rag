"""Every tunable in one place, so the CLI, the API and the evaluator
cannot drift apart.

Anything that changes what ends up *in* the index (chunking, embedding
model) is folded into the corpus fingerprint, so switching it forces a
rebuild instead of silently querying a mismatched index.
"""

import os

from dotenv import load_dotenv

load_dotenv()


def _flag(name, default=False):
    """Read a boolean from the environment without surprises."""

    raw = os.getenv(name)

    if raw is None:
        return default

    return raw.strip().lower() in ("1", "true", "yes", "on")


# ------------------------------------------------------------------
# Groq / LLM
# ------------------------------------------------------------------

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# LLM used for the final, grounded answer.
#
# The llama-3.x models this project was built against were withdrawn from
# Groq and now 404. Note the failure mode that caused: a dead model does
# not crash the pipeline, because generate_answer returns the API error as
# the answer string rather than raising. So every answer came back as
# "The language model request failed: ..." and every citation check
# reported zero citations - which reads like a prompting regression, not
# an outage. Anything that pins a model id should fail loudly instead.
# The free tier meters each model separately: 8,000 tokens per minute and
# 200,000 per day, per model. The Week 5 traffic run spent the whole daily
# budget of gpt-oss-120b on 70 traces and then wrote 65 rate-limit errors
# into the trace file, so the work is split across the two budgets - and
# the split happens to be the better design anyway, because a judge that
# is the same model as the generator grades its own homework.
#
#   LLM_MODEL     writes the answers and the claim summaries.
#   JUDGE_MODEL   grades them. Deliberately NOT the same model.
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-20b")

# gpt-oss models emit reasoning tokens that are billed against the same
# budget and are never shown. On this corpus "low" cost about a third of
# the completion tokens of "medium" and changed no answer we could see, so
# it buys roughly three times as much traffic out of a fixed daily cap.
# Recorded in every trace, because it is a model parameter like any other.
REASONING_EFFORT = os.getenv("REASONING_EFFORT", "low")

# How many times to wait out a 429 before giving up, and the longest single
# wait worth taking. The daily bucket refills at a trickle, so a wait of
# more than a few minutes means the budget is gone rather than busy, and
# blocking a batch for an hour to discover that is not useful.
RATE_LIMIT_RETRIES = int(os.getenv("RATE_LIMIT_RETRIES", "6"))
MAX_RATE_LIMIT_WAIT = float(os.getenv("MAX_RATE_LIMIT_WAIT", "180"))

# Small, fast model used for query transforms (condensation, rewriting,
# HyDE) and for the LLM-judge in failure separation. It never sees the
# retrieved documents when transforming, so it cannot leak into answers.
UTILITY_MODEL = os.getenv("UTILITY_MODEL", "openai/gpt-oss-20b")

# Kept for backwards compatibility with earlier configs.
CONDENSE_MODEL = os.getenv("CONDENSE_MODEL", UTILITY_MODEL)

# The LLM judge in rag/judge.py. Held apart from LLM_MODEL on purpose, and
# now held apart by MODEL FAMILY as well.
#
# The first attempt used gpt-oss-120b and 22 of 25 verdicts came back as
# 429s: the Week 5 traffic had already spent that model's 200,000-token
# daily budget, which refills at roughly 139 tokens a minute, so the API
# was asking for a four-minute wait per call. The failure was recorded
# honestly - rag/judge.py returns faithful=None on error and rag/judge.py's
# agreement() drops those from the denominator rather than scoring them -
# so the run reported "3 scored, 22 unscored" instead of a 100% agreement
# figure computed from three cases. That is the whole reason the error
# path returns None rather than defaulting to True.
#
# Qwen is a different model family from the gpt-oss generator, which is a
# stronger independence property than a bigger sibling would have been: a
# judge sharing a tokenizer, a training corpus and a house style with the
# thing it grades will forgive its own idioms.
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "qwen/qwen3.8-27b")


# ------------------------------------------------------------------
# Chunking
# ------------------------------------------------------------------

# "fixed"     - flat token window over the whole document
# "recursive" - split on structure (blank lines, sentences) first, then
#               pack into token windows without crossing a hard boundary
# "sentence"  - one chunk per sentence group, overlapping by sentences
# "structure" - split on the document's own form/clause/table landmarks,
#               keep an exclusion row atomic, stamp every chunk with the
#               form number and clause that scope it
CHUNK_STRATEGY = os.getenv("CHUNK_STRATEGY", "structure")

# Sizes are in tokens. The default is kept under the 256 word-piece
# truncation limit of the small sentence-transformer encoders, so no
# chunk is embedded only partially.
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "220"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "40"))

# Sentence strategy only: how many sentences overlap between chunks.
SENTENCE_OVERLAP = int(os.getenv("SENTENCE_OVERLAP", "1"))


# ------------------------------------------------------------------
# Embeddings
# ------------------------------------------------------------------

# Key into rag.embeddings.EMBEDDING_MODELS.
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "bge-small")


# ------------------------------------------------------------------
# Vector store (Chroma / HNSW)
# ------------------------------------------------------------------

# All supported encoders emit normalised vectors, so cosine is the right
# space. ef_construction trades index build time for recall; ef_search
# trades query latency for recall; max_neighbors (M) trades memory for
# recall. These defaults favour recall — the corpus is small.
HNSW_SPACE = os.getenv("HNSW_SPACE", "cosine")
HNSW_EF_CONSTRUCTION = int(os.getenv("HNSW_EF_CONSTRUCTION", "200"))
HNSW_EF_SEARCH = int(os.getenv("HNSW_EF_SEARCH", "100"))
HNSW_MAX_NEIGHBORS = int(os.getenv("HNSW_MAX_NEIGHBORS", "32"))


# ------------------------------------------------------------------
# Retrieval
# ------------------------------------------------------------------

# Candidates pulled from each retriever before fusion.
DENSE_TOP_K = int(os.getenv("DENSE_TOP_K", "20"))
SPARSE_TOP_K = int(os.getenv("SPARSE_TOP_K", "20"))

# Reciprocal Rank Fusion damping constant. 60 is the value from the
# original RRF paper and behaves well without per-corpus tuning.
RRF_K = int(os.getenv("RRF_K", "60"))

# Upper bound on how many fused candidates reach the reranker.
RERANK_CANDIDATES = int(os.getenv("RERANK_CANDIDATES", "20"))

# Final number of chunks handed to the LLM.
TOP_K = int(os.getenv("TOP_K", "3"))

DEFAULT_MODE = os.getenv("DEFAULT_MODE", "hybrid")


# ------------------------------------------------------------------
# MMR (Maximal Marginal Relevance)
# ------------------------------------------------------------------

# Overlapping chunks make near-duplicate neighbours very likely, and
# three paraphrases of one paragraph is a worse prompt than three
# different paragraphs. MMR trades a little relevance for coverage.
USE_MMR = _flag("USE_MMR", False)

# 1.0 = pure relevance, 0.0 = pure diversity.
MMR_LAMBDA = float(os.getenv("MMR_LAMBDA", "0.7"))

# How many fused candidates MMR selects before reranking.
MMR_POOL = int(os.getenv("MMR_POOL", "10"))


# ------------------------------------------------------------------
# Reranking
# ------------------------------------------------------------------

# Key into rag.rerankers.RERANKERS ("none" disables the stage).
RERANKER = os.getenv("RERANKER", "ms-marco")

COHERE_API_KEY = os.getenv("COHERE_API_KEY", "")
COHERE_RERANK_MODEL = os.getenv("COHERE_RERANK_MODEL", "rerank-english-v3.0")

# Reranker scores are unbounded logits; anything below this is a
# non-answer even if it was the best of a bad pool. Scale is per model,
# so rag.rerankers carries a default floor for each.
MIN_RERANK_SCORE = (
    float(os.environ["MIN_RERANK_SCORE"])
    if os.getenv("MIN_RERANK_SCORE")
    else None
)

CROSS_ENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


# ------------------------------------------------------------------
# Query transforms
# ------------------------------------------------------------------

# Rewrite the user's phrasing into a retrieval-friendly query.
USE_QUERY_REWRITE = _flag("USE_QUERY_REWRITE", False)

# HyDE: embed a hypothetical answer instead of the question, on the
# theory that an answer looks more like the passage that contains it.
USE_HYDE = _flag("USE_HYDE", False)


# ------------------------------------------------------------------
# Storage
# ------------------------------------------------------------------

DOCUMENTS_FOLDER = os.getenv("DOCUMENTS_FOLDER", "insurance_docs")
CHROMA_PATH = os.getenv("CHROMA_PATH", "./chroma_db")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "insurance_documents")

GOLDEN_SET_PATH = os.getenv("GOLDEN_SET_PATH", "eval/golden_set.json")
EVAL_RESULTS_PATH = os.getenv("EVAL_RESULTS_PATH", "eval/results")

# Bumped whenever the indexing pipeline changes shape, so an index built
# by an older version of this code is not silently reused. v4 added the
# endorsement provenance fields (source_file, form_number, policy_line,
# edition_date) and the per-file fingerprint that incremental sync reads.
INDEX_SCHEMA_VERSION = "4"


def index_signature():
    """
    The settings that decide what is stored in the index.

    Folded into the corpus fingerprint: change any of these and the next
    run rebuilds rather than querying an index built under other rules.
    """

    return "|".join([
        f"v{INDEX_SCHEMA_VERSION}",
        CHUNK_STRATEGY,
        str(CHUNK_SIZE),
        str(CHUNK_OVERLAP),
        str(SENTENCE_OVERLAP),
        EMBEDDING_MODEL,
        HNSW_SPACE,
    ])


def require_api_key():
    """
    Fail loudly, and only when the key is actually about to be used.

    Importing the package must stay side-effect free so that indexing
    utilities and the evaluator can run without any credentials.
    """

    if not GROQ_API_KEY:
        raise ValueError(
            "GROQ_API_KEY environment variable is not set."
        )

    return GROQ_API_KEY
