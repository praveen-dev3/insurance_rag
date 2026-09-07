"""A keyword search over the endorsement text, for the search_policy tool.

Not rag.engine. That engine (dense + BM25 + rerank) is what the three real
front ends share, and Task Set D is not testing retrieval quality - it is
testing whether an agent loop and a fixed workflow reach the same coverage
decision over the same tool surface. Standing up the full hybrid pipeline
here would mean this file's number is partly a retrieval-quality number,
which is a different, already-answered question (see
tools/w7_retrieval_delta.py).

Building over tools/data/endorsement_content.py rather than re-parsing the
rendered PDFs keeps this exact: that module is the source
tools/make_endorsements.py renders into insurance_docs/*.pdf, so a chunk
found here is word-for-word what a real retrieval would eventually find in
the indexed corpus, without needing the embedding/rerank stack loaded just
to answer "does form HO-0521 require a secondary power source".
"""

import re
from collections import Counter

from data.endorsement_content import ENDORSEMENTS

STOPWORDS = {
    "a", "an", "and", "any", "applies", "are", "as", "at", "be", "by",
    "for", "from", "in", "is", "it", "of", "on", "or", "that", "the",
    "this", "to", "under", "was", "we", "where", "which", "with", "does",
    "do", "not", "no", "than", "each", "its", "their", "them", "than",
}

WORD_RE = re.compile(r"[a-z0-9]+")

# A clause that states the actual dollar or percentage figure ("A
# deductible of ... ($2,500) applies...") vs. one that only refers to a
# deductible in the abstract ("less the deductible in Clause 5.3"). Both
# share plenty of vocabulary with a "deductible" query; only the first is
# useful to compute_payout, so it needs its own signal to win the rank.
AMOUNT_RE = re.compile(r"\$[\d,]+|\b\d+\s*percent\b|\(\d+%\)")


def tokenize(text):
    return [w for w in WORD_RE.findall(text.lower()) if w not in STOPWORDS]


def _build_chunks():
    """One chunk per paragraph and per exclusion-table row.

    An exclusion row is kept atomic - never split, never merged with a
    neighbouring row - for the same reason CLAUDE.md gives for the real
    chunker: a row and the code that scopes it must travel together or a
    search can return "excluded absolutely" without the code that says
    which exclusion that was.
    """

    chunks = []

    for form in ENDORSEMENTS:
        heading = ""

        for kind, payload in form["blocks"]:

            if kind == "h":
                heading = payload
                continue

            if kind == "p":
                chunks.append({
                    "form_number": form["form_number"],
                    "policy_line": form["policy_line"],
                    "clause": heading,
                    "text": payload,
                })
                continue

            if kind == "t":
                for code, description, disposition in payload["rows"]:
                    chunks.append({
                        "form_number": form["form_number"],
                        "policy_line": form["policy_line"],
                        "clause": f"{heading} / {payload['title']} ({code})",
                        "text": f"{code}: {description}. Disposition: {disposition}.",
                    })

                if payload["note"]:
                    chunks.append({
                        "form_number": form["form_number"],
                        "policy_line": form["policy_line"],
                        "clause": f"{heading} / {payload['title']} (note)",
                        "text": payload["note"],
                    })

    for i, chunk in enumerate(chunks):
        chunk["id"] = f"{chunk['form_number']}#{i}"
        chunk["tokens"] = Counter(tokenize(chunk["text"]))
        chunk["has_amount"] = bool(AMOUNT_RE.search(chunk["text"]))

    return chunks


_CHUNKS = _build_chunks()

FORM_NUMBERS = sorted({chunk["form_number"] for chunk in _CHUNKS})


DEDUCTIBLE_QUERY_WORDS = {"deductible", "excess"}


def _score(query_tokens, chunk):
    """Shared-token count, plus two flat bonuses.

    A query that names "E-14" should out-rank one that just shares
    ordinary words with the E-14 row, and counting a code as one token
    among many would not guarantee that - a five-word disposition can
    out-count a two-token code query on shared-word count alone. Likewise
    a query asking for the deductible should out-rank a clause that only
    refers to "the deductible in Clause 5.3" in passing, over the one
    clause that actually states the dollar or percentage figure - see
    AMOUNT_RE.
    """

    chunk_tokens = chunk["tokens"]

    overlap = sum(min(n, chunk_tokens[tok]) for tok, n in query_tokens.items())

    code_bonus = 5 * sum(
        1 for tok in query_tokens
        if re.fullmatch(r"e\d+", tok) and chunk_tokens[tok]
    )

    amount_bonus = (
        4 if chunk["has_amount"] and (query_tokens.keys() & DEDUCTIBLE_QUERY_WORDS)
        else 0
    )

    return overlap + code_bonus + amount_bonus


def search_policy_corpus(query, form_number=None, top_k=3):
    """Return the top_k chunks by keyword overlap, optionally scoped.

    Mirrors rag.engine.RagEngine.retrieve's shape (query in, scored
    chunks out, a filter that narrows rather than errors on no match) so
    the tool built on top of it reads like the app's real search_policy
    would, not like a toy.
    """

    query_tokens = Counter(tokenize(query))

    pool = (
        [c for c in _CHUNKS if c["form_number"] == form_number]
        if form_number else _CHUNKS
    )

    scored = [
        (chunk, _score(query_tokens, chunk))
        for chunk in pool
    ]

    scored = [(c, s) for c, s in scored if s > 0]
    scored.sort(key=lambda pair: pair[1], reverse=True)

    return [
        {
            "id": c["id"],
            "form_number": c["form_number"],
            "policy_line": c["policy_line"],
            "clause": c["clause"],
            "text": c["text"],
            "score": s,
        }
        for c, s in scored[:top_k]
    ]
