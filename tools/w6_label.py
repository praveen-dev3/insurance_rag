"""Print each summary next to the wording it was written from, for labelling.

    python tools/w6_label.py --slice 0:5

Shows exactly what the judge will see and nothing else: the adjuster notes,
the retrieved POLICY WORDING, and the summary. No assertion results, no
verdict, no `wording_says` note from the case file — anything else on the
screen is an anchor, and the whole value of a hand label is that it was
formed independently.

The judge has not run and cannot run: tools/run_w6.py refuses `--stage judge`
until eval/labels_25.json exists.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summaries", default="eval/w6/summaries.json")
    parser.add_argument("--slice", default=None)
    parser.add_argument("--chars", type=int, default=1100)
    args = parser.parse_args()

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass

    rows = json.loads(
        Path(args.summaries).read_text(encoding="utf-8")
    )["rows"]

    if args.slice:
        start, _, end = args.slice.partition(":")
        rows = rows[int(start or 0): int(end) if end else None]

    for row in rows:

        print("\n" + "=" * 78)
        print(f"{row['id']}   [{row['kind']}]   claim line: "
              f"{row['claim']['policy_line']}   form on file: "
              f"{row['claim']['form_number']}")
        print("=" * 78)

        print("\n--- ADJUSTER NOTES ---")
        print(row["notes_as_pasted"])

        print("\n--- POLICY WORDING RETRIEVED ---")

        for index, chunk in enumerate(row["retrieved"], start=1):
            print(
                f"\n[{index}] {chunk['form_number']} ed.{chunk['edition_date']} "
                f"({chunk['policy_line']})  rerank="
                f"{None if chunk['rerank_score'] is None else round(chunk['rerank_score'], 2)}"
            )
            print(chunk["text"][: args.chars])

        print("\n--- SUMMARY PRODUCED ---")
        print(row["summary"])


if __name__ == "__main__":
    main()
