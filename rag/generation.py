"""Prompt construction and grounded answer generation.

This is the only place the retrieved text meets the LLM, so it is the
only place a hallucination can enter the product. The prompt is built to
make that hard rather than to make the answer fluent:

  * the chunks are presented as numbered SOURCES with their document and
    page attached, so the model can cite without inventing a reference;
  * the refusal sentence is given verbatim, so refusals are detectable
    downstream by string match instead of by another LLM call;
  * the rules about conditions exist because insurance text is full of
    "covered, provided that ..." and a summariser that drops the proviso
    produces an answer that is confidently, dangerously wrong.

Temperature is 0 everywhere. Answers to the same question over the same
documents should not vary between runs, and the evaluator depends on
that to attribute a metric change to the retriever rather than to noise.
"""

import re

from openai import OpenAIError

from rag.config import LLM_MODEL, REASONING_EFFORT
from rag.llm import complete, get_client
from rag.query import HISTORY_TURNS
from rag.retrieval import format_pages

# The exact sentence the model is told to emit when the documents do not
# answer the question. Kept as a constant because rag.diagnostics matches
# against it to detect a refusal, and the evaluator counts those.
NO_ANSWER = "I don't know based on the provided documents."

# Prefix used when the API call itself fails. A failed generation is
# returned as text rather than raised, so that one bad request does not
# take down a CLI session or an HTTP handler - but that means an outage
# and a bad answer are the same type, and only this marker tells them
# apart. Anything measuring answer quality must check for it first, or a
# decommissioned model reads as a quality regression.
GENERATION_ERROR = "The language model request failed:"

SYSTEM_PROMPT = (
    "You are a strict document-grounded insurance assistant."
)

# Bumped whenever build_prompt's template changes. Recorded on every trace
# so that a change in behaviour can be pinned to a prompt edit rather than
# argued about. rag.tracing stores a hash of the rendered template
# alongside it, because a version string nobody remembered to bump is
# worse than no version string at all.
ANSWER_PROMPT_VERSION = "answer-v1"


def build_prompt(question, retrieved_chunks):
    """
    Render the retrieved chunks and the question into one user message.

    Each chunk becomes a numbered SOURCE block carrying its chunk_id, the
    form number and edition that scope it, the clause it sits under and
    its page range. That structure is what lets the model cite without
    being able to invent a reference: every component of every citation it
    can make is one it was handed, and each one resolves to exactly one
    row in the index.

    The chunk_id is the load-bearing part. "HO-0304, Clause 3.1" is a
    claim about the corpus that still has to be looked up by hand; a
    chunk_id is a primary key, and verify_citations below turns checking
    an answer into a set membership test.
    """

    context_parts = []

    for index, chunk in enumerate(retrieved_chunks, start=1):

        context_parts.append(
            f"""
SOURCE {index}
chunk_id: {chunk.id}
form_number: {chunk.form_number} (edition {chunk.edition_date})
policy_line: {chunk.policy_line}
clause: {chunk.clause_label}
document: {chunk.source_file}
page: {format_pages(chunk)}

{chunk.text}
"""
        )

    context = "\n".join(context_parts)

    prompt = f"""
You are an insurance document assistant.

Answer the user's question using ONLY the SOURCE blocks below.

RULES:

1. Do not use outside knowledge. Do not invent missing information.

2. Every factual claim in your answer must be followed by a citation in
   exactly this format:

   [chunk_id=<the chunk_id, copied verbatim> | <form_number> | <clause>]

   Copy the chunk_id character for character from the SOURCE block you
   used. Never construct, shorten, merge or guess a chunk_id. If you
   cannot point at the SOURCE block a claim came from, delete the claim.

3. If the SOURCE blocks do not contain enough information to answer,
   reply with exactly this sentence and nothing else:

   "{NO_ANSWER}"

   This is not a judgement call. You have no basis other than the SOURCE
   blocks, so "not in the sources" and "no answer exists" are the same
   outcome and both require the sentence above. Do not reason from your
   own knowledge of insurance. Do not offer a partial answer, a likely
   answer, a general industry practice, or a suggestion about where the
   answer might be found. Do not hedge and then answer anyway.

4. An exclusion code (E-17, E-44, ...) means nothing without the form
   that scopes it. Never state that a code applies without naming the
   form_number and edition from the SOURCE block you read it in. If the
   SOURCE block containing a code does not identify its form, say that
   the scope could not be established rather than assuming it.

5. If a rule is conditional, preserve the condition. Do not assume a
   condition is satisfied unless a SOURCE says it is.

6. If two SOURCES conflict, say so and cite both.

DOCUMENTS:

{context}

USER QUESTION:

{question}

ANSWER:
"""

    return prompt


# Matches the citation format rule 2 demands. Tolerant of whitespace and
# of the model padding the form/clause fields, because the part that has
# to be exact is the chunk_id and only the chunk_id.
CITATION = re.compile(
    r"\[\s*chunk_id\s*=\s*(?P<chunk_id>[^\|\]]+?)\s*(?:\|[^\]]*)?\]",
    re.IGNORECASE,
)


def extract_citations(answer):
    """Every chunk_id the answer claims to have used, in order."""

    return [
        match.group("chunk_id").strip()
        for match in CITATION.finditer(answer or "")
    ]


def verify_citations(answer, retrieved_chunks):
    """
    Check every citation in an answer against what was actually retrieved.

    Returns the resolved and unresolved ids rather than raising. An
    unresolved citation is a real defect - it means the model produced an
    id that is not in the index, which is a hallucinated reference wearing
    the costume of a checkable one - but it is a defect in the *answer*,
    and the caller should be able to show it rather than lose it to an
    exception.

    The point of this function is that it makes "the citations resolve" a
    property that is tested rather than asserted.
    """

    available = {chunk.id: chunk for chunk in retrieved_chunks}

    cited = extract_citations(answer)

    resolved = [chunk_id for chunk_id in cited if chunk_id in available]
    unresolved = [chunk_id for chunk_id in cited if chunk_id not in available]

    return {
        "cited": cited,
        "resolved": sorted(set(resolved)),
        "unresolved": sorted(set(unresolved)),
        "all_resolve": not unresolved and bool(cited),
        "citations": [
            available[chunk_id].citation
            for chunk_id in dict.fromkeys(resolved)
        ],
    }


def is_generation_error(answer):
    """
    Did the API call fail, as opposed to the model declining to answer?

    Kept separate from is_refusal because the two look identical to any
    metric that only counts "answers that contain no citations", and
    conflating them turns an outage into a phantom quality regression.
    """

    return (answer or "").lstrip().startswith(GENERATION_ERROR)


def is_refusal(answer):
    """
    Did the model emit the refusal sentence, and only that?

    Matched on the constant rather than judged by another model, so the
    evaluator counts refusals deterministically. An answer that contains
    the refusal sentence *and* then answers anyway is not a refusal, which
    is why this checks the whole stripped string.
    """

    return (answer or "").strip().strip('"').rstrip(".") == (
        NO_ANSWER.rstrip(".")
    )


def build_messages(question, retrieved_chunks, history=None):
    """
    Assemble the full message list: system, recent turns, then the
    grounded prompt.

    History is replayed so the answer reads as part of a conversation,
    but it is deliberately capped at HISTORY_TURNS and placed *before*
    the grounded prompt. The documents are therefore the last and most
    salient thing the model reads, and a long chat cannot gradually crowd
    them out of the context window.
    """

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    for turn in (history or [])[-HISTORY_TURNS:]:

        # Defensive: the history arrives from an HTTP client, so a turn
        # with a bogus role or an empty body must not reach the API.
        if turn.get("role") in ("user", "assistant") and turn.get("content"):
            messages.append({
                "role": turn["role"],
                "content": turn["content"]
            })

    messages.append({
        "role": "user",
        "content": build_prompt(question, retrieved_chunks)
    })

    return messages


def generate_answer(question, retrieved_chunks, history=None, model=None,
                    on_wait=None):
    """
    Produce the whole answer in one call. Used by the CLI's one-shot mode
    and by the evaluator, where streaming would only get in the way.

    An empty chunk list short-circuits to the refusal: with nothing
    retrieved there is nothing to ground an answer in, and asking the
    model anyway is how an empty context turns into a confident guess.
    """

    if not retrieved_chunks:
        return NO_ANSWER

    try:
        response = complete(
            model=model or LLM_MODEL,
            temperature=0,
            reasoning_effort=REASONING_EFFORT,
            messages=build_messages(question, retrieved_chunks, history),
            on_wait=on_wait,
        )
    except OpenAIError as error:
        # Returned rather than raised: a failed generation is a bad
        # answer, not a crashed application, and the caller (CLI, API,
        # evaluator) can render it like any other answer. rag.llm retries
        # rate limits before it gets here, so anything reaching this line
        # is a real failure rather than a busy minute.
        return f"{GENERATION_ERROR} {error}"

    return response.choices[0].message.content


def stream_answer(question, retrieved_chunks, history=None, model=None):
    """
    Yield the answer in deltas as the model produces them.

    Errors are yielded as text rather than raised so that a failure mid
    stream still reaches the user instead of truncating the response
    without explanation — from the browser's point of view a raised
    exception and a finished answer look identical.
    """

    if not retrieved_chunks:
        yield NO_ANSWER
        return

    try:
        stream = get_client().chat.completions.create(
            model=model or LLM_MODEL,
            temperature=0,
            reasoning_effort=REASONING_EFFORT,
            stream=True,
            messages=build_messages(question, retrieved_chunks, history)
        )

        for event in stream:

            # The final chunk of a Groq stream carries usage data and no
            # choices; iterating it blindly would raise IndexError.
            if not event.choices:
                continue

            delta = event.choices[0].delta

            if delta and delta.content:
                yield delta.content

    except OpenAIError as error:
        yield f"\n\nThe language model request failed: {error}"
