"""Week 12 capstone: the claims triage and coverage assistant - one entry point.

    python weeks.py w12 triage --claim CLM-2026-80003      # one FNOL in, one referral out, with the trace
    python weeks.py w12 all                                # the whole integrated eval and every audit

    python weeks.py w12 run | score | taxonomy | trajectory   # the eval, stage by stage
    python weeks.py w12 retrieval | groundability | pii | trace | replay | judge | agreement | reports
    python weeks.py w12 serve-policy-wording               # run our MCP server for an external client

`all` is the single command a stranger runs. It spends LLM tokens (about 31
triage runs and 31 judge calls) and, on the free Groq tier, takes about an
hour; everything that does not need the model (`retrieval`, `pii`) is also
available on its own and runs in a couple of minutes.

Nothing here has a model of its own to call: the model is called in exactly
one place, tools/w12_agent.py, and (for judging) tools/w12_audit.py.
"""

import json
import os
import sys

# The capstone runs on gpt-oss-120b, not the gpt-oss-20b of Weeks 7-11: the
# free tier caps 20b at 200,000 tokens a day and Week 11's suite had spent
# it. Set before any import, because tools/w7d_common.py reads LLM_MODEL once
# at import time. Override with LLM_MODEL=... in the environment.
os.environ.setdefault("LLM_MODEL", "openai/gpt-oss-120b")

STAGES_AFTER_RUN = ["score", "taxonomy", "trajectory", "retrieval", "groundability", "pii", "trace"]


def triage(argv):
    """Demo part 1: a live FNOL in, a visible tool trail, a referral out."""

    import argparse

    from data.w12_claims import CLAIMS_BY_NUMBER
    from w11_obs import RequestSink
    from w12_agent import TriageSession

    parser = argparse.ArgumentParser(prog="weeks.py w12 triage")
    parser.add_argument("--claim", required=True)
    parser.add_argument("--question", default=None)
    parser.add_argument("--no-date-filter", action="store_true")
    args = parser.parse_args(argv)

    claim = CLAIMS_BY_NUMBER[args.claim]

    if args.no_date_filter:
        import os
        os.environ["W12_DATE_FILTER"] = "0"

    sink = RequestSink()
    session = TriageSession(sink=sink)

    try:
        print(f"tools discovered at runtime: {session.discovered()}\n", flush=True)

        trace, referral = session.run(
            claim["claim_number"], question=args.question or claim["question"],
            user_id="cli", case_id=claim["case_id"], registry_claim=claim,
        )
    finally:
        session.close()

    print("tool trail:")

    for call in trace.tool_calls:
        shown = {k: v for k, v in call["args"].items() if k != "query"}
        print(f"  {call['name']:<26} {call['server'] or 'local':<15} {shown}")

    print(f"\ntrace id: {trace.trace_id}   outcome: {trace.outcome}")
    totals = trace.totals()
    print(f"latency {totals['latency_ms'] / 1000:.1f}s   tokens {totals['tokens_in']}+{totals['tokens_out']}   "
          f"cost ${totals['cost_usd']:.5f}\n")
    print(json.dumps(referral, indent=2))

    return 0


def main():

    argv = sys.argv[1:]

    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0

    stage, rest = argv[0], argv[1:]

    if stage == "triage":
        return triage(rest)

    if stage == "serve-policy-wording":
        from w12_policy_server import build_server
        build_server().serve_forever()
        return 0

    if stage in ("run", "score", "taxonomy", "trajectory"):
        import w12_eval
        sys.argv = ["w12 " + stage, stage] + rest
        return w12_eval.main()

    if stage in ("retrieval", "groundability", "pii", "trace", "replay", "judge", "agreement"):
        import w12_audit
        sys.argv = ["w12 " + stage, stage] + rest
        return w12_audit.main()

    if stage == "reports":
        import w12_reports
        sys.argv = ["w12 reports"] + rest
        return w12_reports.main()

    if stage == "all":
        import w12_audit
        import w12_eval

        for step in ["run"] + STAGES_AFTER_RUN + ["judge"]:
            print(f"\n===== w12 {step} =====", flush=True)
            module = w12_audit if step in ("retrieval", "groundability", "pii", "trace", "judge") else w12_eval
            sys.argv = ["w12 " + step, step] + rest
            module.main()

        print("\nNext, by hand: fill eval/w12/labels_main.json, then `weeks.py w12 agreement`.")
        return 0

    print(f"unknown stage {stage!r}\n\n{__doc__}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
