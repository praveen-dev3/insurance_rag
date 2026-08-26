"""Failure separation.

"The app is sometimes wrong" is not a fixable statement. There are two
failures hiding inside it, and they have opposite fixes:

  RETRIEVAL   the passage that answers the question never reached the
              prompt. A better LLM changes nothing. Fix the retriever:
              chunking, hybrid, reranking, query rewriting.

  GENERATION  the right passage was in the prompt and the answer is
              still wrong — a misread condition, a missing citation, an
              invented number. Fix the prompt or the model.

Two ways to tell them apart are provided. With a labelled question you
get a deterministic verdict from the ground truth; without one, an LLM
judge reads the retrieved context and rules on whether it was sufficient.
"""

import json
import re
from dataclasses import asdict, dataclass, field

from openai import OpenAIError

from rag.config import UTILITY_MODEL
from rag.generation import NO_ANSWER
from rag.llm import get_client

RETRIEVAL_FAILURE = "retrieval_failure"
GENERATION_FAILURE = "generation_failure"
CORRECT_REFUSAL = "correct_refusal"
MISSED_REFUSAL = "missed_refusal"
OK = "ok"

LABELS = (
    RETRIEVAL_FAILURE,
    GENERATION_FAILURE,
    CORRECT_REFUSAL,
    MISSED_REFUSAL,
    OK,
)

EXPLANATIONS = {
    RETRIEVAL_FAILURE: (
        "The answering passage never reached the prompt. Fix retrieval."
    ),
    GENERATION_FAILURE: (
        "The right passage was retrieved and the answer is still wrong. "
        "Fix the prompt or the model."
    ),
    CORRECT_REFUSAL: (
        "Not in the corpus, and the app correctly said so."
    ),
    MISSED_REFUSAL: (
        "Not in the corpus, and the app answered anyway. This is the "
        "hallucination case."
    ),
    OK: "Right passage, right answer.",
}


# The three-way vocabulary the Week 4 brief grades against. This module's
# own labels are finer - it splits "not in corpus" by whether the app
# refused or hallucinated, which is the difference between a safe system
# and an unsafe one - so the mapping is many-to-one and lossy in that one
# direction only. Both are reported; the tally uses these.
TASK_LABELS = {
    RETRIEVAL_FAILURE: "R",
    GENERATION_FAILURE: "G",
    CORRECT_REFUSAL: "Not-In-Corpus",
    MISSED_REFUSAL: "Not-In-Corpus",
    OK: "OK",
}


@dataclass
class Diagnosis:
    """
    A verdict on one answer.

    `context_sufficient` and `answer_grounded` are kept as separate
    fields, not merged into the label, because they are what the label is
    derived from: sufficient-but-not-grounded is a generation failure,
    insufficient is a retrieval one. Keeping both means a surprising
    label can be checked rather than merely disbelieved.
    """

    label: str
    reason: str = ""
    context_sufficient: bool | None = None
    answer_grounded: bool | None = None
    refused: bool = False
    evidence: dict = field(default_factory=dict)

    @property
    def explanation(self):
        return EXPLANATIONS.get(self.label, "")

    @property
    def task_label(self):
        """R / G / Not-In-Corpus / OK."""

        return TASK_LABELS.get(self.label, self.label)

    def to_dict(self):
        return {
            **asdict(self),
            "explanation": self.explanation,
            "task_label": self.task_label,
        }


# ============================================================
# CHUNK-LEVEL VERDICT (Week 4)
# ============================================================

def _describe(chunk):
    """A chunk in one short phrase, for an evidence line."""

    form = getattr(chunk, "form_number", None) or chunk.source
    clause = getattr(chunk, "clause_label", None) or "?"
    score = getattr(chunk, "rerank_score", None)

    if score is None:
        score = getattr(chunk, "rrf_score", None)

    tail = f" {score:.3f}" if isinstance(score, (int, float)) else ""

    return f"{form}/{clause}{tail}"


def classify_by_chunk_id(trace, answer, correct_chunk_id, k=3,
                         answerable=True, answer_contains=None):
    """
    Deterministic R / G / Not-In-Corpus verdict against a known chunk_id.

    Week 3 labelled ground truth at page level on purpose, because chunk
    ids move whenever the chunker changes and page labels stay valid
    across a chunking sweep. Week 4 changes only the *retriever* and pins
    the chunker, so chunk ids are stable for the whole experiment and can
    carry the ground truth - which is stricter, and is what the brief
    asks for.

    The reason field is written as a single line of trace evidence rather
    than a verdict, because "R" on its own is an assertion and "the
    correct chunk was at fused rank 9 and the reranker scored it -1.0" is
    a fact someone else can check.
    """

    top = trace.final[:k]
    top_ids = [chunk.id for chunk in top]

    refused = answer_refuses(answer)

    if not answerable:

        return Diagnosis(
            label=CORRECT_REFUSAL if refused else MISSED_REFUSAL,
            reason=(
                f"Out of corpus; app refused. Top-{k} were "
                f"[{', '.join(_describe(c) for c in top) or 'nothing survived the score floor'}]."
                if refused else
                f"Out of corpus but the app answered anyway from "
                f"[{', '.join(_describe(c) for c in top)}]."
            ),
            refused=refused,
            evidence={"top_ids": top_ids},
        )

    if correct_chunk_id not in top_ids:

        # Where did it actually go? A chunk that fusion found and the
        # reranker discarded is a different bug from one never retrieved,
        # and the fix is different too.
        fused_rank = next(
            (
                rank for rank, chunk in enumerate(trace.fused, start=1)
                if chunk.id == correct_chunk_id
            ),
            None,
        )

        reranked_rank = next(
            (
                rank for rank, chunk in enumerate(trace.reranked, start=1)
                if chunk.id == correct_chunk_id
            ),
            None,
        )

        if fused_rank is None:
            where = "it was never retrieved by any retriever"
        elif reranked_rank is None:
            where = f"fusion had it at rank {fused_rank}, rerank dropped it"
        else:
            where = (
                f"fusion had it at rank {fused_rank}, "
                f"rerank left it at rank {reranked_rank}"
            )

        return Diagnosis(
            label=RETRIEVAL_FAILURE,
            reason=(
                f"Correct chunk absent from top-{k}; {where}. "
                f"Top-{k} were [{', '.join(_describe(c) for c in top)}]."
            ),
            context_sufficient=False,
            refused=refused,
            evidence={
                "correct_chunk_id": correct_chunk_id,
                "top_ids": top_ids,
                "fused_rank": fused_rank,
                "reranked_rank": reranked_rank,
                "present_before_rerank": fused_rank is not None,
            },
        )

    rank = top_ids.index(correct_chunk_id) + 1

    # No answer was generated, so the generation half cannot be judged.
    # Returning OK here would claim the answer was good; returning
    # GENERATION_FAILURE would be worse still, because an empty string
    # trips answer_refuses() and every retrieval success would be
    # mislabelled as a generation failure.
    if answer is None:

        return Diagnosis(
            label=OK,
            reason=(
                f"Correct chunk at rank {rank} of {k}. "
                "Answer not generated, so generation was not judged."
            ),
            context_sufficient=True,
            answer_grounded=None,
            evidence={"correct_chunk_id": correct_chunk_id, "rank": rank},
        )

    missing = missing_phrases(answer, answer_contains)

    if refused or missing:

        return Diagnosis(
            label=GENERATION_FAILURE,
            reason=(
                f"Correct chunk WAS at rank {rank} of {k} and the answer "
                + (
                    "still refused."
                    if refused
                    else f"still omits {missing}."
                )
            ),
            context_sufficient=True,
            answer_grounded=False,
            refused=refused,
            evidence={
                "correct_chunk_id": correct_chunk_id,
                "rank": rank,
                "missing_phrases": missing,
            },
        )

    return Diagnosis(
        label=OK,
        reason=f"Correct chunk at rank {rank} of {k} and the answer uses it.",
        context_sufficient=True,
        answer_grounded=True,
        evidence={"correct_chunk_id": correct_chunk_id, "rank": rank},
    )


# Typographic characters an LLM emits where the source document has
# plain ASCII. Left unnormalised, a substring check for "E-17" fails
# against an answer that says "E‑17" - and the question gets labelled a
# generation failure when the answer was correct all along. That is a
# worse bug than it looks: it sends you off to fix a prompt that was
# never broken, and it inflates G at the expense of R, which is the exact
# ratio the whole week turns on.
_UNICODE_LOOKALIKES = {
    "‐": "-",  # hyphen
    "‑": "-",  # non-breaking hyphen
    "‒": "-",  # figure dash
    "–": "-",  # en dash
    "—": "-",  # em dash
    "−": "-",  # minus sign
    " ": " ",  # no-break space
    " ": " ",  # thin space
    " ": " ",  # narrow no-break space
    "‘": "'",
    "’": "'",
    "“": '"',
    "”": '"',
}


def normalize_for_match(text):
    """
    Fold typographic variants to ASCII before substring matching.

    Also closes the gap in "2 %". Models emit a thin space before a
    percent sign because typographers do; the document says "2%", and a
    checker that treats those as different facts is measuring house style.
    """

    text = text or ""

    for source, target in _UNICODE_LOOKALIKES.items():
        text = text.replace(source, target)

    text = " ".join(text.lower().split())

    return re.sub(r"(\d)\s+%", r"\1%", text)


def missing_phrases(answer, answer_contains):
    """
    Which required phrases are genuinely absent from the answer.

    An entry may be a string, which must appear, or a list of strings, of
    which any one satisfies the requirement. The any-of form exists
    because some facts have more than one faithful rendering - "2%" and
    "2 percent" are the same claim - and pinning one spelling measures the
    model's typography rather than its correctness.
    """

    normalised = normalize_for_match(answer)

    missing = []

    for phrase in answer_contains or []:

        variants = phrase if isinstance(phrase, (list, tuple)) else [phrase]

        if not any(normalize_for_match(v) in normalised for v in variants):
            missing.append(
                "|".join(variants) if len(variants) > 1 else variants[0]
            )

    return missing


def answer_refuses(answer):
    """
    Did the app decline to answer?

    Matched loosely, because the model paraphrases the refusal sentence
    even at temperature 0.
    """

    if not answer:
        return True

    lowered = answer.lower()

    return (
        NO_ANSWER.lower() in lowered
        or "i don't know based on" in lowered
        or "do not contain" in lowered and "i don't know" in lowered
    )


# ============================================================
# WITH GROUND TRUTH
# ============================================================

def classify_with_ground_truth(trace, answer, relevant_pages,
                              source=None, answer_contains=None,
                              answerable=True):
    """
    Deterministic verdict for a labelled question.

    Retrieval is judged at page level rather than chunk level, so the
    same labels stay valid when the chunking strategy changes and every
    chunk id changes with it.
    """

    refused = answer_refuses(answer)

    if not answerable:

        return Diagnosis(
            label=CORRECT_REFUSAL if refused else MISSED_REFUSAL,
            reason=(
                "Out of scope and refused."
                if refused
                else "Out of scope but the app answered anyway."
            ),
            refused=refused,
            evidence={"retrieved": _retrieved_pages(trace)},
        )

    retrieved = _retrieved_pages(trace)

    hit = any(
        _pages_overlap(chunk, relevant_pages, source)
        for chunk in trace.final
    )

    if not hit:

        return Diagnosis(
            label=RETRIEVAL_FAILURE,
            reason=(
                f"Expected page(s) {sorted(relevant_pages)} were not in "
                f"the final context (got {retrieved})."
            ),
            context_sufficient=False,
            refused=refused,
            evidence={
                "expected_pages": sorted(relevant_pages),
                "retrieved": retrieved,
                "present_before_rerank": any(
                    _pages_overlap(chunk, relevant_pages, source)
                    for chunk in trace.fused
                ),
            },
        )

    missing = missing_phrases(answer, answer_contains)

    if refused or missing:

        return Diagnosis(
            label=GENERATION_FAILURE,
            reason=(
                "Right passage retrieved but the answer refused."
                if refused
                else f"Right passage retrieved but the answer omits {missing}."
            ),
            context_sufficient=True,
            answer_grounded=False,
            refused=refused,
            evidence={"missing_phrases": missing, "retrieved": retrieved},
        )

    return Diagnosis(
        label=OK,
        reason="Expected page retrieved and the answer contains the facts.",
        context_sufficient=True,
        answer_grounded=True,
        evidence={"retrieved": retrieved},
    )


def _pages_overlap(chunk, relevant_pages, source=None):

    if source and chunk.source != source:
        return False

    return any(
        chunk.page_start <= page <= chunk.page_end
        for page in relevant_pages
    )


def _retrieved_pages(trace):

    return [
        {"source": chunk.source, "pages": [chunk.page_start, chunk.page_end]}
        for chunk in trace.final
    ]


# ============================================================
# WITHOUT GROUND TRUTH (LLM JUDGE)
# ============================================================

JUDGE_PROMPT = """You are auditing a document question-answering system.

Decide two things, independently:

1. context_sufficient - do the CONTEXT passages contain the information
   needed to answer the QUESTION? Judge the passages alone. Ignore
   whether the ANSWER is any good.

2. answer_grounded - is every factual claim in the ANSWER supported by
   the CONTEXT? An answer that correctly says it does not know is
   grounded. An answer stating anything absent from the CONTEXT is not.

Reply with JSON only:
{{"context_sufficient": true/false, "answer_grounded": true/false, "reason": "one sentence"}}

QUESTION:
{question}

CONTEXT:
{context}

ANSWER:
{answer}

JSON:"""


def classify_with_judge(question, trace, answer, model=None):
    """
    Verdict for an unlabelled question.

    The judge is asked the two questions separately and on purpose:
    conflating "was the context good?" with "was the answer good?" is
    exactly the confusion this module exists to remove.
    """

    context = "\n\n".join(
        f"[{chunk.source} p.{chunk.page_start}-{chunk.page_end}]\n{chunk.text}"
        for chunk in trace.final
    ) or "(no passages were retrieved)"

    refused = answer_refuses(answer)

    if not trace.final:

        return Diagnosis(
            label=RETRIEVAL_FAILURE,
            reason="Nothing survived retrieval, so there was nothing to answer from.",
            context_sufficient=False,
            refused=refused,
        )

    try:
        response = get_client().chat.completions.create(
            model=model or UTILITY_MODEL,
            temperature=0,
            max_tokens=300,
            response_format={"type": "json_object"},
            messages=[{
                "role": "user",
                "content": JUDGE_PROMPT.format(
                    question=question,
                    context=context,
                    answer=answer or "(no answer)"
                )
            }]
        )

        verdict = json.loads(response.choices[0].message.content or "{}")

    except (OpenAIError, json.JSONDecodeError, ValueError) as error:

        return Diagnosis(
            label=OK,
            reason=f"Judge unavailable ({error}); no verdict.",
            refused=refused,
        )

    sufficient = bool(verdict.get("context_sufficient"))
    grounded = bool(verdict.get("answer_grounded"))
    reason = str(verdict.get("reason", ""))

    if not sufficient:
        # The passages did not answer the question. Refusing was the
        # right move, but retrieval still failed to find the passage
        # that would have answered it. Answering anyway is the
        # hallucination case.
        label = RETRIEVAL_FAILURE if refused else MISSED_REFUSAL

    elif not grounded:
        label = GENERATION_FAILURE

    else:
        label = OK

    return Diagnosis(
        label=label,
        reason=reason,
        context_sufficient=sufficient,
        answer_grounded=grounded,
        refused=refused,
    )
