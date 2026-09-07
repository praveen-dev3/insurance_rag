"""The shared Groq client, and the retry policy around it.

Lives in its own module so that query transforms, answer generation and
the failure-separation judge can all reach it without importing each
other.

The retry policy is not incidental. The first Week 5 traffic run produced
82 traces of which 65 were the string "The language model request failed:
Error code: 429" — a whole week of traffic that was really one afternoon
of rate limiting. Nothing in the app noticed, because rag.generation
returns a failed request as the answer text rather than raising, which is
right for a CLI session and catastrophic for a trace corpus: it turns an
outage into 65 apparently-terrible answers, and the taxonomy built on them
would have described Groq's free tier rather than the claims assistant.

So 429s are retried here, honouring the wait the API asks for, and a
request that still cannot be served raises instead of being smuggled
downstream as content.

Why the `openai` client against Groq's base URL, rather than the `groq`
SDK: Groq exposes an OpenAI-compatible endpoint, so pointing the OpenAI
client at it makes a move to OpenAI, Together or a local vLLM server a
change of GROQ_BASE_URL and a model name. The vendor SDK would have bought
nothing and cost that portability.
"""

import random
import re
import time

from openai import OpenAI, RateLimitError

from rag.config import (
    GROQ_BASE_URL,
    MAX_RATE_LIMIT_WAIT,
    RATE_LIMIT_RETRIES,
    require_api_key,
)

_client = None

# Groq states the wait in the error body: "Please try again in 1m28.992s".
# Reading it is strictly better than backing off blindly, because the
# free-tier daily bucket refills at a trickle and a doubling backoff either
# overshoots by minutes or gives up while the answer was seconds away.
RETRY_AFTER = re.compile(
    r"try again in\s*(?:(\d+)m)?\s*([\d.]+)s", re.IGNORECASE
)


def get_client():
    """
    Build the client on first use.

    Deferred so that importing the package — during indexing, or in the
    evaluator's retrieval-only mode — does not require credentials.

    `max_retries=0`: the SDK's own retry is disabled because it backs off
    on a schedule of its own choosing and swallows the body that says how
    long to actually wait. Retrying is handled by `complete` below, which
    reads it.
    """

    global _client

    if _client is None:
        _client = OpenAI(
            base_url=GROQ_BASE_URL,
            api_key=require_api_key(),
            # Generous, because it has to cover the slowest thing sent
            # through this client: a claim summary over several long policy
            # blocks, with reasoning tokens on top. A tight timeout here
            # would turn a slow-but-fine request into a failure, and a
            # failure is recorded as a bad answer.
            timeout=120.0,
            max_retries=0,
        )

    return _client


def parse_retry_after(error):
    """Seconds the API asked us to wait, or None if it did not say."""

    match = RETRY_AFTER.search(str(error))

    if not match:
        return None

    minutes = float(match.group(1) or 0)

    return minutes * 60 + float(match.group(2))


def complete(on_wait=None, **request):
    """
    One chat completion, retrying rate limits rather than returning them.

    Raises RateLimitError if the wait the API asks for exceeds
    MAX_RATE_LIMIT_WAIT, or if the retries run out. Raising is deliberate:
    a caller that wants to record a failure can catch it, but nothing
    should be able to mistake a rate limit for a model output without
    saying so.

    `on_wait` is called with the number of seconds before each sleep, so a
    batch job can report that it is waiting rather than appearing hung.
    """

    last_error = None

    # `+ 1` because RATE_LIMIT_RETRIES counts *retries*, not attempts: the
    # first pass through the loop is the original request.
    for attempt in range(RATE_LIMIT_RETRIES + 1):

        try:
            return get_client().chat.completions.create(**request)

        except RateLimitError as error:

            last_error = error

            if attempt == RATE_LIMIT_RETRIES:
                break

            wait = parse_retry_after(error)

            if wait is None:
                # Only reached when the error body did not name a wait -
                # the fallback, not the plan. Exponential so a genuinely
                # busy minute is not hammered, capped at 30s because past
                # that the parsed wait would almost certainly have been
                # present and this is guesswork either way.
                wait = min(2 ** attempt, 30)

            # Jitter, so that a batch which hit the limit together does not
            # come back through the door together. 1.5s is wide enough to
            # de-synchronise a batch of ~25 and small enough to be noise
            # against waits the API states in minutes.
            wait += random.uniform(0, 1.5)

            if wait > MAX_RATE_LIMIT_WAIT:
                raise

            if on_wait is not None:
                on_wait(wait)

            time.sleep(wait)

    raise last_error
