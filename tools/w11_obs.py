"""Week 11 observability: one request log line per request, spans inside it.

A request log answers "what happened to *this* request" without anyone
having to remember a trace id. The complaint this module exists for - "an
adjuster says it told a claimant something was covered when the policy
excludes it, sometime yesterday" - arrives with no id, no claim number and
no timestamp, so every field a person would reasonably describe a request
by has to be a field the log can be sliced on: when (ts), who (user_id),
which prompt (prompt_version), what kind of request (input_type), how much
it cost (totals.cost_usd), and what it *said* (output.text, indexed).

Two decisions are load-bearing, both inherited from rag/tracing.py rather
than reinvented:

**Redaction happens on write.** `RequestSink.write` runs the record through
the same `Redactor` the Week 5 trace writer uses and then `verify`s it,
refusing the write if a registered name or claim number survives. The
adjuster note is never stored at all - only its sha256 and length - because
the cheapest PII control is not having the field. The *output* is stored
(redacted), since the complaint is about what the system said.

**Retrieved context ids are logged per request.** Without them a wrong
coverage call is a two-day mystery (did retrieval miss the exclusions
schedule, or did the model ignore it?). With them it is one hop: look at
`context_ids`, see whether an exclusion row is in there.

rag/tracing.py is loaded by file path rather than `import rag.tracing`:
importing anything under `rag` runs rag/__init__.py, which pulls in
chromadb and sentence-transformers - the same reason w7d_common.py talks to
Groq directly.
"""

import hashlib
import importlib.util
import json
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from w7d_common import INPUT_PRICE_PER_M, OUTPUT_PRICE_PER_M

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOG_PATH = REPO_ROOT / "traces" / "requests.jsonl"

LOG_SCHEMA_VERSION = "2"

# The three buckets cost_by_stage.md reports. "retrieval" is the policy
# search, "generation" is every model call, "tools" is everything else the
# agent called (claim lookup, payout arithmetic, referral). Fixed here so a
# span cannot invent a fourth bucket that the cost report then silently
# drops.
STAGES = ("retrieval", "generation", "tools")

# USD per million tokens (input, output), by model. gpt-oss-20b is the rate
# quoted in tools/w7d_common.py; gpt-oss-120b is Groq's published list price
# as recalled when this was written and should be re-checked before the
# figure is used for anything but a ratio. Unknown models fall back to the
# 20b rate, which understates the cost of a larger one.
PRICES = {
    "openai/gpt-oss-20b": (INPUT_PRICE_PER_M, OUTPUT_PRICE_PER_M),
    "openai/gpt-oss-120b": (0.15, 0.60),
}


def cost_for(model, tokens_in, tokens_out):
    price_in, price_out = PRICES.get(model, PRICES["openai/gpt-oss-20b"])

    return tokens_in / 1_000_000 * price_in + tokens_out / 1_000_000 * price_out


def _load_redaction_module():
    spec = importlib.util.spec_from_file_location(
        "rag_tracing_by_path", REPO_ROOT / "rag" / "tracing.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_tracing = _load_redaction_module()
Redactor = _tracing.Redactor
prompt_fingerprint = _tracing.prompt_fingerprint
sha256_short = _tracing.sha256_short


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class RequestTrace:
    """One request's spans, built up as the request runs.

    Spans are flat and carry their own start offset rather than nesting:
    a flat list is greppable and sums trivially by stage, and the tree shape
    of an agent loop (lap -> tool) is recoverable from `lap` in attrs.
    """

    def __init__(self, user_id, input_type, prompt_version, retrieval_version,
                 model, claim_number=None, trace_id=None, ts=None):

        self.trace_id = trace_id or f"req-{uuid.uuid4().hex[:12]}"
        self.ts = ts or now_iso()
        self.user_id = user_id
        self.input_type = input_type
        self.prompt_version = prompt_version
        self.retrieval_version = retrieval_version
        self.model = model
        self.claim_number = claim_number
        self.spans = []
        self.context_ids = []
        self.input = {}
        self.output = {}
        self.outcome = "error"
        self.extra = {}
        self.tool_calls = []
        self.server_spans = []
        self._t0 = time.perf_counter()

    # ----------------------------------------------------------

    @contextmanager
    def span(self, name, stage, **attrs):
        """
        Time one unit of work. The caller fills `span["tokens_in"]` etc.

        Yields the span dict so tokens can be set after the call returns,
        which is the only point they are known. The span is appended in a
        `finally`, so a call that raised is still in the log with its
        latency - the slow failing span is the one worth seeing.
        """

        if stage not in STAGES:
            raise ValueError(f"unknown stage {stage!r}; expected one of {STAGES}")

        record = {
            "span_id": f"sp-{len(self.spans) + 1:02d}",
            "name": name,
            "stage": stage,
            "t_start_ms": round((time.perf_counter() - self._t0) * 1000, 1),
            "latency_ms": 0.0,
            "tokens_in": 0,
            "tokens_out": 0,
            "cost_usd": 0.0,
            "attrs": dict(attrs),
        }

        start = time.perf_counter()

        try:
            yield record
        finally:
            record["latency_ms"] = round((time.perf_counter() - start) * 1000, 1)

            if record["tokens_in"] or record["tokens_out"]:
                record["cost_usd"] = round(
                    cost_for(self.model, record["tokens_in"], record["tokens_out"]), 6
                )

            self.spans.append(record)

    def add_context(self, ids):
        for chunk_id in ids:
            if chunk_id not in self.context_ids:
                self.context_ids.append(chunk_id)

    # ----------------------------------------------------------

    def totals(self):
        by_stage = {stage: {"latency_ms": 0.0, "tokens_in": 0, "tokens_out": 0,
                            "cost_usd": 0.0, "spans": 0} for stage in STAGES}

        for span in self.spans:
            bucket = by_stage[span["stage"]]
            bucket["latency_ms"] = round(bucket["latency_ms"] + span["latency_ms"], 1)
            bucket["tokens_in"] += span["tokens_in"]
            bucket["tokens_out"] += span["tokens_out"]
            bucket["cost_usd"] = round(bucket["cost_usd"] + span["cost_usd"], 6)
            bucket["spans"] += 1

        return {
            "latency_ms": round((time.perf_counter() - self._t0) * 1000, 1),
            "tokens_in": sum(s["tokens_in"] for s in self.spans),
            "tokens_out": sum(s["tokens_out"] for s in self.spans),
            "cost_usd": round(sum(s["cost_usd"] for s in self.spans), 6),
            "by_stage": by_stage,
        }

    def to_record(self):
        return {
            "log_schema": LOG_SCHEMA_VERSION,
            "trace_id": self.trace_id,
            "ts": self.ts,
            "user_id": self.user_id,
            "input_type": self.input_type,
            "claim_number": self.claim_number,
            "prompt_version": self.prompt_version,
            "retrieval_version": self.retrieval_version,
            "model": self.model,
            "input": self.input,
            "context_ids": self.context_ids,
            "spans": self.spans,
            "totals": self.totals(),
            "output": self.output,
            "outcome": self.outcome,
            **({"extra": self.extra} if self.extra else {}),
        }


def notes_digest(notes):
    """
    What the log keeps of an adjuster note: a hash and a length.

    Enough to tell that two requests were about the same note and that a
    note was long, not enough to read it. Storing the note "so the trace is
    searchable" is the mistake the Week 11 brief names: the claimant's
    description of their own injury would cross the line drawn in Week 5.
    """

    return {
        "notes_sha256": hashlib.sha256((notes or "").encode("utf-8")).hexdigest()[:16],
        "notes_chars": len(notes or ""),
    }


class RequestSink:
    """Append-only JSONL, redacted and verified before every write."""

    def __init__(self, path=None, redactor=None, enrich=None):

        self.path = Path(path or DEFAULT_LOG_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.redactor = redactor or Redactor()
        self.enrich = enrich
        self._lock = threading.Lock()

    def register_claim(self, claim_number, claimant=None):
        self.redactor.register_claim_number(claim_number)
        if claimant:
            self.redactor.register_name(claimant)

    def write(self, trace_or_record):

        record = (
            trace_or_record.to_record()
            if isinstance(trace_or_record, RequestTrace)
            else trace_or_record
        )

        with self._lock:

            redacted, counts = self.redactor.walk(record)
            redacted["redaction"] = {
                "stage": "before_write",
                "names_replaced": counts["names"],
                "claim_numbers_replaced": counts["claim_numbers"],
            }

            # Derived fields are computed on the redacted record, after the
            # redaction verify, so a derived field can never be the thing
            # that smuggles an identifier back in.
            if self.enrich is not None:
                redacted = self.enrich(redacted)

            self.redactor.verify(redacted)

            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(redacted, default=str) + "\n")

            return redacted


def read_log(path=None):
    path = Path(path or DEFAULT_LOG_PATH)

    if not path.exists():
        return []

    rows = []

    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))

    return rows
