"""HTTP API for the insurance RAG, plus hosting for the React UI.

Run it with:

    uvicorn server:app --reload --port 8010

The chat endpoint streams Server-Sent Events so the browser can render
the retrieved sources immediately, then the stage-by-stage retrieval
trace, then the answer token by token — rather than staring at a spinner
for the whole round trip.

Why SSE and not the two obvious alternatives:

  * A plain JSON response would be simpler to write, and would show the
    user nothing until the last token of the answer existed. On this
    pipeline the sources are known seconds before the answer is
    finished, and the sources are the part a reader needs in order to
    judge the answer — so holding them back is the one thing worth
    engineering around.
  * WebSockets would also stream, but they buy bidirectionality this app
    never uses (the browser says nothing after the question) at the cost
    of connection state, a second protocol, and reconnection logic. SSE
    is a normal HTTP response that happens not to end yet, so it works
    through the Vite dev proxy and needs no client library.

FastAPI over bare Starlette or Flask for one specific reason: the
request models below (ChatRequest, Filters) are Pydantic, so every
pipeline knob arrives validated and in range before it can reach a model
call. Flask would mean hand-written validation for each of the eleven.

The other half of this file exists for failure *labelling*. /api/chat
returns the retrieval trace next to the answer, which is what lets a bad
result be classified as R — retrieval fetched the wrong context — versus
G — the context was right and the model misused it. Without the trace
visible, that distinction is a guess, and a guess sends you off tuning a
prompt to fix a retriever.
"""

import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from rag.config import MMR_LAMBDA, MMR_POOL, TOP_K
from rag.diagnostics import EXPLANATIONS, classify_with_judge
from rag.embeddings import get_embedder
from rag.engine import RagEngine
from rag.evaluation import load_golden_set
from rag.rerankers import RERANKERS, get_reranker
from rag.retrieval import RETRIEVAL_MODES

# The built UI is served by this same process (see the STATIC UI section
# at the bottom). One process rather than two means one URL, no CORS in
# production, and `uvicorn server:app` is the whole deployment — which
# matters more here than the flexibility of a separate static host,
# because the app is a single-user learning tool, not a fleet.
FRONTEND_DIST = Path(__file__).parent / "frontend" / "dist"

# Vite's dev server; the built UI is served from this app and needs no
# cross-origin allowance.
DEV_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


class Turn(BaseModel):
    """One previous message. Role is validated downstream, not here, so
    a malformed history degrades to fewer turns rather than a 422."""

    role: str
    content: str


class Filters(BaseModel):
    """Metadata filter. Every field optional; absent means unfiltered."""

    sources: list[str] | None = None
    policy_lines: list[str] | None = None
    form_numbers: list[str] | None = None
    edition_dates: list[str] | None = None
    page_min: int | None = None
    page_max: int | None = None

    def as_dict(self):
        """
        Drop empty values and collapse to None when nothing is set.

        `{"sources": []}` would otherwise reach the retriever as "search
        no documents" instead of "do not filter".
        """

        payload = {
            key: value
            for key, value in self.model_dump().items()
            if value not in (None, [], "")
        }

        return payload or None


class ChatRequest(BaseModel):
    """
    One question plus the pipeline configuration to answer it with.

    The configuration travels per request rather than living in server
    state so two clients can compare settings without fighting over a
    shared global — and so the trace returned alongside the answer
    describes the run that actually happened.

    Bounds are enforced here because these values reach model calls: an
    unbounded top_k is an unbounded prompt.
    """

    question: str
    history: list[Turn] = Field(default_factory=list)
    mode: str = "hybrid"

    # ge=1: zero chunks is a refusal, which the client should request by
    # not asking, not by asking for nothing. le=10 is the prompt-size
    # guard — at CHUNK_SIZE=220 tokens, ten chunks is already ~2,200
    # tokens of context, and the free-tier budget is 8,000 tokens per
    # minute. An unbounded top_k here is an unbounded bill.
    top_k: int = Field(default=TOP_K, ge=1, le=10)

    reranker: str | None = None
    use_mmr: bool = False

    # 0.0-1.0 is MMR's own definition (1.0 pure relevance, 0.0 pure
    # diversity), so anything outside it is meaningless rather than
    # merely extreme.
    mmr_lambda: float = Field(default=MMR_LAMBDA, ge=0.0, le=1.0)

    # le=50 caps the pool MMR selects from. MMR is O(n²) in the pool
    # size, and there are only RERANK_CANDIDATES=20 fused candidates to
    # draw from anyway, so 50 is a generous ceiling rather than a
    # working limit.
    mmr_pool: int = Field(default=MMR_POOL, ge=1, le=50)
    use_rewrite: bool = False
    use_hyde: bool = False
    diagnose: bool = False
    filters: Filters | None = None


# One engine for the whole process, held in a dict rather than a module
# global so lifespan() can rebind it without a `global` statement.
#
# Sharing one engine across requests is the point: it owns the Chroma
# collection and the two loaded models, which cost seconds to build. The
# per-request configuration lives on ChatRequest instead, so two clients
# with different settings share the models without sharing the settings.
state = {"engine": None, "error": None}


@asynccontextmanager
async def lifespan(app):

    try:
        engine = RagEngine()

        # Pay the model-load cost at boot instead of on the first user's
        # question.
        get_embedder()
        get_reranker().score("warmup", ["warmup"])

        state["engine"] = engine

    except Exception as error:
        # A missing corpus or an unreadable index must not stop the
        # server from starting: /api/health has to stay reachable so the
        # UI can explain what went wrong.
        state["error"] = str(error)
        print(f"Failed to initialise the RAG engine: {error}")

    yield


app = FastAPI(title="Insurance RAG", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=DEV_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_engine():
    """
    The engine, or a 503 explaining why there isn't one.

    Startup deliberately does not abort on failure, so this is where a
    broken index turns into an HTTP status instead of a dead process.
    """

    engine = state["engine"]

    if engine is None:
        raise HTTPException(
            status_code=503,
            detail=state["error"] or "The RAG engine is not ready."
        )

    return engine


# ============================================================
# API
# ============================================================

@app.get("/api/health")
def health():
    """
    Readiness plus the whole configuration surface.

    Returns 200 even when the engine failed to start, with
    `ready: false` and the error — a 503 here would leave the UI unable
    to tell "server down" from "index broken", which are very different
    things to tell the user.
    """

    engine = state["engine"]

    if engine is None:
        return {"ready": False, "error": state["error"]}

    return {
        "ready": True,
        "error": None,
        "failure_labels": EXPLANATIONS,
        **engine.stats(),
    }


def sse(event_type, payload):
    """Encode one Server-Sent Event.

    The wire format is fixed by the spec, not chosen: `data: ` prefix and
    a blank line to end the event. That trailing `\\n\\n` is what makes
    the browser dispatch it — omit it and the client waits forever for an
    event that has already been sent.

    The type travels *inside* the JSON rather than as an SSE `event:`
    field, so the browser can use the default `onmessage` handler for
    everything and switch on `data.type`. One handler, one parse.
    """

    # default=str so a stray datetime or Path in a trace cannot raise
    # mid-stream. By this point the 200 and the headers have already gone
    # out, so a serialisation error could not become an HTTP error — it
    # would just truncate the response and look like a network drop.
    body = json.dumps({"type": event_type, **payload}, default=str)

    return f"data: {body}\n\n"


@app.post("/api/chat")
def chat(request: ChatRequest):
    """
    Answer one question, streamed as Server-Sent Events.

    Defined with `def` rather than `async def` so Starlette runs it in a
    worker thread: every stage below it (Chroma, the encoders, the Groq
    client) is synchronous, and running blocking work on the event loop
    would stall every other request in the process.
    """

    engine = get_engine()

    question = request.question.strip()

    if not question:
        raise HTTPException(status_code=400, detail="Question is empty.")

    if request.mode not in RETRIEVAL_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"mode must be one of {list(RETRIEVAL_MODES)}."
        )

    if request.reranker and request.reranker not in RERANKERS:
        raise HTTPException(
            status_code=400,
            detail=f"reranker must be one of {list(RERANKERS)}."
        )

    history = [turn.model_dump() for turn in request.history]

    options = {
        "mode": request.mode,
        "top_k": request.top_k,
        "reranker": request.reranker,
        "use_mmr": request.use_mmr,
        "mmr_lambda": request.mmr_lambda,
        "mmr_pool": request.mmr_pool,
        "use_rewrite": request.use_rewrite,
        "use_hyde": request.use_hyde,
        "filters": request.filters.as_dict() if request.filters else None,
    }

    def event_stream():

        answer_parts = []
        trace = None

        try:
            for event_type, payload in engine.stream(
                question,
                history=history,
                **options
            ):

                # Order matters and is set by engine.stream(): sources,
                # then trace, then tokens. Sources first because they are
                # readable while the answer is still being written; the
                # trace next because it is what makes the answer
                # *checkable* — the UI can show which chunk each citation
                # points at before the citation itself appears.
                if event_type == "sources":
                    yield sse("sources", payload)

                elif event_type == "trace":
                    # Kept, not just forwarded: if --diagnose was asked
                    # for, the judge below needs it after the stream ends.
                    trace = payload
                    yield sse("trace", {"trace": payload})

                else:
                    answer_parts.append(payload)
                    yield sse("token", {"text": payload})

            if request.diagnose and trace is not None:
                yield sse("diagnosis", {
                    "diagnosis": _diagnose(
                        engine, question, history, options, answer_parts
                    )
                })

            # An explicit terminator. The client cannot tell a finished
            # stream from a dropped connection otherwise — both look like
            # "the socket closed" — so without this the UI would leave a
            # spinner running after a perfectly good answer.
            yield sse("done", {})

        # Caught and yielded as an event rather than raised. The response
        # status went out with the first byte of the stream, so raising
        # here cannot produce a 500 — it would abort the connection and
        # the browser would report a network error instead of the actual
        # message. An error event puts the real reason on screen.
        except Exception as error:
            yield sse("error", {"message": str(error)})

    return StreamingResponse(
        event_stream(),
        # text/event-stream is what makes the browser treat this as SSE;
        # with any other media type EventSource refuses the response.
        media_type="text/event-stream",
        headers={
            # A partial stream is not a document worth caching, and a
            # cached one would replay a stale answer.
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Stops nginx from buffering the stream into one response.
            "X-Accel-Buffering": "no",
        }
    )


def _diagnose(engine, question, history, options, answer_parts):
    """
    Re-run retrieval to get the trace objects the judge needs.

    Cheap relative to generation, and it keeps the streaming path free of
    the bookkeeping that carrying live chunk objects through the SSE
    generator would require.
    """

    queries, _, trace = engine.prepare(question, history=history, **options)

    diagnosis = classify_with_judge(
        queries["search_query"],
        trace,
        "".join(answer_parts)
    )

    return diagnosis.to_dict()


@app.post("/api/reindex")
def reindex():
    """
    Rebuild both indexes from the PDFs on disk.

    Blocking and unstreamed: it takes seconds on a corpus this size, and
    a progress stream would be more machinery than the wait justifies.
    Returns the fresh stats so the caller can update without a second
    round trip to /api/health.
    """

    engine = get_engine()

    return engine.reindex()


@app.get("/api/golden-set")
def golden_set():
    """
    The evaluation questions, so the UI can offer them as one-click
    probes with their expected pages already known.
    """

    try:
        cases = load_golden_set()
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error))

    return {
        "cases": [
            {
                "id": case.id,
                "question": case.question,
                "expected_pages": case.relevant_pages,
                "answerable": case.answerable,
                "tags": case.tags,
            }
            for case in cases
        ]
    }


@app.get("/api/eval-results")
def eval_results():
    """Serve whatever evaluate.py last wrote, for the metrics panel."""

    folder = Path("eval/results")

    if not folder.is_dir():
        return {"runs": {}}

    runs = {}

    for path in sorted(folder.glob("*.json")):

        # A half-written file — an evaluator run killed mid-save — must
        # not take down the whole metrics panel. Skipping one run is a
        # better failure than a 500 that hides the other four.
        try:
            runs[path.stem] = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

    return {"runs": runs}


# ============================================================
# STATIC UI
# ============================================================

# Guarded, because `frontend/dist` only exists after `npm run build`.
# Without the guard the API would refuse to start for anyone who has not
# built the UI — including the evaluator's author, who never needs it.
#
# This block is last in the file on purpose: the catch-all route below
# matches every path, and FastAPI resolves routes in declaration order,
# so registering it before /api/* would swallow the API.
if FRONTEND_DIST.is_dir():

    app.mount(
        "/assets",
        StaticFiles(directory=FRONTEND_DIST / "assets"),
        name="assets"
    )

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        """Serve the built single-page app for any non-API route."""

        # Without this, a typo in an API path would return the HTML shell
        # with a 200 instead of a 404, which is maddening to debug.
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Unknown endpoint.")

        candidate = (FRONTEND_DIST / full_path).resolve()

        # resolve() then is_relative_to() is the path-traversal guard:
        # a request for `../../.env` resolves outside FRONTEND_DIST and
        # fails the check. Checking the raw string for ".." instead would
        # miss the encoded and symlinked spellings; resolving first and
        # comparing real paths does not.
        if (
            full_path
            and candidate.is_file()
            and candidate.is_relative_to(FRONTEND_DIST.resolve())
        ):
            return FileResponse(candidate)

        # Anything else is treated as a client-side route: a path that
        # only exists once React has booted, so the shell is the correct
        # response. This is what makes a deep link or a browser refresh
        # work instead of 404ing on a route the server never declared.
        return FileResponse(FRONTEND_DIST / "index.html")
