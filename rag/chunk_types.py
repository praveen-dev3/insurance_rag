"""The chunk data model and the BM25 tokeniser it is indexed with."""

import re
from dataclasses import dataclass, field

from rag.metadata import UNSPECIFIED


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
