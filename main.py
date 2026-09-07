"""Command-line interface for the insurance RAG pipeline.

The retrieval and generation logic lives in the `rag` package, which the
web server (`server.py`) and the evaluator (`evaluate.py`) drive through
the same RagEngine.

Why a CLI *as well as* the server, when both answer the same questions:
this is the short loop for anyone changing retrieval. It needs no
browser, no `npm run build`, and no second process — start it, and the
next edit to `rag/` is one restart away from being visible. The server is
for using the app; this is for working on it.

The flags are the knobs the coursework actually turns:

    --reindex     rebuild the index after changing a chunking setting
    --mode        hybrid | dense | sparse — the Week 3 comparison
    --reranker    swap or disable the cross-encoder stage
    --trace       print the stage-by-stage funnel (see print_trace)
    --diagnose    label the result retrieval-failure vs generation-failure

Nothing in this file decides anything about retrieval. Every knob is
forwarded to RagEngine, because the moment a front end grows its own
retrieval path, the evaluator stops measuring what the server serves.
"""

import argparse
import sys

# argparse rather than click/typer: it is in the standard library, so the
# CLI adds no dependency to a project whose install is already heavy
# (torch, chromadb, sentence-transformers).
#
# Everything below comes from `rag` — the lists of valid modes, rerankers
# and strategies included. Importing RETRIEVAL_MODES instead of writing
# ("hybrid", "dense", "sparse") here means `--mode` cannot offer a choice
# the retriever does not implement, and the defaults (TOP_K, MMR_LAMBDA,
# MMR_POOL) come from rag/config.py so the CLI and the server start from
# the same settings rather than two copies that drift.
from rag.chunking import CHUNK_STRATEGIES
from rag.config import CHUNK_SIZE, CHUNK_STRATEGY, MMR_LAMBDA, MMR_POOL, TOP_K
from rag.diagnostics import classify_with_judge
from rag.engine import RagEngine
from rag.generation import stream_answer
from rag.rerankers import RERANKERS
from rag.retrieval import RETRIEVAL_MODES, format_pages


def tolerate_console_encoding():
    """
    Stop an unprintable glyph from killing the run.

    PDFs routinely carry characters the Windows console codepage cannot
    encode (private-use glyphs from embedded fonts, typographic dashes).
    Printing one raises UnicodeEncodeError, which would abort mid-answer;
    replacing it costs one substituted character instead.
    """

    for stream in (sys.stdout, sys.stderr):

        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def describe_scores(chunk):
    """One line summarising how each retrieval stage rated the chunk.

    Every stage is printed, not just the final score, because the useful
    question about a chunk is *which stage put it here*. A chunk with a
    bm25 rank and no vector rank was found by keyword alone — usually an
    exact form number like HO-0304 — and one with a high RRF score but a
    low rerank score is the reranker doing its job.
    """

    parts = []

    if chunk.dense_rank is not None:
        parts.append(
            f"vector #{chunk.dense_rank} (distance {chunk.distance:.4f})"
        )

    if chunk.sparse_rank is not None:
        parts.append(
            f"bm25 #{chunk.sparse_rank} (score {chunk.bm25_score:.4f})"
        )

    if not parts:
        parts.append("no retriever rank")

    parts.append(f"RRF {chunk.rrf_score:.5f}")

    if chunk.mmr_rank is not None:
        parts.append(f"MMR #{chunk.mmr_rank}")

    if chunk.rerank_score is not None:
        parts.append(f"rerank {chunk.rerank_score:.4f}")

    return " | ".join(parts)


def print_trace(trace):
    """
    The inspection view, in a terminal.

    Shows how many candidates entered and left each stage, then the
    candidates themselves — which is what turns "it answered wrong" into
    "the reranker dropped the right chunk".
    """

    # 70 is a display width, not a tuned value: it fits inside the
    # default 80-column console without wrapping, and the same 70 is
    # reused for every banner below so the sections line up when you
    # scroll back through a long session.
    print("\n" + "=" * 70)
    print("RETRIEVAL TRACE")
    print("=" * 70)

    queries = trace.config.get("queries") or {}

    print(f"asked      : {trace.question}")

    if queries.get("condensed") and queries["condensed"] != trace.question:
        print(f"condensed  : {queries['condensed']}")

    if queries.get("rewritten"):
        print(f"rewritten  : {queries['rewritten']}")

    # The other query lines print in full; this one is truncated because
    # a HyDE probe is a whole hypothetical paragraph, and the point of
    # showing it is to check it is *about the right thing* before it gets
    # embedded. 160 characters is roughly the first two lines — enough to
    # spot a probe that wandered off topic, short enough not to bury the
    # funnel underneath it.
    if queries.get("hyde"):
        print(f"HyDE probe : {queries['hyde'][:160]}...")

    print(f"mode       : {trace.mode}")

    if trace.filters:
        print(f"filters    : {trace.filters}")

    # Counts in, counts out, one stage per entry. Reading the funnel
    # left to right localises a bad answer to a stage before you read a
    # single chunk: "fused 20 -> reranked 20 -> final 0" is the floor
    # rejecting everything, which is a different bug from "vector 20,
    # bm25 0", which is BM25 never matching the query's vocabulary.
    funnel = [
        ("vector", len(trace.dense)),
        ("bm25", len(trace.sparse)),
        ("fused (RRF)", len(trace.fused)),
        ("MMR", len(trace.mmr)),
        ("reranked", len(trace.reranked)),
        ("final", len(trace.final)),
    ]

    # Stages that did not run are omitted so the line stays readable
    # (MMR is off by default, sparse is absent in dense mode). "final" is
    # the exception and always prints, because `final 0` — nothing
    # cleared the relevance floor — is the single most important thing
    # this line can tell you, and hiding it because it is zero would hide
    # exactly the run you are debugging.
    print("\nfunnel     : " + "  ->  ".join(
        f"{name} {count}" for name, count in funnel if count or name == "final"
    ))

    print("timings ms : " + ", ".join(
        f"{stage} {value}" for stage, value in trace.timings_ms.items()
    ))

    if trace.dropped_below_floor:
        print(
            f"\nDropped below the relevance floor: "
            f"{len(trace.dropped_below_floor)} chunk(s). "
            "Nothing in the corpus scored as relevant."
        )


def ask_question(engine, question, history, args):
    """
    One turn: retrieve, optionally explain, answer, optionally diagnose.

    Retrieval and generation are called separately rather than through
    `engine.ask`, so the retrieved chunks can be printed before the
    answer starts streaming — the same ordering the web UI uses, and for
    the same reason: the citations are readable while the answer is still
    being written.
    """

    print("\n" + "=" * 70)
    print("QUESTION")
    print("=" * 70)
    print(question)

    # prepare() only retrieves; stream_answer() only generates. Calling
    # them separately rather than engine.ask() is what lets the chunks
    # print before the first token arrives. engine.ask() would block
    # until the whole answer existed, and the sources — the part a reader
    # needs in order to judge the answer — would arrive last.
    #
    # Both paths run the identical retrieval code inside RagEngine;
    # ask() is literally prepare() plus generate_answer(). This is a
    # choice about display order, not about the pipeline.
    queries, chunks, trace = engine.prepare(
        question,
        history=history,
        mode=args.mode,
        top_k=args.top_k,
        filters=build_filters(args),
        use_rewrite=args.rewrite,
        use_hyde=args.hyde,
        use_mmr=args.mmr,
        mmr_lambda=args.mmr_lambda,
        mmr_pool=args.mmr_pool,
        reranker=args.reranker,
    )

    if args.trace:
        print_trace(trace)

    print("\n" + "=" * 70)
    print(f"RETRIEVED CHUNKS  [mode: {args.mode}]")
    print("=" * 70)

    # Not an error. An empty pool means every candidate scored below the
    # reranker's relevance floor, and the answer that follows will be a
    # refusal. A refusal on an out-of-scope question is a pass
    # (`correct_refusal`), so this message is information, not a warning.
    if not chunks:
        print("\nNo chunk cleared the relevance floor.")

    for index, chunk in enumerate(chunks, start=1):

        print(f"\n--- Chunk {index} ---")
        print(f"Source: {chunk.source}")
        print(f"Page: {format_pages(chunk)}")
        print(f"Scores: {describe_scores(chunk)}")

        # A preview, not the chunk. Chunks are built to CHUNK_SIZE=220
        # tokens, which is comfortably more than 500 characters, so this
        # always truncates — deliberately. With top_k chunks on screen at
        # once, printing each one in full pushes the answer off the top of
        # the scrollback; 500 characters is enough to recognise which
        # passage this is and to see whether it is on topic. The API
        # truncates nothing — /api/chat sends each chunk's full text — so
        # the web inspection view is where you read a chunk end to end.
        print(f"Text:\n{chunk.text[:500]}")

    print("\n" + "=" * 70)
    print("FINAL ANSWER")
    print("=" * 70)

    answer_parts = []

    # search_query, not the raw question: prepare() may have condensed a
    # follow-up ("what about hail?") into a standalone question, or
    # rewritten it. Passing the original here would answer a different
    # question from the one the chunks were retrieved for.
    for delta in stream_answer(
        queries["search_query"],
        chunks,
        history=history
    ):
        # flush=True because stdout is block-buffered when piped, and
        # without it a streamed answer would appear all at once at the
        # end — which defeats the only reason to stream in a terminal.
        print(delta, end="", flush=True)
        answer_parts.append(delta)

    print()

    answer = "".join(answer_parts)

    # Behind a flag because it costs an extra LLM call per question. The
    # judge sees the trace and the answer together, which is the only way
    # to separate "the passage never reached the prompt" (retrieval
    # failure — no prompt change will fix it) from "the passage was there
    # and the model still got it wrong" (generation failure). Guessing at
    # that split by eye is how a Week 4 run ends up tuning the prompt to
    # fix a retrieval bug.
    if args.diagnose:

        diagnosis = classify_with_judge(
            queries["search_query"],
            trace,
            answer
        )

        print("\n" + "=" * 70)
        print("DIAGNOSIS")
        print("=" * 70)
        print(f"verdict    : {diagnosis.label}")
        print(f"meaning    : {diagnosis.explanation}")
        print(f"reason     : {diagnosis.reason}")
        print(f"context ok : {diagnosis.context_sufficient}")
        print(f"grounded   : {diagnosis.answer_grounded}")

    return answer


def build_filters(args):
    """Metadata filter from the CLI flags, or None if unfiltered."""

    filters = {}

    if args.source:
        filters["sources"] = args.source

    if args.policy_line:
        filters["policy_lines"] = args.policy_line

    if args.form:
        filters["form_numbers"] = args.form

    if args.page_min is not None:
        filters["page_min"] = args.page_min

    # page_min/page_max are tested with `is not None`, not truthiness,
    # because page 0 is a legitimate bound and `if args.page_min` would
    # silently drop it.
    if args.page_max is not None:
        filters["page_max"] = args.page_max

    # `or None` rather than returning the empty dict: downstream, an
    # empty filter dict and "no filter" must not be confused. The same
    # distinction is made in server.py's Filters.as_dict, for the same
    # reason — `{"sources": []}` reads as "search no documents".
    return filters or None


def parse_args():
    """
    Flags mirror the settings the web UI exposes, so a configuration
    found by clicking around can be reproduced — and scripted — here.

    The stage toggles default to None rather than False so that "not
    passed" stays distinguishable from "explicitly off", letting the
    config file supply the default.
    """

    parser = argparse.ArgumentParser(
        description="Ask questions about your insurance PDFs."
    )

    parser.add_argument(
        "--reindex",
        action="store_true",
        help="Rebuild the index from the PDFs before starting."
    )

    # `choices=RETRIEVAL_MODES` rather than a literal tuple, so adding a
    # mode to the retriever exposes it here automatically and argparse
    # rejects a typo before the engine boots.
    #
    # Note the default is the literal "hybrid", not config.DEFAULT_MODE:
    # setting DEFAULT_MODE in .env does not move this default. (--top-k
    # and the MMR flags below *do* read their defaults from config.)
    parser.add_argument(
        "--mode",
        choices=RETRIEVAL_MODES,
        default="hybrid",
        help=(
            "Retrieval strategy: hybrid (BM25 + vectors, fused with RRF), "
            "dense (vectors only), or sparse (BM25 only). Default: hybrid."
        )
    )

    # Default comes from config (TOP_K=3), not a literal, so the CLI, the
    # server and the evaluator all start from the same k. An evaluator
    # scoring k=3 while the CLI quietly served k=5 would be reporting on
    # a configuration nobody uses.
    parser.add_argument(
        "--top-k",
        type=int,
        default=TOP_K,
        help=f"Chunks passed to the LLM after reranking (default {TOP_K})."
    )

    parser.add_argument(
        "--reranker",
        choices=RERANKERS,
        default=None,
        help="Reranker to use. Default: whatever RERANKER is set to."
    )

    parser.add_argument(
        "--mmr",
        action="store_true",
        default=None,
        help="Diversify the candidate pool with MMR before reranking."
    )

    # Both defaults live in rag/config.py (MMR_LAMBDA=0.7 relevance vs
    # diversity, MMR_POOL=10 candidates selected before reranking); the
    # rationale for those values is documented there, next to the values.
    parser.add_argument("--mmr-lambda", type=float, default=MMR_LAMBDA)
    parser.add_argument("--mmr-pool", type=int, default=MMR_POOL)

    parser.add_argument(
        "--rewrite",
        action="store_true",
        default=None,
        help="Rewrite the question into a retrieval-friendly query first."
    )

    parser.add_argument(
        "--hyde",
        action="store_true",
        default=None,
        help="Embed a hypothetical answer instead of the question (HyDE)."
    )

    parser.add_argument(
        "--source",
        action="append",
        help="Only search this document. Repeatable."
    )

    parser.add_argument(
        "--policy-line",
        action="append",
        help=(
            "Only search endorsements on this policy line "
            "(homeowners, dwelling_fire, motor). Repeatable."
        )
    )

    parser.add_argument(
        "--form",
        action="append",
        help="Only search this form number, e.g. HO-0304. Repeatable."
    )

    parser.add_argument("--page-min", type=int, default=None)
    parser.add_argument("--page-max", type=int, default=None)

    parser.add_argument(
        "--trace",
        action="store_true",
        help="Print the stage-by-stage retrieval trace."
    )

    parser.add_argument(
        "--diagnose",
        action="store_true",
        help=(
            "After answering, classify the result as a retrieval failure, "
            "a generation failure, or fine."
        )
    )

    # One-shot mode. Exists so a question can be scripted or pasted into
    # a write-up as a reproducible command, rather than described as
    # "start the CLI and type this".
    parser.add_argument(
        "--question",
        help="Ask a single question and exit instead of starting the loop."
    )

    return parser.parse_args()


def main():
    """
    Boot the engine once, then loop — or answer one question and exit.

    Building the engine is the expensive part (index load plus two model
    loads), which is why the interactive loop exists at all: it amortises
    that cost over as many questions as you care to ask.
    """

    args = parse_args()

    # Before anything prints. The first thing this function does is emit
    # a banner containing chunk-strategy names, and a PDF-derived glyph
    # can appear in a source name — reconfiguring after the first print
    # would be too late.
    tolerate_console_encoding()

    print("=" * 70)
    print("INSURANCE CLAIM RAG")
    print(
        f"chunking={CHUNK_STRATEGY}/{CHUNK_SIZE}  mode={args.mode}  "
        f"strategies={','.join(CHUNK_STRATEGIES)}"
    )
    print("=" * 70)

    # The expensive line in the file: loading the Chroma collection, the
    # bge-small embedder and the cross-encoder. Built once, before the
    # loop, so the cost is paid per session rather than per question.
    engine = RagEngine(force_reindex=args.reindex)

    # Printed at startup because the most common confusion when a number
    # moves is not knowing which index and which models produced it — a
    # stale index answers perfectly happily, it just answers from the
    # wrong chunks.
    stats = engine.stats()

    print(
        f"\nReady: {stats['chunks']} chunks, "
        f"embeddings={stats['embedding']['model_id']}, "
        f"reranker={stats['reranker']['key']}"
    )

    # Grows without a cap on purpose, and that is safe: nothing sends the
    # whole list to a model. Both consumers slice it — rag/query.py
    # condenses using the last HISTORY_TURNS (6) turns, and
    # rag/generation.py replays the same last 6 — so the prompt stays a
    # fixed size however long the session runs. Truncating here as well
    # would just mean two places to keep in step.
    history = []

    if args.question:
        ask_question(engine, args.question, history, args)
        return

    while True:

        try:
            question = input(
                "\nAsk an insurance question (type 'exit' to quit): "
            )
        # Ctrl-C and Ctrl-D (and a closed pipe) exit cleanly rather than
        # dumping a traceback. This loop is the normal way to use the
        # tool, so its normal way to end should not look like a crash.
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if question.lower() == "exit":
            print("Goodbye!")
            break

        if not question.strip():
            continue

        answer = ask_question(engine, question, history, args)

        # Appended *after* the turn is answered, not before. The history
        # passed into ask_question must describe the conversation up to
        # this question — including it would have the condenser rewrite
        # the question using itself as context.
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": answer})


if __name__ == "__main__":
    main()
