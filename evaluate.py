"""Measure retrieval, instead of guessing at it.

    python evaluate.py retrieval                  # current config
    python evaluate.py sweep-retrieval            # modes, reranker, MMR
    python evaluate.py sweep-retrieval --with-transforms
    python evaluate.py sweep-chunking             # chunk size / strategy
    python evaluate.py answers                    # end-to-end + failure labels
    python evaluate.py compare --before a.json --after b.json

Every command writes its raw results to eval/results/ so a later run can
be diffed against it rather than remembered.

Why this is a front end and not a standalone script
---------------------------------------------------
It builds a RagEngine and measures *that*, using the same retrieval path
the server serves. The tempting alternative — a script with its own
loader, its own retriever, its own top-k — would be shorter and would
quietly measure a fourth system that no user ever touches. Every number
in the write-ups would then describe something that does not exist.

Why `retrieval` and `answers` are separate commands
---------------------------------------------------
They cost different things, so they earn different habits.

  retrieval   makes ZERO LLM calls. Everything it needs — embeddings,
              BM25, fusion, the cross-encoder — runs locally, so it is
              free, repeatable and deterministic. Run it before and
              after any change to retrieval.
  answers     generates a real answer per case, so it spends real
              tokens against the free tier's daily budget, and two runs
              of it are not bit-identical. Run it when the question is
              about answer quality, not about retrieval.

That gap is why `retrieval` is the de facto regression gate: there is no
pytest suite in this repo, and no test dependency in pyproject.toml.
`python evaluate.py retrieval --k 1` is the only automated behavioural
check that exists, so it is the one to run before claiming a change
helped.

`compare` exists because a single number cannot tell you what happened.
An average that rose while three questions regressed is a different
result from one that rose cleanly, and only a per-question diff of two
saved runs separates them.
"""

import argparse
import json
import sys
from pathlib import Path

from rag.config import EVAL_RESULTS_PATH, GOLDEN_SET_PATH, TOP_K
from rag.engine import RagEngine
from rag.evaluation import (
    compare,
    evaluate_answers,
    evaluate_retrieval,
    format_table,
    load_golden_set,
    save_results,
    sweep_chunking,
    sweep_retrieval,
)
from rag.query import hyde_document, rewrite_query
from rag.rerankers import get_reranker


def tolerate_console_encoding():
    """PDF text routinely contains glyphs the Windows console cannot encode."""

    for stream in (sys.stdout, sys.stderr):

        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


# ============================================================
# TRANSFORMS AS EVALUATION ARMS
# ============================================================

def rewrite_transform(question):
    """Query rewriting affects both retrievers."""

    # Both return values are the rewritten text: rewriting replaces the
    # query outright, so BM25 and the dense probe see the same string.
    # Contrast hyde_transform below, where they deliberately differ.
    rewritten = rewrite_query(question)

    return rewritten, rewritten


def hyde_transform(question):
    """HyDE swaps only the dense probe; BM25 keeps the literal question.

    The split is the whole point. HyDE's hypothetical passage helps the
    embedder, which is matching meaning — but it would actively hurt
    BM25, which matches tokens: an invented paragraph brings invented
    vocabulary, and keyword search would then rank documents by how well
    they match words the model made up. The literal question keeps the
    real terms (form numbers, "water backup", "sump") that BM25 is here
    to catch.
    """

    passage = hyde_document(question)

    # `or question` is the fallback when generation returns nothing —
    # degrade to plain dense retrieval rather than embedding an empty
    # string, which would score every chunk identically and turn one
    # failed LLM call into a silently meaningless arm of the sweep.
    return question, passage or question


# ============================================================
# COMMANDS
# ============================================================

def command_retrieval(args, engine, cases):
    """
    Score one configuration — whatever the current settings are.

    The three lines printed after the table are the ones worth reading:
    a question that was never retrieved needs a different fix from one
    that fusion found and the reranker then threw away, and an
    out-of-scope question whose context survived the floor is a
    hallucination waiting to happen.
    """

    result = evaluate_retrieval(
        engine.retriever,
        cases,
        k=args.k,
        label=args.label or "current",
        mode=args.mode,
        use_mmr=args.mmr,
        reranker=get_reranker(args.reranker) if args.reranker else None,
    )

    print()
    print(format_table([result], k=args.k))
    print()
    print(f"Missed entirely : {result['misses'] or 'none'}")
    print(f"Lost in rerank  : {result['lost_in_rerank'] or 'none'}")
    print(
        "Out-of-scope questions with surviving context: "
        f"{result['out_of_scope']['context_survived']}"
        f"/{result['out_of_scope']['cases']}"
    )

    return result


def command_sweep_retrieval(args, engine, cases):
    """
    Add one stage at a time and watch the number move.

    The arms are cumulative on purpose — dense, then sparse, then fusion,
    then reranking — so each row's delta is attributable to exactly one
    change. Comparing two configurations that differ in three ways tells
    you nothing about which of the three helped.

    The transform arms cost an LLM call per question, so they are behind
    a flag; the BGE arm downloads ~1.1 GB, so it is behind another.
    """

    variants = [
        {"label": "dense only", "mode": "dense", "reranker": get_reranker("none")},
        {"label": "bm25 only", "mode": "sparse", "reranker": get_reranker("none")},
        {"label": "hybrid RRF, no rerank", "mode": "hybrid",
         "reranker": get_reranker("none")},
        {"label": "hybrid + cross-encoder", "mode": "hybrid",
         "reranker": get_reranker("ms-marco")},
        {"label": "hybrid + rerank + MMR", "mode": "hybrid",
         "reranker": get_reranker("ms-marco"), "use_mmr": True},
    ]

    if args.with_transforms:
        variants.extend([
            {"label": "hybrid + rerank + rewrite", "mode": "hybrid",
             "reranker": get_reranker("ms-marco"),
             "transform": rewrite_transform},
            {"label": "hybrid + rerank + HyDE", "mode": "hybrid",
             "reranker": get_reranker("ms-marco"),
             "transform": hyde_transform},
        ])

    if args.with_bge:
        variants.append({
            "label": "hybrid + BGE reranker", "mode": "hybrid",
            "reranker": get_reranker("bge"),
        })

    results = sweep_retrieval(engine.retriever, cases, variants, k=args.k)

    print("\n" + format_table(results, k=args.k))

    return results


def command_sweep_chunking(args, engine, cases):
    """
    Re-index the corpus once per chunking variant and score each.

    This is the expensive sweep — every arm rebuilds embeddings — which
    is why the sizes chosen bracket the default rather than scanning
    exhaustively. Page-level ground truth is what makes the results
    comparable at all: chunk ids change with every variant, so
    chunk-level labels would compare nothing.
    """

    variants = [
        {"strategy": "fixed", "chunk_size": 150, "overlap": 30},
        {"strategy": "fixed", "chunk_size": 300, "overlap": 60},
        {"strategy": "recursive", "chunk_size": 150, "overlap": 30},
        {"strategy": "recursive", "chunk_size": 220, "overlap": 40},
        {"strategy": "recursive", "chunk_size": 400, "overlap": 80},
        {"strategy": "sentence", "chunk_size": 220, "overlap": 40},
    ]

    results = sweep_chunking(
        engine.chroma_client,
        cases,
        variants,
        k=args.k,
        mode=args.mode,
    )

    print("\n" + format_table(results, k=args.k))
    print()

    for result in results:
        print(
            f"{result['label']:<24} {result['chunks_indexed']:>4} chunks   "
            f"misses: {result['misses'] or 'none'}"
        )

    return results


def command_answers(args, engine, cases):
    """
    Run the whole pipeline and label every outcome.

    Unlike the retrieval commands this includes the out-of-scope
    questions, because the thing being measured — did it refuse when it
    should have? — only exists once an answer has been generated.
    Successes are summarised; failures are printed in full, since those
    are what the run is for.
    """

    result = evaluate_answers(
        engine,
        cases,
        k=args.k,
        label=args.label or "answers",
        mode=args.mode,
        use_mmr=args.mmr,
    )

    print()
    print(f"{'label':<20} {'count':>6}  {'rate':>6}")
    print("-" * 36)

    for name, count in result["counts"].items():
        print(f"{name:<20} {count:>6}  {result['rates'][name]:>6.2%}")

    print("\nFailures:")

    for row in result["rows"]:

        if row["label"] in ("ok", "correct_refusal"):
            continue

        print(f"  [{row['label']}] {row['id']}: {row['question']}")
        print(f"      {row['reason']}")

    return result


def command_compare(args, engine, cases):
    """
    Diff two saved runs.

    The last three lines matter more than the metric table: an average
    that improved while three questions regressed is a different result
    from one that improved cleanly, and only the per-question lists can
    tell them apart.
    """

    before = json.loads(Path(args.before).read_text(encoding="utf-8"))
    after = json.loads(Path(args.after).read_text(encoding="utf-8"))

    # Accept either a bare result or a saved wrapper.
    before = before.get("result", before)
    after = after.get("result", after)

    diff = compare(before, after, k=args.k)

    print(f"\n{diff['before']}  ->  {diff['after']}\n")
    print(f"{'stage':<10} {'metric':<14} {'before':>8} {'after':>8} {'delta':>8}")
    print("-" * 52)

    for row in diff["rows"]:
        print(
            f"{row['stage']:<10} {row['metric']:<14} "
            f"{row['before']:>8.3f} {row['after']:>8.3f} {row['delta']:>+8.3f}"
        )

    print(f"\nFixed by the change   : {diff['fixed'] or 'none'}")
    print(f"Regressed             : {diff['regressed'] or 'none'}")
    print(f"Still failing         : {diff['still_failing'] or 'none'}")

    return diff


COMMANDS = {
    "retrieval": command_retrieval,
    "sweep-retrieval": command_sweep_retrieval,
    "sweep-chunking": command_sweep_chunking,
    "answers": command_answers,
    "compare": command_compare,
}


def parse_args():
    """
    One flag set shared by every command.

    Not all flags apply to all commands — `--before/--after` only mean
    something to `compare` — but a single parser keeps the invocations
    uniform and the file short. `--k` matters most: on a small corpus,
    k=3 saturates and only k=1 discriminates between configurations.
    """

    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument("command", choices=sorted(COMMANDS))
    parser.add_argument("--k", type=int, default=TOP_K)
    parser.add_argument("--golden-set", default=GOLDEN_SET_PATH)
    parser.add_argument("--mode", default="hybrid")
    parser.add_argument("--reranker", default=None)
    parser.add_argument("--mmr", action="store_true")
    parser.add_argument("--with-transforms", action="store_true")
    parser.add_argument(
        "--with-bge",
        action="store_true",
        help="Include the BGE reranker arm (downloads ~1.1 GB on first use)."
    )
    parser.add_argument("--label", default=None)
    parser.add_argument("--out", default=None)
    parser.add_argument("--before", default=None)
    parser.add_argument("--after", default=None)

    return parser.parse_args()


def main():
    """
    Load the golden set, run one command, print it, save it.

    Saving is unconditional: the whole point of measuring is to be able
    to compare against the measurement later, and a number that only
    existed in a terminal is a number you will re-run to get back.
    """

    args = parse_args()
    tolerate_console_encoding()

    cases = load_golden_set(args.golden_set)

    print(f"Loaded {len(cases)} evaluation cases from {args.golden_set}.")

    # `compare` reads saved files; it must not pay to boot the index or
    # load two models to diff two JSON documents.
    engine = None if args.command == "compare" else RagEngine()

    result = COMMANDS[args.command](args, engine, cases)

    # Default output is per-command, so re-running a command overwrites
    # its own file. Pass --out to keep a run around for a later compare.
    out = args.out or str(
        Path(EVAL_RESULTS_PATH) / f"{args.command}.json"
    )

    saved = save_results({"command": args.command, "result": result}, out)

    print(f"\nSaved to {saved}")


if __name__ == "__main__":
    main()
