"""The shared Groq client.

Lives in its own module so that query transforms, answer generation and
the failure-separation judge can all reach it without importing each
other.
"""

from openai import OpenAI

from rag.config import GROQ_BASE_URL, require_api_key

_client = None


def get_client():
    """
    Build the client on first use.

    Deferred so that importing the package — during indexing, or in the
    evaluator's retrieval-only mode — does not require credentials.
    """

    global _client

    if _client is None:
        _client = OpenAI(
            base_url=GROQ_BASE_URL,
            api_key=require_api_key(),
            timeout=60.0,
            max_retries=3
        )

    return _client
