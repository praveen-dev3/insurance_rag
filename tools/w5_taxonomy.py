"""Turn the hand-written open-coding sentences into the taxonomy table.

    python tools/w5_taxonomy.py
    python tools/w5_taxonomy.py --coding eval/w5/open_coding_demo.json --label demo

Every number in taxonomy.md is computed here rather than typed there. That
is not fussiness: the counts, the percentages and the "of 20" denominator
are the output of the week, and a percentage typed by hand into a markdown
table is a number nobody can check and everybody will quote.

The coding file is read in two halves on purpose, and the script reports
whether the halves are consistent:

  sentence   what the reader SAW in that trace. Written first, for all
             twenty traces, before any mode existed.
  mode       which cluster it landed in. Added in a second pass over the
             sentences, not while reading the traces.

`--strict` fails if any observation carries a mode that is not in the
declared `modes` block, which is what stops the cluster list and the
assignments drifting apart as modes get renamed.
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SEVERITY_ORDER = {
    "wrongly denies a claim": 0,
    "wrongly pays a claim": 1,
    "wrongly denies or wrongly pays a claim": 2,
    "annoys the adjuster": 3,
}


def load_coding(path):

    payload = json.loads(Path(path).read_text(encoding="utf-8"))

    observations = payload["observations"]
    modes = payload.get("modes", {})

    return payload, observations, modes


def build_table(observations, modes, strict=True):
    """
    Count, percent, severity and one real example per mode.

    The example is picked as the first trace_id in the mode rather than
    the "best" one, because choosing an illustrative example is how a
    taxonomy row quietly becomes a story about the worst case rather than
    a description of the mode.
    """

    coded = [item for item in observations if item.get("mode")]
    uncoded = [item for item in observations if not item.get("mode")]

    counts = Counter(item["mode"] for item in coded)

    unknown = sorted(set(counts) - set(modes))

    if unknown and strict:
        raise SystemExit(
            f"Modes used in observations but not declared: {unknown}"
        )

    examples = defaultdict(list)

    for item in coded:
        examples[item["mode"]].append(item["trace_id"])

    total = len(observations)

    rows = [
        {
            "mode": mode,
            "count": count,
            "percent": round(100 * count / total, 1),
            "severity": modes.get(mode, {}).get("severity", "?"),
            "example_trace_id": sorted(examples[mode])[0],
            "all_trace_ids": sorted(examples[mode]),
        }
        for mode, count in counts.items()
    ]

    rows.sort(
        key=lambda row: (
            -row["count"],
            SEVERITY_ORDER.get(row["severity"], 9),
            row["mode"],
        )
    )

    return {
        "total_traces": total,
        "coded": len(coded),
        "uncoded": [item["trace_id"] for item in uncoded],
        "modes_declared": len(modes),
        "modes_used": len(counts),
        "rows": rows,
    }


def render_markdown(table, label=""):

    lines = [
        f"| Mode | Count | % of {table['total_traces']} | Severity | Example trace_id |",
        "|---|---:|---:|---|---|",
    ]

    for row in table["rows"]:
        lines.append(
            f"| {row['mode']} | {row['count']} | {row['percent']}% | "
            f"{row['severity']} | `{row['example_trace_id']}` |"
        )

    return "\n".join(lines)


def main():

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coding", default="eval/w5/open_coding.json")
    parser.add_argument("--out", default=None)
    parser.add_argument("--label", default="random sample")
    parser.add_argument("--no-strict", action="store_true")
    args = parser.parse_args()

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass

    payload, observations, modes = load_coding(args.coding)

    table = build_table(observations, modes, strict=not args.no_strict)

    print(f"Coding file : {args.coding}")
    print(f"Sample      : {args.label}, {table['total_traces']} traces")
    print(f"Modes       : {table['modes_used']} used "
          f"of {table['modes_declared']} declared")

    if table["uncoded"]:
        print(f"UNCODED     : {table['uncoded']}")

    print()
    print(render_markdown(table, args.label))

    # A mode list that does not add to the sample size means a trace was
    # counted twice or dropped, and the frequencies are wrong. Say so.
    counted = sum(row["count"] for row in table["rows"])

    print(f"\nRows sum to {counted} of {table['total_traces']} traces."
          + ("" if counted == table["total_traces"] else "  <-- MISMATCH"))

    out = Path(args.out or "eval/w5/taxonomy_table.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "label": args.label,
        "coding_file": args.coding,
        "seed": payload.get("seed"),
        **table,
    }, indent=2), encoding="utf-8")

    print(f"Saved to {out}")


if __name__ == "__main__":
    main()
