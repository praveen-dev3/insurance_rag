"""Claim summaries written from adjuster notes, backed by policy wording.

This is the feature Week 6 measures. An adjuster pastes their notes; the
app retrieves the policy wording those notes engage and writes a summary
that states a coverage position. That summary is what claims ops wants to
route work by, which is why a summary that invents coverage is not a
quality problem but a payout that should not have happened.

The output format is fixed-field on purpose. Two different readers have to
consume it and they need opposite things:

  * the deterministic assertions in rag/assertions.py need to find the
    claim number, the date of loss, the deductible and any exclusion code
    without asking a model where they are;
  * the judge needs prose it can reason about.

A labelled block followed by a free narrative gives both, and costs the
model nothing it was not already doing. The alternative — JSON — would
make the assertions trivial and the judge's job harder, because the thing
being judged is whether the *reasoning* overstates coverage, and reasoning
does not survive being flattened into fields.

Nothing here decides whether a summary is any good. That is deliberately
split: assertions in rag/assertions.py, the single judged criterion in
rag/judge.py. Mixing the two is how you end up paying a model to check a
date format.
"""

import re
from dataclasses import asdict, dataclass, field

from openai import OpenAIError

from rag.config import LLM_MODEL, REASONING_EFFORT
from rag.generation import GENERATION_ERROR
from rag.llm import complete
from rag.retrieval import format_pages

# Bumped whenever SUMMARY_PROMPT changes. Recorded in every trace, so a
# behaviour change can be attributed to a prompt edit instead of being
# argued about. rag.tracing also stores a hash of the template, because a
# version string that someone forgot to bump is worse than none.
SUMMARY_PROMPT_VERSION = "summary-v1"

# The sentence the model emits when the retrieved wording does not settle
# the coverage question. Matched by string downstream rather than judged,
# so "it declined" is never a matter of opinion.
UNDETERMINED = "Coverage position could not be determined from the retrieved policy wording."


@dataclass
class ClaimFile:
    """
    One claim as it arrives from the claims system.

    `claim_number`, `claimant` and `date_of_loss` are carried as fields
    rather than left inside the notes because both the redactor and the
    assertions need them as data. Parsing them back out of free text would
    make the privacy control depend on a regex getting lucky.
    """

    claim_id: str
    claim_number: str
    claimant: str
    date_of_loss: str
    policy_line: str
    notes: str
    form_number: str | None = None
    reported_date: str | None = None
    tags: list = field(default_factory=list)

    def as_dict(self):
        return asdict(self)

    def redacted(self, redactor):
        """
        The same claim with the claimant and claim number pseudonymised.

        Applied at the point the claim enters the app, before retrieval
        and before the model call — not on the way to the trace file. Two
        things follow from that ordering and both are worth having:

          * the real claimant name and the real claim number never leave
            the process, so they are not in a third-party API's logs
            either. Redacting at the trace boundary would protect the file
            on disk and nothing else;
          * the trace becomes exactly replayable. If the model saw the
            real number and the trace stored a surrogate, a replay would
            re-run with different input and the diff would show a
            difference that the app never produced.

        rag.tracing.TraceWriter still verifies at the write boundary. That
        is not redundant — it is the check that catches a future call site
        that forgets to call this.
        """

        return ClaimFile(
            claim_id=self.claim_id,
            claim_number=redactor.register_claim_number(self.claim_number),
            claimant=redactor.register_name(self.claimant),
            date_of_loss=self.date_of_loss,
            policy_line=self.policy_line,
            notes=redactor.redact(self.notes)[0],
            form_number=self.form_number,
            reported_date=self.reported_date,
            tags=list(self.tags),
        )

    def search_query(self):
        """
        What to retrieve on.

        The notes verbatim, with the form number prepended when the claim
        record names one. Prepending it is not a trick: the claim file
        really does say which form is attached, and withholding that from
        the retriever would be measuring a harder problem than the app
        actually has.

        The file header is deliberately NOT part of the query. A claim
        number and a claimant name are high-entropy tokens that BM25 will
        happily rank on, and there is nothing in the policy wording for
        them to match — so including them spends retrieval budget pulling
        whichever chunk happens to share a digit.
        """

        prefix = f"{self.form_number} " if self.form_number else ""

        return f"{prefix}{self.notes}".strip()

    def as_pasted(self):
        """
        The claim exactly as it reaches the model: file header, then notes.

        The header is not decoration. `claim_number` and `date_of_loss`
        are fields on the claim record, and the downstream assertions
        check that the summary echoed them — so if they never reach the
        prompt, every summary fails those assertions for a reason that has
        nothing to do with summary quality, and the assertion measures the
        harness instead of the app. This is what an adjuster actually
        pastes: the file header their claims system prints, followed by
        what they typed.
        """

        header = [
            f"Claim number: {self.claim_number}",
            f"Claimant: {self.claimant}",
            f"Date of loss: {self.date_of_loss}",
            f"Policy line: {self.policy_line}",
            f"Form attached: {self.form_number or 'not recorded'}",
        ]

        if self.reported_date:
            header.append(f"Date reported: {self.reported_date}")

        return "\n".join(header) + "\n\nAdjuster notes:\n" + self.notes.strip()


SUMMARY_PROMPT = """You are a claims adjuster's assistant. Write a claim summary from the
ADJUSTER NOTES below, using the POLICY WORDING blocks as the only source
for any statement about coverage.

RULES:

1. Every statement about what the policy covers, excludes, limits or
   requires must come from a POLICY WORDING block. Do not use outside
   knowledge of how insurance usually works. If the wording does not
   settle the point, say so.

2. An exclusion code (E-17, E-44, ...) means nothing without the form that
   scopes it. Only cite a code that appears in a POLICY WORDING block, and
   name the form_number and edition from that same block. Codes are reused
   across policy lines with different dispositions, so a code read from a
   block belonging to a different policy_line than the claim is not
   authority for this claim.

3. Preserve conditions. "Covered provided that X" is not "covered". If a
   condition is stated in the wording and the notes do not say whether it
   is met, the summary must say the condition is unresolved.

4. If the POLICY WORDING blocks do not settle the coverage question, set
   the coverage position to UNDETERMINED and write exactly this sentence
   as the first line of the narrative:

   "{undetermined}"

Reply in exactly this layout, with these field labels, and nothing before
or after it:

CLAIM SUMMARY
Claim number: <the claim number from the notes, copied verbatim>
Date of loss: <the date of loss from the notes, as YYYY-MM-DD>
Policy line: <the policy line from the notes>
Coverage position: <COVERED or DENIED or UNDETERMINED>
Exclusion relied on: <the exclusion code and the form that scopes it, or NONE>
Deductible: <the deductible or excess amount that applies, or UNKNOWN>
Narrative: <three to six sentences: what happened, what the wording says,
what follows, and what is still outstanding. Cite each coverage statement
as [chunk_id=<chunk_id copied verbatim> | <form_number> | <clause>].>

POLICY WORDING:

{context}

ADJUSTER NOTES:

{notes}

CLAIM SUMMARY:
"""


def build_context(chunks):
    """
    Render the retrieved chunks as citable POLICY WORDING blocks.

    policy_line is printed on every block because the corpus deliberately
    carries near-identical exclusions on two lines — E-17 on homeowners and
    E-71 on dwelling fire say nearly the same thing and dispose of it
    differently. A model that cannot see which line a block belongs to
    cannot avoid the mistake, and blaming it for making one would be
    blaming it for a missing field.
    """

    if not chunks:
        return "(no policy wording was retrieved)"

    blocks = []

    for index, chunk in enumerate(chunks, start=1):

        blocks.append(
            f"""
POLICY WORDING {index}
chunk_id: {chunk.id}
form_number: {chunk.form_number} (edition {chunk.edition_date})
policy_line: {chunk.policy_line}
clause: {chunk.clause_label}
document: {chunk.source_file}
page: {format_pages(chunk)}

{chunk.text}
"""
        )

    return "\n".join(blocks)


def build_summary_prompt(claim, chunks):
    """Render one claim and its retrieved wording into the user message."""

    return SUMMARY_PROMPT.format(
        undetermined=UNDETERMINED,
        context=build_context(chunks),
        notes=claim.as_pasted() if isinstance(claim, ClaimFile) else claim,
    )


def generate_summary(claim, chunks, model=None, temperature=0, seed=None,
                     on_wait=None):
    """
    Produce one claim summary. Returns (text, model_params, usage).

    The model parameters are returned rather than assumed by the caller so
    that the trace records what was actually sent — including the fallback
    when `seed` is not supported by the endpoint, which is the kind of
    silent difference that makes a replay diverge and look like a bug in
    the app.
    """

    params = {
        "id": model or LLM_MODEL,
        "temperature": temperature,
        "reasoning_effort": REASONING_EFFORT,
        "seed": seed,
        "max_tokens": None,
        "top_p": None,
    }

    request = {
        "model": params["id"],
        "temperature": temperature,
        "reasoning_effort": REASONING_EFFORT,
        "messages": [{
            "role": "user",
            "content": build_summary_prompt(claim, chunks),
        }],
    }

    if seed is not None:
        request["seed"] = seed

    try:
        response = complete(on_wait=on_wait, **request)
    except OpenAIError as error:
        # Returned, not raised, for the same reason rag.generation does it:
        # one failed request must not take down a batch of 25. Callers
        # separate this from a bad summary with is_generation_error.
        return f"{GENERATION_ERROR} {error}", params, None

    usage = getattr(response, "usage", None)

    return (
        response.choices[0].message.content,
        params,
        {
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
        } if usage else None,
    )


# ============================================================
# PARSING THE FIXED FIELDS BACK OUT
# ============================================================

FIELD_LABELS = (
    "Claim number",
    "Date of loss",
    "Policy line",
    "Coverage position",
    "Exclusion relied on",
    "Deductible",
    "Narrative",
)


def parse_summary(text):
    """
    Pull the labelled fields out of a summary.

    Tolerant of the model bolding a label or changing its capitalisation,
    strict about the label itself. A missing field comes back as None
    rather than an empty string, so an assertion can distinguish "the model
    wrote nothing there" from "the model wrote the field and left it
    blank" — those are different defects and only one is a formatting
    problem.
    """

    fields = dict.fromkeys(FIELD_LABELS)

    if not text:
        return fields

    # Labels may be preceded by markdown emphasis and followed by a colon
    # that the model sometimes puts inside the emphasis.
    pattern = re.compile(
        r"^\s*[*_#\s]*(" + "|".join(re.escape(l) for l in FIELD_LABELS) + r")"
        r"[*_\s]*:\s*(.*)$",
        re.IGNORECASE | re.MULTILINE,
    )

    matches = list(pattern.finditer(text))

    for index, match in enumerate(matches):

        label = next(
            l for l in FIELD_LABELS
            if l.lower() == match.group(1).strip().lower()
        )

        # The narrative runs to the end of the document or to the next
        # label, whichever comes first; every other field is one line.
        end = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else len(text)
        )

        value = (
            text[match.start(2):end] if label == "Narrative"
            else match.group(2)
        )

        fields[label] = value.strip() or None

    return fields


def coverage_position(text):
    """COVERED / DENIED / UNDETERMINED, or None if the field is absent."""

    value = (parse_summary(text).get("Coverage position") or "").upper()

    for position in ("UNDETERMINED", "DENIED", "COVERED"):
        if position in value:
            return position

    return None
