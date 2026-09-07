"""Shared plumbing for the agent and the workflow: the LLM client, token/
cost accounting, the result shape both race entrants return, and grading.

Deliberately does not import rag.llm or rag.config. Both are otherwise
reusable - rag.llm.complete has the retry-after parsing this file's
call_llm re-derives a smaller version of - but importing anything under
the rag package runs rag/__init__.py, which imports rag.engine, which
imports chromadb and sentence-transformers. Task Set D is racing an agent
loop against a workflow over three tool calls; it has no reason to load
the embedding and reranking stack to do that, so this module talks to
Groq directly with its own client.
"""

import os
import re
import time
from dataclasses import dataclass, field

from dotenv import load_dotenv
from openai import BadRequestError, OpenAI, RateLimitError

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# Same default as rag.config.LLM_MODEL, read independently so this module
# has no import-time dependency on rag.config - see the module docstring.
MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-20b")
REASONING_EFFORT = os.getenv("REASONING_EFFORT", "low")

# Groq's listed price for openai/gpt-oss-20b as of 2026-09: $0.075 / 1M
# input tokens, $0.30 / 1M output tokens (reasoning tokens bill as
# output). Cost is an estimate on that rate, not an invoice line.
INPUT_PRICE_PER_M = 0.075
OUTPUT_PRICE_PER_M = 0.30

_client = None


def get_client():

    global _client

    if _client is None:
        if not GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY environment variable is not set.")

        _client = OpenAI(base_url=GROQ_BASE_URL, api_key=GROQ_API_KEY, timeout=60.0, max_retries=0)

    return _client


RETRY_AFTER = re.compile(r"try again in\s*(?:(\d+)m)?\s*([\d.]+)s", re.IGNORECASE)


def _parse_retry_after(error):
    match = RETRY_AFTER.search(str(error))
    if not match:
        return None
    minutes = float(match.group(1) or 0)
    return minutes * 60 + float(match.group(2))


def call_llm(**request):
    """One chat completion, honouring Groq's stated 429 wait.

    openai/gpt-oss-20b's free tier caps at 8,000 tokens per minute (see
    rag.config.LLM_MODEL's comment) and this race makes on the order of a
    hundred calls across 10 claims x 2 systems x several laps, so hitting
    that cap mid-race is the normal case, not an edge case - reading the
    wait Groq states rather than guessing is what keeps that from turning
    into either a spurious failure or a much longer blind backoff.

    Also retries a `tool_use_failed` BadRequestError, which is Groq's
    gpt-oss models occasionally leaking a `<|channel|>...` harmony-format
    token into a tool call's name mid-conversation - a sampling glitch,
    not a shape problem with this request, and resampling the same call
    usually clears it.
    """

    last_error = None

    for attempt in range(8):
        try:
            return get_client().chat.completions.create(**request)
        except RateLimitError as error:
            last_error = error
            if attempt == 7:
                break
            wait = _parse_retry_after(error) or min(2 ** attempt, 30)
            time.sleep(wait + 0.5)
        except BadRequestError as error:
            if "tool_use_failed" not in str(error) or attempt == 2:
                raise
            last_error = error

    raise last_error


def cost_usd(prompt_tokens, completion_tokens):
    return (
        prompt_tokens / 1_000_000 * INPUT_PRICE_PER_M
        + completion_tokens / 1_000_000 * OUTPUT_PRICE_PER_M
    )


_JSON_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)


def extract_json_obj(text):
    """Pull the first balanced-looking {...} block out of model output.

    Both systems are asked for a fenced JSON object but a small model at
    low reasoning effort sometimes wraps it in a sentence anyway; matching
    greedily from the first '{' to the last '}' is one regex instead of a
    hand-rolled brace counter, and is safe here because the model only
    ever emits one JSON object per final answer.
    """

    import json

    match = _JSON_OBJ_RE.search(text or "")

    if not match:
        return None

    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


@dataclass
class Budget:
    """The four budgets Task Set D §2.4 requires enforced in code.

    Sized from the real c04 run (the deepest of the 10 claims: get_claim,
    two search_policy calls, a redirect that doubles both, compute_payout,
    then the final answer - 6 laps, ~12k tokens, ~30s including one 429
    wait): generous enough that a normal claim never trips a budget, so
    the budget-termination log in eval/w7d/budget_termination.log has to
    come from a deliberately tiny budget (see w7d_race.py's budget_demo)
    rather than from these defaults ever misfiring on a real run.
    """

    max_iterations: int = 10
    max_tokens: int = 16000
    max_cost_usd: float = 0.02
    max_wall_clock_s: float = 90.0


DEFAULT_BUDGET = Budget()


@dataclass
class RunResult:
    """What both run_agent() and run_workflow() return.

    Same shape for both on purpose - race() diffs the two systems field by
    field, and a race between two different result shapes would need a
    translation layer that could itself hide a discrepancy.
    """

    system: str
    claim_id: str
    outcome: str  # "completed" | "budget_exceeded" | "error"
    budget_reason: str | None = None
    coverage_status: str | None = None
    exclusion_code: str | None = None
    deductible: float | None = None
    payout: float | None = None
    iterations: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    wall_clock_s: float = 0.0
    tool_calls: list = field(default_factory=list)
    transcript: list = field(default_factory=list)
    raw_final: dict | None = None

    @property
    def total_tokens(self):
        return self.prompt_tokens + self.completion_tokens

    @property
    def cost_usd(self):
        return cost_usd(self.prompt_tokens, self.completion_tokens)


def grade(result, golden):
    """Pass iff the coverage call is right AND the payout is right.

    Exclusion-code agreement is recorded but does not gate pass/fail: an
    adjuster's downstream system only ever consumes the status and the
    dollar figure, and gating on the exact code would fail a run that
    reached the right business outcome by citing E-14's neighbour E-12 in
    its rationale - a real but different bug from getting the money wrong.
    """

    if result.outcome != "completed":
        return False, f"did not complete ({result.budget_reason})"

    if result.coverage_status != golden["status"]:
        return False, f"status {result.coverage_status!r} != {golden['status']!r}"

    expected_payout = golden["payout"]
    actual_payout = result.payout

    if actual_payout is None or abs(actual_payout - expected_payout) > 1:
        return False, f"payout {actual_payout!r} != {expected_payout!r}"

    return True, "ok"
