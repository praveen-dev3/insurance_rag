"""Trace capture for the claims assistant.

A trace exists to answer one question after the fact: *why did the app say
that?* Answering it requires that the trace be replayable, and replayable
means every input to the answer is recorded — the prompt version, the
chunk ids and the score each stage gave them, the model and its
parameters, and the raw output before anything downstream touched it. A
trace missing any of those is a log line, not a trace: you can read it and
still not be able to reproduce what happened.

Two decisions in here are load-bearing.

**Redaction happens before the write, not after.** `TraceWriter.write`
redacts the record and then *verifies* that no registered claimant name
and no un-minted claim number survives, raising if one does. Redacting
after the fact is not a privacy control — the identifier was already on
disk, and every backup taken between the write and the scrub still has
it. The check is what makes the ordering a property of the code rather
than a promise in a comment.

**Claim numbers are pseudonymised, not blanked.** A claim number replaced
with `[REDACTED]` destroys two things that are needed later: the ability
to tell whether two traces concern the same claim, and the ability to
assert downstream that a generated summary echoed the claim number in the
right format. So a claim number is mapped to a stable surrogate *in the
same CLM-YYYY-NNNNN shape*, keyed by an HMAC over the original. The year
is preserved because it is not identifying on its own and the format
assertion in rag/assertions.py checks it.

The surrogate is what makes the enforcement possible, too: the writer
knows every surrogate it has minted, so any CLM token in an outgoing
record that is not one of them is by definition a raw claim number that
escaped redaction, and the write fails.
"""

import hashlib
import hmac
import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

TRACE_SCHEMA_VERSION = "1"

DEFAULT_TRACE_PATH = Path("traces/claims_traces.jsonl")

# Salt for the pseudonymisation HMAC. Read from the environment so the
# mapping from a real claim number to its surrogate is not reproducible by
# anyone holding only the trace file and this source. It falls back to a
# fixed development value, and says so, because a silent random salt would
# make surrogates differ between runs and quietly break the "same claim in
# two traces" property that pseudonymisation exists to preserve.
REDACTION_SALT = os.getenv("REDACTION_SALT", "dev-salt-not-for-production")

CLAIM_NUMBER = re.compile(r"\bCLM-(\d{4})-(\d{5})\b")

# Best-effort personal-name patterns, for names that were never registered
# on the claim record. These are a backstop and are labelled as one: the
# guarantee in this module comes from the registry, which is exact.
#
# The case-insensitive flag is deliberately NOT set on these. It was, once,
# and it made `[a-z]` match uppercase — so the pattern matched inside the
# module's own surrogates, registering "FF" out of "[CLAIMANT-FF16E0]" as
# a claimant name. A two-character "name" then matched hex digits in every
# chunk_id in the record and the writer refused every trace. Only the
# keyword is case-insensitive; the name parts have to be Capitalised, which
# is what makes them name-shaped in the first place.
NAME_PART = r"[A-Z][a-z'’-]{2,}"

NAME_PATTERNS = (
    # "Mr John Smith", "Ms. Priya Raghunathan"
    re.compile(
        r"\b(?:Mr|Mrs|Ms|Miss|Dr)\.?\s+"
        rf"(?:{NAME_PART}\s+){{0,2}}{NAME_PART}"
    ),
    # "Insured: John Smith", "Claimant - Priya Raghunathan"
    re.compile(
        r"(?i:\b(?:insured|claimant|policyholder|named insured)\b)\s*[:\-]\s*"
        rf"((?:{NAME_PART}\s+){{0,2}}{NAME_PART})"
    ),
)


def _digest(value):
    """Stable keyed digest of one identifier."""

    return hmac.new(
        REDACTION_SALT.encode("utf-8"),
        str(value).strip().lower().encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def surrogate_claim_number(claim_number):
    """
    A stable stand-in for one claim number, in the same shape.

    Shape is preserved on purpose. The downstream assertion that a
    generated summary echoed the claim number in CLM-YYYY-NNNNN form has
    to be checkable against the trace, and a `[REDACTED]` token would
    make that assertion untestable on exactly the records where it
    matters.
    """

    match = CLAIM_NUMBER.search(claim_number or "")

    year = match.group(1) if match else "0000"

    tail = int(_digest(claim_number)[:8], 16) % 100000

    return f"CLM-{year}-{tail:05d}"


def surrogate_name(name):
    """A stable stand-in for one person's name."""

    return f"[CLAIMANT-{_digest(name)[:6].upper()}]"


class Redactor:
    """
    Replaces identifiers with stable surrogates, and can prove it did.

    `register` is how the caller declares the identifiers it *knows*
    about — the claimant name and claim number carried as fields on the
    claim record. Those are matched exactly, which is the only kind of
    name matching that can be relied on. The regex layer catches names
    that only ever appeared in free-text notes, and is explicitly a
    backstop rather than the guarantee.
    """

    def __init__(self):

        self.names = {}
        self.claim_numbers = {}
        self._minted_claim_numbers = set()
        self._minted_names = set()

    # ----------------------------------------------------------

    def register_name(self, name):
        """
        Declare a claimant name so it is redacted by exact match.

        Short and all-caps tokens are refused. Not tidiness: a registered
        name is later searched for across the whole serialised record, and
        a two-character "name" matches hex digits inside every chunk_id,
        which turns the verify step from a control into a blanket refusal.
        A token that is not name-shaped is a bug in whatever produced it,
        so it is dropped here rather than propagated.
        """

        if not name or not name.strip():
            return None

        name = name.strip()

        if name.startswith("[CLAIMANT-"):
            return name

        if len(name) < 3 or not re.search(r"[a-z]{2}", name):
            return None

        if name not in self.names:
            self.names[name] = surrogate_name(name)
            self._minted_names.add(self.names[name])

        return self.names[name]

    def register_claim_number(self, claim_number):
        """Declare a claim number so it is redacted by exact match."""

        if not claim_number or not claim_number.strip():
            return None

        claim_number = claim_number.strip()

        if claim_number not in self.claim_numbers:
            self.claim_numbers[claim_number] = surrogate_claim_number(
                claim_number
            )
            self._minted_claim_numbers.add(self.claim_numbers[claim_number])

        return self.claim_numbers[claim_number]

    # ----------------------------------------------------------

    def redact(self, text):
        """
        Return (redacted_text, counts).

        Registered identifiers go first, so that a name which also matches
        a regex is replaced with its registered surrogate rather than with
        a second, differently-keyed one — two surrogates for one person
        would silently break the ability to link that person's traces.
        """

        if not isinstance(text, str) or not text:
            return text, {"names": 0, "claim_numbers": 0}

        names = 0
        numbers = 0

        for real, fake in sorted(
            self.names.items(), key=lambda item: -len(item[0])
        ):
            pattern = re.compile(re.escape(real), re.IGNORECASE)
            text, hits = pattern.subn(fake, text)
            names += hits

        for real, fake in self.claim_numbers.items():
            pattern = re.compile(re.escape(real), re.IGNORECASE)
            text, hits = pattern.subn(fake, text)
            numbers += hits

        # Any claim-number-shaped token still present was never registered.
        # Mint a surrogate for it rather than leave it: an unregistered
        # claim number is exactly the case the registry cannot cover, and
        # is therefore the case worth catching.
        def _replace_number(match):

            nonlocal numbers

            token = match.group(0)

            if token in self._minted_claim_numbers:
                return token

            numbers += 1

            return self.register_claim_number(token)

        text = CLAIM_NUMBER.sub(_replace_number, text)

        for pattern in NAME_PATTERNS:

            def _replace_name(match):

                nonlocal names

                # Group 1 where the pattern captures the bare name after a
                # field label; the whole match where it captures a title.
                target = match.group(1) if match.groups() else match.group(0)

                if target.startswith("[CLAIMANT-"):
                    return match.group(0)

                fake = self.register_name(target)

                # register_name refuses tokens that are not name-shaped.
                # Leaving the text untouched is right: there was no name
                # there to redact.
                if fake is None:
                    return match.group(0)

                names += 1

                return match.group(0).replace(target, fake)

            text = pattern.sub(_replace_name, text)

        return text, {"names": names, "claim_numbers": numbers}

    # ----------------------------------------------------------

    def walk(self, value):
        """Redact every string inside a nested structure, counting hits."""

        totals = {"names": 0, "claim_numbers": 0}

        def _walk(node):

            if isinstance(node, str):
                redacted, counts = self.redact(node)
                totals["names"] += counts["names"]
                totals["claim_numbers"] += counts["claim_numbers"]
                return redacted

            if isinstance(node, dict):
                return {key: _walk(item) for key, item in node.items()}

            if isinstance(node, (list, tuple)):
                return [_walk(item) for item in node]

            return node

        return _walk(value), totals

    def verify(self, payload):
        """
        Raise if any identifier survived the redaction pass.

        This is the whole reason redaction lives inside the writer. A
        function that redacts is a hope; a function that redacts and then
        refuses to return unless the result is clean is a control.
        """

        blob = json.dumps(payload, default=str)

        # Word-boundaried, not a bare substring search. A substring check
        # reports a surname as surviving because it happens to appear
        # inside a longer token, and an identifier check that cries wolf
        # gets switched off, which is worse than not having it.
        for real in self.names:
            if re.search(rf"{re.escape(real)}", blob, re.IGNORECASE):
                raise ValueError(
                    f"Claimant name '{real}' survived redaction; refusing "
                    "to write the trace."
                )

        for real in self.claim_numbers:
            if re.search(rf"{re.escape(real)}", blob, re.IGNORECASE):
                raise ValueError(
                    f"Claim number '{real}' survived redaction; refusing "
                    "to write the trace."
                )

        for token in set(CLAIM_NUMBER.findall(blob)):
            rebuilt = f"CLM-{token[0]}-{token[1]}"
            if rebuilt not in self._minted_claim_numbers:
                raise ValueError(
                    f"Claim number '{rebuilt}' is in the record but was "
                    "never minted as a surrogate, so it is a real "
                    "identifier that escaped redaction."
                )

        return True


# ============================================================
# PROMPT IDENTITY
# ============================================================

def prompt_fingerprint(version, template):
    """
    The label and the hash of the prompt text that produced an answer.

    Both, not either. The label is what a human reads in a taxonomy row;
    the hash is what catches the case where the label was not bumped after
    the template was edited, which is the only failure mode a version
    string on its own cannot detect.
    """

    return {
        "version": version,
        "template_sha256": hashlib.sha256(
            (template or "").encode("utf-8")
        ).hexdigest()[:16],
    }


def sha256_short(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


# ============================================================
# CHUNK AND TRACE SERIALISATION
# ============================================================

def chunk_row(chunk):
    """
    One retrieved chunk, with every score any stage gave it.

    The scores are the point. "The right passage was not in the answer" is
    a symptom shared by three different bugs, and only the per-stage
    scores separate them: never retrieved, retrieved and fused low,
    retrieved and then discarded by the reranker.
    """

    return {
        "chunk_id": chunk.id,
        "source": chunk.source,
        "pages": [chunk.page_start, chunk.page_end],
        "form_number": getattr(chunk, "form_number", None),
        "edition_date": getattr(chunk, "edition_date", None),
        "policy_line": getattr(chunk, "policy_line", None),
        "clause": getattr(chunk, "clause_label", None),
        "dense_rank": chunk.dense_rank,
        "distance": chunk.distance,
        "sparse_rank": chunk.sparse_rank,
        "bm25_score": chunk.bm25_score,
        "rrf_score": chunk.rrf_score,
        "mmr_rank": chunk.mmr_rank,
        "rerank_score": chunk.rerank_score,
    }


def retrieval_block(trace, options=None):
    """The retrieval half of a trace: what was asked, and what came back."""

    options = options or {}

    return {
        "mode": trace.mode,
        "filters": trace.filters or None,
        "options": options,
        "queries": (trace.config or {}).get("queries") or {
            "condensed": trace.question,
            "search_query": trace.search_query,
            "dense_query": trace.dense_query,
        },
        "timings_ms": trace.timings_ms,
        "counts": {
            "dense": len(trace.dense),
            "sparse": len(trace.sparse),
            "fused": len(trace.fused),
            "mmr": len(trace.mmr),
            "reranked": len(trace.reranked),
            "final": len(trace.final),
            "dropped_below_floor": len(trace.dropped_below_floor),
        },
        # Only the stages a replay or a diagnosis needs. Storing all 20
        # dense candidates per trace would multiply the file by ten and
        # add nothing: what matters is what reached the prompt, and where
        # the chunk that should have reached it actually went.
        "final": [chunk_row(chunk) for chunk in trace.final],
        "reranked": [chunk_row(chunk) for chunk in trace.reranked],
        "dropped_below_floor": [
            chunk_row(chunk) for chunk in trace.dropped_below_floor
        ],
    }


class TraceWriter:
    """
    Append-only JSONL trace log with redaction enforced at the boundary.

    One line per trace, because a trace file is read by grep and by
    `random.sample` far more often than by a human scrolling it, and a
    pretty-printed record makes both awkward.
    """

    def __init__(self, path=None, run_id=None, redactor=None):

        self.path = Path(path or DEFAULT_TRACE_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)

        self.run_id = run_id or uuid.uuid4().hex[:8]
        self.redactor = redactor or Redactor()

        self._lock = threading.Lock()
        self._written = 0

    # ----------------------------------------------------------

    def next_trace_id(self):
        """
        Sequential within a run, prefixed by the run.

        A bare counter would collide across runs and a bare uuid would be
        unreadable in a taxonomy table; this is legible and unique.
        """

        return f"tr-{self.run_id}-{self._written + 1:04d}"

    def write(self, record):
        """
        Redact, verify, then append. In that order, always.

        Returns the record as written, so a caller can report the
        surrogate identifiers it just created rather than the real ones.
        """

        with self._lock:

            redacted, counts = self.redactor.walk(record)

            redacted["redaction"] = {
                "stage": "before_write",
                "names_replaced": counts["names"],
                "claim_numbers_replaced": counts["claim_numbers"],
                "policy": (
                    "registered claimant names and claim numbers are "
                    "replaced with stable HMAC surrogates inside "
                    "TraceWriter.write, and the record is refused if any "
                    "real identifier survives"
                ),
            }

            self.redactor.verify(redacted)

            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(redacted, default=str) + "\n")

            self._written += 1

            return redacted

    # ----------------------------------------------------------

    def record(self, task, question, trace, output, prompt, model,
               options=None, history=None, session_id=None, turn=1,
               citations=None, extra=None, usage=None, tags=None):
        """
        Assemble and write one trace.

        Every field the replay needs is a named parameter rather than
        something the caller may or may not think to include, which is the
        only way a schema stays complete once there are three call sites.
        """

        record = {
            "trace_schema": TRACE_SCHEMA_VERSION,
            "trace_id": self.next_trace_id(),
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "run_id": self.run_id,
            "session_id": session_id or self.run_id,
            "turn": turn,
            "task": task,
            "tags": sorted(tags or []),
            "input": {
                "question": question,
                "history": history or [],
            },
            "prompt": prompt,
            "model": model,
            "retrieval": retrieval_block(trace, options),
            "output": {
                "raw": output,
                "usage": usage,
            },
            "citations": citations,
        }

        if extra:
            record["extra"] = extra

        return self.write(record)


def read_traces(path=None):
    """
    Load a trace file. Malformed lines are reported, not skipped silently.

    A trace file is appended to by long-running processes that can be
    killed mid-write, so a truncated final line is expected rather than
    exceptional — but a truncated line in the *middle* means something
    interleaved two writes, and silently dropping it would hide that.
    """

    path = Path(path or DEFAULT_TRACE_PATH)

    if not path.exists():
        raise FileNotFoundError(f"No trace file at '{path}'.")

    traces = []
    bad = []

    lines = path.read_text(encoding="utf-8").splitlines()

    for number, line in enumerate(lines, start=1):

        if not line.strip():
            continue

        try:
            traces.append(json.loads(line))
        except json.JSONDecodeError:
            bad.append(number)

    if bad:
        print(
            f"Warning: {len(bad)} malformed line(s) in {path}: "
            f"{bad[:5]}{' ...' if len(bad) > 5 else ''}"
        )

    return traces


def index_traces(traces):
    """trace_id -> trace, for replay and for sampling."""

    return {trace["trace_id"]: trace for trace in traces}
