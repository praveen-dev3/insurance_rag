"""Query transforms — everything that happens to the question before
retrieval sees it.

Three transforms, applied in this order:

  condense  resolve a follow-up against the conversation, so "how much is
            it?" becomes a question that means something on its own.
  rewrite   restate the question in the vocabulary of the corpus, so a
            user's phrasing ("can I lend my bike to a mate?") lands
            nearer the clause that answers it ("persons entitled to
            drive").
  HyDE      draft a hypothetical answer and embed *that* instead of the
            question. A question and its answer look different to an
            embedding model; an answer and the passage containing it look
            alike. HyDE exploits the second.

All three are best-effort: if the model call fails, the original
question is used. A degraded query beats a broken request.
"""

from openai import OpenAIError

from rag.config import UTILITY_MODEL
from rag.llm import complete

# How many previous turns are replayed. Enough for a follow-up to make
# sense, short enough that the documents stay dominant in the context.
HISTORY_TURNS = 6


def _complete(prompt, max_tokens=220):

    response = complete(
        model=UTILITY_MODEL,
        temperature=0,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}]
    )

    return (response.choices[0].message.content or "").strip()


# ============================================================
# CONDENSATION
# ============================================================

def condense_question(question, history):
    """
    Rewrite a follow-up into a question that stands on its own.

    Retrieval sees only the question string, so "what about for dental?"
    retrieves nothing useful unless the missing subject is restored from
    the conversation.
    """

    if not history:
        return question

    transcript = "\n".join(
        f"{turn['role'].capitalize()}: {turn['content']}"
        for turn in history[-HISTORY_TURNS:]
    )

    prompt = (
        "Given the conversation below, rewrite the follow-up question so "
        "that it can be understood without the conversation.\n\n"
        "Rules:\n"
        "- Keep the user's wording and terminology wherever possible.\n"
        "- Only resolve references such as 'it', 'that', 'the same'.\n"
        "- Do not answer the question.\n"
        "- If the question already stands alone, return it unchanged.\n"
        "- Return the rewritten question only, with no preamble.\n\n"
        f"CONVERSATION:\n{transcript}\n\n"
        f"FOLLOW-UP QUESTION:\n{question}\n\n"
        "STANDALONE QUESTION:"
    )

    try:
        rewritten = _complete(prompt)
    except OpenAIError:
        return question

    return rewritten or question


# ============================================================
# QUERY REWRITING
# ============================================================

def rewrite_query(question, domain="insurance policy documents"):
    """
    Restate the question in the vocabulary the documents actually use.

    Deliberately conservative: expanding a question into something the
    user did not ask is how retrieval starts answering the wrong thing.
    Identifiers, amounts and dates are preserved verbatim, because those
    are exactly what the BM25 half of the retriever keys on.
    """

    prompt = (
        f"Rewrite the search query below so it retrieves better from "
        f"{domain}.\n\n"
        "Rules:\n"
        "- Keep every identifier, number, date and proper noun exactly "
        "as written.\n"
        "- Prefer the formal terminology such documents use.\n"
        "- Add at most a few clarifying terms; do not change the "
        "question's meaning or scope.\n"
        "- Do not answer the question.\n"
        "- Return the rewritten query only, on one line.\n\n"
        f"QUERY:\n{question}\n\n"
        "REWRITTEN QUERY:"
    )

    try:
        rewritten = _complete(prompt, max_tokens=120)
    except OpenAIError:
        return question

    # A rewrite that collapses the query to a couple of words has lost
    # more than it gained.
    if not rewritten or len(rewritten.split()) < 2:
        return question

    return rewritten


# ============================================================
# HyDE
# ============================================================

def hyde_document(question, domain="an insurance policy"):
    """
    Draft the passage that would answer the question.

    The draft is deliberately never shown to the user and never enters
    the grounded prompt — it exists only as a retrieval probe, and it is
    invented, so treating it as fact would be exactly the hallucination
    this whole system is built to avoid.
    """

    prompt = (
        f"Write a short passage from {domain} that would answer the "
        "question below.\n\n"
        "Rules:\n"
        "- Write it in the style and vocabulary of a policy document.\n"
        "- Two or three sentences.\n"
        "- Invent plausible specifics if needed; this text is used only "
        "as a search probe and is never shown to anyone.\n"
        "- Return the passage only.\n\n"
        f"QUESTION:\n{question}\n\n"
        "PASSAGE:"
    )

    try:
        passage = _complete(prompt, max_tokens=220)
    except OpenAIError:
        return None

    return passage or None


# ============================================================
# PIPELINE
# ============================================================

def transform(question, history=None, use_rewrite=False, use_hyde=False):
    """
    Run the enabled transforms and report what each one produced.

    Returns a dict rather than a bare string so the inspection view can
    show the question at every stage — when retrieval goes wrong, the
    transform that mangled the query is a prime suspect.
    """

    condensed = condense_question(question, history or [])

    rewritten = rewrite_query(condensed) if use_rewrite else None

    search_query = rewritten or condensed

    hyde = hyde_document(search_query) if use_hyde else None

    return {
        "original": question,
        "condensed": condensed,
        "rewritten": rewritten,
        "hyde": hyde,
        # What BM25 and the reranker see.
        "search_query": search_query,
        # What gets embedded for the dense search.
        "dense_query": hyde or search_query,
    }
