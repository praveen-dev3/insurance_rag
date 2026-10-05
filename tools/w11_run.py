"""Week 11 Task Set D: find the coverage answer that ignored an exclusion.

    python weeks.py w11d-eval --stage suite --label red   --prompt triage-v1 --retrieval kw-r1
    python weeks.py w11d-eval --stage suite --label green --prompt triage-v2 --retrieval kw-r2
    python weeks.py w11d-eval --stage seed      # build yesterday's log with one sealed plant
    python weeks.py w11d-eval --stage reports   # trace.json, cost_by_stage.md, tenx.md

The drill itself is run with tools/w11_drill.py (start / find / answer),
because the clock has to be started by one command and stopped by another.
"""

import argparse
import sys

from w11_suite import SUITE, format_summary, run_suite, summarise, OUT_DIR


def stage_suite(args):

    cases = args.cases.split(",") if args.cases else SUITE

    print(f"running {len(cases)} cases x {args.trials} trials "
          f"[{args.prompt} / {args.retrieval}]", flush=True)

    summary = run_suite(args.prompt, args.retrieval, trials=args.trials,
                        label=args.label, cases=cases,
                        log=lambda line: print(line, flush=True))

    text = format_summary(summary)
    print("\n" + text)
    (OUT_DIR / f"suite_{args.label}.txt").write_text(text + "\n", encoding="utf-8")


def main():

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["suite", "seed", "reports"], required=True)
    parser.add_argument("--label", default="run")
    parser.add_argument("--prompt", default="triage-v2")
    parser.add_argument("--retrieval", default="kw-r2")
    parser.add_argument("--trials", type=int, default=2)
    parser.add_argument("--cases", default=None, help="comma-separated claim ids")
    args = parser.parse_args()

    if args.stage == "suite":
        stage_suite(args)
    elif args.stage == "reports":
        from w11_reports import reports
        reports()
    elif args.stage == "seed":
        print("seeding is `python tools/w11_drill.py seed` - see that module's docstring",
              file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
