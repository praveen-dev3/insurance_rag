"""Run a week of claims traffic through the app and trace every turn.

    python tools/w5_traffic.py                 # the random population
    python tools/w5_traffic.py --demo          # the curated demo set
    python tools/w5_traffic.py --limit 5       # smoke test

Nothing is evaluated here and nothing is labelled. This script exists only
to produce the trace file that Week 5 reads, and it runs the app on its
DEFAULT settings — the same mode, top_k, reranker and score floor the CLI
and the web UI use. Running the traffic under tuned settings would produce
a taxonomy of a system nobody is actually using.

The traces from the demo set are tagged `demo` and written to the same
file, so the random sample can exclude them by tag. Keeping them in a
separate file would make it too easy to sample from the wrong one, which
is the exact mistake the bonus exists to expose.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from claims_population import CLAIM_FILES, DEMO_QUESTIONS, QUESTIONS  # noqa: E402

from rag.claims import (  # noqa: E402
    SUMMARY_PROMPT,
    SUMMARY_PROMPT_VERSION,
    ClaimFile,
    build_summary_prompt,
    generate_summary,
)
from rag.config import DEFAULT_MODE, LLM_MODEL, TOP_K  # noqa: E402
from rag.engine import RagEngine  # noqa: E402
from rag.generation import (  # noqa: E402
    ANSWER_PROMPT_VERSION,
    build_prompt,
    generate_answer,
    verify_citations,
)
from rag.tracing import (  # noqa: E402
    DEFAULT_TRACE_PATH,
    Redactor,
    TraceWriter,
    prompt_fingerprint,
    sha256_short,
)

# The retrieval settings every trace in this run was produced under.
# Written into each trace rather than assumed, because a trace that does
# not say what settings produced it cannot be replayed six weeks later
# when the defaults have moved.
RUN_OPTIONS = {
    "mode": DEFAULT_MODE,
    "top_k": TOP_K,
    "use_mmr": False,
    "use_rewrite": False,
    "use_hyde": False,
    "reranker": "ms-marco",
    "filters": None,
}


def _report_wait(seconds):
    """
    Say out loud that the run is waiting on the rate limiter.

    A batch that goes quiet for two minutes looks hung, and the natural
    response to a hung batch is to kill it — which is how the first run
    ended up with 65 rate-limit errors written into the trace file as if
    they were answers.
    """

    print(f"      rate limited; waiting {seconds:.0f}s", flush=True)


def tolerate_console_encoding():

    for stream in (sys.stdout, sys.stderr):

        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def trace_question(engine, writer, item, session_id, turn, history, tags):
    """One adjuster question: retrieve, answer, trace."""

    question = item["text"]

    queries, chunks, trace = engine.prepare(
        question,
        history=history,
        mode=RUN_OPTIONS["mode"],
        top_k=RUN_OPTIONS["top_k"],
        use_mmr=RUN_OPTIONS["use_mmr"],
        use_rewrite=RUN_OPTIONS["use_rewrite"],
        use_hyde=RUN_OPTIONS["use_hyde"],
        reranker=RUN_OPTIONS["reranker"],
    )

    answer = generate_answer(
        queries["search_query"],
        chunks,
        history=history,
        on_wait=_report_wait,
    )

    rendered = build_prompt(queries["search_query"], chunks)

    return writer.record(
        task="qa",
        question=question,
        trace=trace,
        output=answer,
        prompt={
            **prompt_fingerprint(ANSWER_PROMPT_VERSION, _answer_template()),
            "rendered_sha256": sha256_short(rendered),
        },
        model={
            "id": LLM_MODEL,
            "temperature": 0,
            "seed": None,
            "max_tokens": None,
            "top_p": None,
        },
        options=RUN_OPTIONS,
        history=list(history),
        session_id=session_id,
        turn=turn,
        citations=verify_citations(answer, chunks),
        tags=tags,
        extra={"case_id": item["id"]},
    )


def _answer_template():
    """The QA prompt template with the variable parts blanked."""

    return build_prompt("<question>", [])


def trace_summary(engine, writer, record, session_id, tags):
    """
    One claim file: pseudonymise, retrieve on the notes, summarise, trace.

    The claim is redacted before it touches retrieval or the model, so the
    identifiers never leave the process and the trace is an exact record
    of the inputs the model actually saw.
    """

    claim = ClaimFile(**record).redacted(writer.redactor)

    queries, chunks, trace = engine.prepare(
        claim.search_query(),
        mode=RUN_OPTIONS["mode"],
        top_k=RUN_OPTIONS["top_k"],
        use_mmr=RUN_OPTIONS["use_mmr"],
        use_rewrite=RUN_OPTIONS["use_rewrite"],
        use_hyde=RUN_OPTIONS["use_hyde"],
        reranker=RUN_OPTIONS["reranker"],
    )

    summary, params, usage = generate_summary(
        claim, chunks, on_wait=_report_wait
    )

    rendered = build_summary_prompt(claim, chunks)

    return writer.record(
        task="summary",
        question=claim.as_pasted(),
        trace=trace,
        output=summary,
        prompt={
            **prompt_fingerprint(SUMMARY_PROMPT_VERSION, SUMMARY_PROMPT),
            "rendered_sha256": sha256_short(rendered),
        },
        model=params,
        options=RUN_OPTIONS,
        session_id=session_id,
        turn=1,
        citations=verify_citations(summary, chunks),
        usage=usage,
        tags=tags,
        extra={
            "case_id": claim.claim_id,
            # The claim record as the app received it, minus the notes
            # which are already in `input.question`. Redacted on the way
            # out like everything else, so the surrogate claim number in
            # here is the same surrogate that appears in the output — which
            # is what makes the Week 6 "did it echo the claim number"
            # assertion checkable against the trace.
            "claim": {
                "claim_id": claim.claim_id,
                "claim_number": claim.claim_number,
                "claimant": claim.claimant,
                "date_of_loss": claim.date_of_loss,
                "policy_line": claim.policy_line,
                "form_number": claim.form_number,
            },
        },
    )


def main():

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true",
                        help="Run the curated demo set instead.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--out", default=str(DEFAULT_TRACE_PATH))
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()

    tolerate_console_encoding()

    engine = RagEngine()

    print(f"Index: {engine.chunk_count} chunks.")

    redactor = Redactor()

    # Every claimant name and claim number the claims system knows about is
    # registered up front, so redaction matches on the identifier rather
    # than on a pattern that happens to catch it. This is the half of the
    # redaction that carries a guarantee.
    for record in CLAIM_FILES:
        redactor.register_name(record["claimant"])
        redactor.register_claim_number(record["claim_number"])

    writer = TraceWriter(
        path=args.out,
        run_id=args.run_id or ("demo" if args.demo else "wk5"),
        redactor=redactor,
    )

    tags = ["demo", "curated"] if args.demo else ["random-population"]

    written = 0

    if args.demo:

        for item in DEMO_QUESTIONS[: args.limit]:

            trace = trace_question(
                engine, writer, item,
                session_id=f"demo-{item['id']}",
                turn=1,
                history=[],
                tags=tags,
            )

            written += 1
            print(f"  {trace['trace_id']}  demo  {item['id']}")

        print(f"\n{written} demo traces appended to {args.out}")
        return

    # --- claim files ---------------------------------------------

    for record in CLAIM_FILES[: args.limit]:

        trace = trace_summary(
            engine, writer, record,
            session_id=f"claim-{record['claim_id']}",
            tags=tags + ["summary"],
        )

        written += 1
        print(f"  {trace['trace_id']}  summary  {record['claim_id']}")

    # --- adjuster questions --------------------------------------
    #
    # A follow-up inherits the previous question's session and history, so
    # the traffic contains real multi-turn traces. Without them the
    # condensation step would never run in anger and its failures would be
    # invisible to the sample.

    history = []
    session_id = None
    turn = 0

    for item in QUESTIONS[: args.limit]:

        if item.get("follow_up") and session_id:
            turn += 1
        else:
            history = []
            session_id = f"desk-{item['id']}"
            turn = 1

        trace = trace_question(
            engine, writer, item, session_id, turn, history, tags + ["qa"]
        )

        written += 1
        print(f"  {trace['trace_id']}  qa       {item['id']}  turn {turn}")

        history = history + [
            {"role": "user", "content": item["text"]},
            {"role": "assistant", "content": trace["output"]["raw"]},
        ]

    print(f"\n{written} traces appended to {args.out}")


if __name__ == "__main__":
    main()
