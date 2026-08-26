"""Replay one trace from the trace alone and diff it against the original.

    python tools/w5_replay.py tr-wk5-0031
    python tools/w5_replay.py tr-wk5-0031 --no-generate    # retrieval only

The point of the exercise is not that the replay matches. It is to find
out *which fields the trace was missing*, by trying to reconstruct the run
from nothing but the trace record and seeing where it fails. So this
deliberately reads only the trace: the question, the recorded queries, the
recorded retrieval options, the recorded chunk_ids, the recorded prompt
version and hash, and the recorded model parameters. It never looks the
case up in the population file.

Three checks, reported separately because they fail for different reasons:

  retrieval   re-run the search with the recorded queries and options,
              and compare the chunk_ids that come back to the ones the
              trace recorded. A mismatch here means the index moved under
              the trace, not that the app is non-deterministic.
  prompt      rebuild the prompt from the recorded chunk_ids and compare
              its hash to the recorded `rendered_sha256`. This is the
              check that proves the replayed model call received the same
              bytes the original did.
  output      re-call the model and diff the text.

Chunk *text* is not stored in the trace. That is a deliberate trade — it
would multiply the file size by roughly forty — and the consequence is
stated rather than hidden: replay resolves text by chunk_id against the
live index, so a re-index that changes chunk boundaries makes historical
traces unreplayable. The prompt hash check is what detects that, instead
of letting it pass as a model difference.
"""

import argparse
import difflib
import json
import sys
from pathlib import Path

import chromadb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.claims import SUMMARY_PROMPT, build_summary_prompt  # noqa: E402
from rag.config import CHROMA_PATH, COLLECTION_NAME  # noqa: E402
from rag.engine import RagEngine  # noqa: E402
from rag.generation import build_prompt, generate_answer  # noqa: E402
from rag.indexing import open_collection  # noqa: E402
from rag.llm import get_client  # noqa: E402
from rag.retrieval import UNSPECIFIED, RetrievedChunk  # noqa: E402
from rag.tracing import DEFAULT_TRACE_PATH, index_traces, read_traces, sha256_short  # noqa: E402


def resolve_chunks(chunk_rows, collection_name=None):
    """
    Rebuild RetrievedChunk objects from the chunk_ids in a trace.

    The per-stage scores come from the trace and the text comes from the
    index, which is exactly the split that makes the replay honest: the
    trace is authoritative about what the retriever decided, the index is
    authoritative about what the text said.
    """

    client = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = open_collection(client, collection_name or COLLECTION_NAME)

    ids = [row["chunk_id"] for row in chunk_rows]

    if not ids:
        return [], []

    payload = collection.get(ids=ids, include=["documents", "metadatas"])

    found = {
        chunk_id: (document, metadata)
        for chunk_id, document, metadata in zip(
            payload["ids"], payload["documents"], payload["metadatas"]
        )
    }

    chunks = []
    missing = []

    for row in chunk_rows:

        if row["chunk_id"] not in found:
            missing.append(row["chunk_id"])
            continue

        document, metadata = found[row["chunk_id"]]

        chunks.append(RetrievedChunk(
            id=row["chunk_id"],
            text=document,
            source=metadata.get("source", row.get("source")),
            page_start=metadata.get("page_start", 0),
            page_end=metadata.get("page_end", 0),
            source_file=metadata.get("source_file", UNSPECIFIED),
            form_number=metadata.get("form_number", UNSPECIFIED),
            policy_line=metadata.get("policy_line", UNSPECIFIED),
            edition_date=metadata.get("edition_date", UNSPECIFIED),
            clause=metadata.get("clause", UNSPECIFIED),
            clause_label=metadata.get("clause_label", UNSPECIFIED),
            document_title=metadata.get("document_title", UNSPECIFIED),
            exclusion_codes=[
                code for code in
                (metadata.get("exclusion_codes") or "").split(",") if code
            ],
            distance=row.get("distance"),
            dense_rank=row.get("dense_rank"),
            bm25_score=row.get("bm25_score"),
            sparse_rank=row.get("sparse_rank"),
            rrf_score=row.get("rrf_score") or 0.0,
            mmr_rank=row.get("mmr_rank"),
            rerank_score=row.get("rerank_score"),
        ))

    return chunks, missing


def replay_retrieval(engine, trace):
    """Re-run the search using only what the trace recorded."""

    retrieval = trace["retrieval"]
    queries = retrieval.get("queries") or {}
    options = retrieval.get("options") or {}

    chunks, _ = engine.retrieve(
        queries.get("condensed") or trace["input"]["question"],
        mode=retrieval.get("mode"),
        top_k=options.get("top_k", 3),
        filters=retrieval.get("filters"),
        search_query=queries.get("search_query"),
        dense_query=queries.get("dense_query"),
        use_mmr=options.get("use_mmr"),
        reranker=options.get("reranker"),
    )

    original_ids = [row["chunk_id"] for row in retrieval["final"]]
    replayed_ids = [chunk.id for chunk in chunks]

    return {
        "original_ids": original_ids,
        "replayed_ids": replayed_ids,
        "identical": original_ids == replayed_ids,
    }


def rebuild_prompt(trace):
    """
    Rebuild the exact user message the model was sent.

    The task decides which template: the two prompts are different files
    and a replay that used the wrong one would report a hash mismatch that
    looks like index drift.
    """

    chunks, missing = resolve_chunks(trace["retrieval"]["final"])

    if trace["task"] == "summary":
        rendered = build_summary_prompt(trace["input"]["question"], chunks)
        template = SUMMARY_PROMPT
    else:
        rendered = build_prompt(
            (trace["retrieval"]["queries"] or {}).get("search_query")
            or trace["input"]["question"],
            chunks,
        )
        template = build_prompt("<question>", [])

    return {
        "chunks": chunks,
        "missing_chunk_ids": missing,
        "rendered": rendered,
        "rendered_sha256": sha256_short(rendered),
        "recorded_rendered_sha256": trace["prompt"].get("rendered_sha256"),
        "template_sha256": sha256_short(template),
        "recorded_template_sha256": trace["prompt"].get("template_sha256"),
    }


def replay_generation(trace, prompt):
    """Re-call the model with the recorded parameters."""

    model = trace["model"]

    request = {
        "model": model["id"],
        "temperature": model.get("temperature", 0),
        "messages": [{"role": "user", "content": prompt["rendered"]}],
    }

    if model.get("seed") is not None:
        request["seed"] = model["seed"]

    if trace["task"] == "qa":
        # The QA path sends a system message and replays history before
        # the grounded prompt. Reconstructing that from the trace is the
        # reason `input.history` is stored at all.
        return generate_answer(
            (trace["retrieval"]["queries"] or {}).get("search_query")
            or trace["input"]["question"],
            prompt["chunks"],
            history=trace["input"].get("history") or [],
            model=model["id"],
        )

    response = get_client().chat.completions.create(**request)

    return response.choices[0].message.content


def show_diff(original, replayed, width=200):

    lines = list(difflib.unified_diff(
        (original or "").splitlines(),
        (replayed or "").splitlines(),
        fromfile="original",
        tofile="replayed",
        lineterm="",
        n=1,
    ))

    if not lines:
        print("  (byte-identical)")
        return 0

    for line in lines[:60]:
        print("  " + line[:width])

    if len(lines) > 60:
        print(f"  ... {len(lines) - 60} more diff lines")

    return len([l for l in lines if l.startswith(("+", "-"))
                and not l.startswith(("+++", "---"))])


def main():

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace_id")
    parser.add_argument("--traces", default=str(DEFAULT_TRACE_PATH))
    parser.add_argument("--no-generate", action="store_true")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass

    traces = index_traces(read_traces(args.traces))

    if args.trace_id not in traces:
        raise SystemExit(f"No trace '{args.trace_id}' in {args.traces}.")

    trace = traces[args.trace_id]

    print("=" * 72)
    print(f"REPLAY {trace['trace_id']}   task={trace['task']}   ts={trace['ts']}")
    print("=" * 72)
    print(f"prompt version   : {trace['prompt']['version']}")
    print(f"model            : {trace['model']['id']} "
          f"temperature={trace['model'].get('temperature')} "
          f"seed={trace['model'].get('seed')}")
    print(f"retrieval        : mode={trace['retrieval']['mode']} "
          f"options={json.dumps(trace['retrieval']['options'])}")

    engine = RagEngine()

    # --- 1. retrieval -------------------------------------------

    retrieval = replay_retrieval(engine, trace)

    print("\n--- 1. RETRIEVAL ---")
    print(f"  original chunk_ids : {retrieval['original_ids']}")
    print(f"  replayed chunk_ids : {retrieval['replayed_ids']}")
    print(f"  identical          : {retrieval['identical']}")

    # --- 2. prompt ----------------------------------------------

    prompt = rebuild_prompt(trace)

    print("\n--- 2. PROMPT ---")
    print(f"  template sha256  recorded={prompt['recorded_template_sha256']} "
          f"rebuilt={prompt['template_sha256']} "
          f"match={prompt['template_sha256'] == prompt['recorded_template_sha256']}")
    print(f"  rendered sha256  recorded={prompt['recorded_rendered_sha256']} "
          f"rebuilt={prompt['rendered_sha256']} "
          f"match={prompt['rendered_sha256'] == prompt['recorded_rendered_sha256']}")

    if prompt["missing_chunk_ids"]:
        print(f"  UNRESOLVABLE chunk_ids: {prompt['missing_chunk_ids']}")

    # --- 3. output ----------------------------------------------

    result = {
        "trace_id": trace["trace_id"],
        "retrieval": retrieval,
        "prompt": {
            key: value for key, value in prompt.items()
            if key not in ("chunks", "rendered")
        },
    }

    if not args.no_generate:

        replayed = replay_generation(trace, prompt)
        original = trace["output"]["raw"]

        print("\n--- 3. OUTPUT ---")
        print(f"  original chars : {len(original or '')}")
        print(f"  replayed chars : {len(replayed or '')}")
        print(f"  identical      : {original == replayed}")
        print("\n  diff (original -> replayed):")

        changed = show_diff(original, replayed)

        result["output"] = {
            "identical": original == replayed,
            "changed_lines": changed,
            "original": original,
            "replayed": replayed,
        }

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"\nSaved to {out}")


if __name__ == "__main__":
    main()
