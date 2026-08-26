"""Draw the seeded random sample of traces that the taxonomy is built on.

    python tools/w5_sample.py --seed 20260826 --n 20
    python tools/w5_sample.py --seed 20260826 --n 10 --tag demo --out eval/w5/sample_demo.json

The sample is drawn with `random.Random(seed).sample` over the trace ids
**sorted**, not over the file in the order it happens to be on disk. That
detail is the whole reproducibility of the exercise: appending one more
trace to the file would silently reshuffle a position-based sample and the
seed would no longer name the same twenty traces.

Traces tagged `demo` are excluded by default. They are the curated set
shown at the monthly review — the whole point of the bonus is that their
failure frequencies differ from the population's, so letting them into the
random draw would contaminate the number the taxonomy reports.
"""

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.tracing import DEFAULT_TRACE_PATH, read_traces  # noqa: E402


def draw(traces, seed, n, tag=None, exclude_tags=("demo",)):
    """
    Return the sampled trace ids and the frame they were drawn from.

    The frame is returned alongside the sample because "20 of what?" is
    half of what makes a frequency meaningful, and a sample list on its own
    cannot answer it.
    """

    if tag:
        frame = [t for t in traces if tag in (t.get("tags") or [])]
    else:
        frame = [
            t for t in traces
            if not set(t.get("tags") or []) & set(exclude_tags)
        ]

    ids = sorted(t["trace_id"] for t in frame)

    if n > len(ids):
        raise ValueError(
            f"Asked for {n} traces but the frame holds only {len(ids)}."
        )

    sample = random.Random(seed).sample(ids, n)

    return sorted(sample), frame


def main():

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--traces", default=str(DEFAULT_TRACE_PATH))
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--n", type=int, default=20)
    parser.add_argument("--tag", default=None,
                        help="Draw only from traces carrying this tag.")
    parser.add_argument("--out", default="eval/w5/sample.json")
    args = parser.parse_args()

    traces = read_traces(args.traces)

    sample, frame = draw(traces, args.seed, args.n, tag=args.tag)

    index = {t["trace_id"]: t for t in frame}

    payload = {
        "seed": args.seed,
        "n": args.n,
        "tag": args.tag,
        "trace_file": args.traces,
        "traces_in_file": len(traces),
        "frame_size": len(frame),
        "selection": (
            f"random.Random({args.seed}).sample(sorted(trace_ids), {args.n})"
        ),
        "trace_ids": sample,
        "rows": [
            {
                "trace_id": tid,
                "task": index[tid]["task"],
                "case_id": (index[tid].get("extra") or {}).get("case_id"),
                "session_id": index[tid]["session_id"],
                "turn": index[tid]["turn"],
            }
            for tid in sample
        ],
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"Trace file      : {args.traces} ({len(traces)} traces)")
    print(f"Frame           : {len(frame)} traces"
          f"{f' tagged {args.tag}' if args.tag else ' (demo excluded)'}")
    print(f"Seed            : {args.seed}")
    print(f"Selection       : {payload['selection']}")
    print(f"Task mix drawn  : "
          f"{dict(Counter(row['task'] for row in payload['rows']))}")
    print()

    for row in payload["rows"]:
        print(f"  {row['trace_id']}  {row['task']:<8} {row['case_id']}")

    print(f"\nSaved to {out}")


if __name__ == "__main__":
    main()
