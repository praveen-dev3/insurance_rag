"""Print traces in a form a human can actually read, for open coding.

    python tools/w5_read.py --sample eval/w5/sample.json
    python tools/w5_read.py tr-wk5-0031 tr-wk5-0044
    python tools/w5_read.py --sample eval/w5/sample.json --brief

This is a reading tool, not an analysis tool. It deliberately prints no
verdict, no label, no score and no suggestion — only what the trace says
happened: the input, what each retrieved chunk was and what the stages
scored it, and the raw output. Anything else on the screen during open
coding becomes an anchor, and the whole value of the step comes from
describing what you saw rather than confirming what a tool told you.

The one number it does print per chunk is the rerank score, because
"nothing scored above the floor" and "the top chunk scored 8.4" are things
you can SEE in the output and would otherwise have to guess at.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.tracing import DEFAULT_TRACE_PATH, index_traces, read_traces  # noqa: E402


def tolerate_console_encoding():

    for stream in (sys.stdout, sys.stderr):

        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def show(trace, brief=False, chunk_chars=420):

    print("\n" + "=" * 78)
    print(f"{trace['trace_id']}   task={trace['task']}   "
          f"session={trace['session_id']} turn={trace['turn']}   "
          f"case={(trace.get('extra') or {}).get('case_id')}")
    print("=" * 78)

    retrieval = trace["retrieval"]
    queries = retrieval.get("queries") or {}

    print(f"prompt   : {trace['prompt']['version']}  "
          f"model: {trace['model']['id']}  temp={trace['model'].get('temperature')}")
    print(f"mode     : {retrieval['mode']}  counts: {retrieval['counts']}")

    if queries.get("condensed") and queries["condensed"] != trace["input"]["question"]:
        print(f"condensed: {queries['condensed']}")

    if trace["input"].get("history"):
        print(f"history  : {len(trace['input']['history'])} prior message(s)")

    print("\n--- INPUT ---")
    print(trace["input"]["question"])

    print("\n--- RETRIEVED (what reached the prompt) ---")

    if not retrieval["final"]:
        print("  (nothing survived the relevance floor)")

    for position, chunk in enumerate(retrieval["final"], start=1):

        score = chunk.get("rerank_score")

        print(
            f"\n  [{position}] {chunk['form_number']} ed.{chunk['edition_date']} "
            f"[{chunk['policy_line']}]  {chunk['source']} p.{chunk['pages']}"
        )
        print(
            f"      clause={chunk['clause']}  "
            f"rerank={score if score is None else round(score, 3)}  "
            f"dense#{chunk.get('dense_rank')} bm25#{chunk.get('sparse_rank')}"
        )
        print(f"      chunk_id={chunk['chunk_id']}")

    if retrieval.get("dropped_below_floor"):
        print(f"\n  dropped below floor: "
              f"{len(retrieval['dropped_below_floor'])} chunk(s)")

    citations = trace.get("citations") or {}

    if citations:
        print(
            f"\n--- CITATIONS --- cited={len(citations.get('cited') or [])} "
            f"resolved={len(citations.get('resolved') or [])} "
            f"unresolved={len(citations.get('unresolved') or [])}"
        )
        if citations.get("unresolved"):
            print(f"  unresolved: {citations['unresolved']}")

    print("\n--- OUTPUT ---")
    print(trace["output"]["raw"] if not brief
          else (trace["output"]["raw"] or "")[:900])


def main():

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace_ids", nargs="*")
    parser.add_argument("--traces", default=str(DEFAULT_TRACE_PATH))
    parser.add_argument("--sample", default=None,
                        help="Read the ids from a sample file instead.")
    parser.add_argument("--brief", action="store_true")
    parser.add_argument("--slice", default=None,
                        help="e.g. 0:5 to read only part of the sample.")
    args = parser.parse_args()

    tolerate_console_encoding()

    traces = index_traces(read_traces(args.traces))

    ids = list(args.trace_ids)

    if args.sample:
        payload = json.loads(Path(args.sample).read_text(encoding="utf-8"))
        ids = payload["trace_ids"] + ids

    if args.slice:
        start, _, end = args.slice.partition(":")
        ids = ids[int(start or 0): int(end) if end else None]

    if not ids:
        raise SystemExit("Nothing to read: pass trace ids or --sample.")

    for trace_id in ids:

        if trace_id not in traces:
            print(f"\n!! {trace_id} not in {args.traces}")
            continue

        show(traces[trace_id], brief=args.brief)


if __name__ == "__main__":
    main()
