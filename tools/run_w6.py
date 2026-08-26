"""Week 6 Task Set D — the one command.

    python tools/run_w6.py                      # generate, assert, judge, table
    python tools/run_w6.py --stage summaries    # generate only, no judge
    python tools/run_w6.py --stage judge --judge judge_v2
    python tools/run_w6.py --stage agreement --judge judge_v2

Stages, and why they are separable even though `run_w6.py` with no
arguments does all of them:

  summaries   run the 25+ cases through the app and save the summaries.
              Deterministic assertions run here, because they cost
              nothing and need no network.
  judge       run one judge prompt over the saved summaries.
  agreement   compare a judge run against the hand labels.

The separation is what makes the blind protocol enforceable. The labels
are written against the summaries file and committed BEFORE `--stage judge`
is ever run; keeping generation and judging in one inseparable command
would make it impossible to demonstrate that ordering, because every
summary would arrive with a verdict already attached to it.

`--stage judge` refuses to run if the labels file does not exist yet, for
the same reason. It is not possible to accidentally read the judge's
verdicts first.
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.assertions import ASSERTIONS, run_assertions  # noqa: E402
from rag.claims import (  # noqa: E402
    SUMMARY_PROMPT_VERSION,
    ClaimFile,
    build_context,
    coverage_position,
    generate_summary,
)
from rag.config import DEFAULT_MODE, TOP_K  # noqa: E402
from rag.engine import RagEngine  # noqa: E402
from rag.generation import is_generation_error  # noqa: E402
from rag.judge import CRITERION, Verdict, agreement, judge_summary, load_judge_prompt  # noqa: E402
from rag.tracing import Redactor  # noqa: E402

CASES_PATH = Path("eval/w6_cases.json")
SUMMARIES_PATH = Path("eval/w6/summaries.json")
LABELS_PATH = Path("eval/labels_25.json")
RESULTS_DIR = Path("eval/w6")

RUN_OPTIONS = {
    "mode": DEFAULT_MODE,
    "top_k": TOP_K,
    "use_mmr": False,
    "use_rewrite": False,
    "use_hyde": False,
    "reranker": "ms-marco",
}


def _report_wait(seconds):
    """Report a rate-limit wait so a paused batch does not look hung."""

    print(f"      rate limited; waiting {seconds:.0f}s", flush=True)


def tolerate_console_encoding():

    for stream in (sys.stdout, sys.stderr):

        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def load_cases(path=CASES_PATH):

    payload = json.loads(Path(path).read_text(encoding="utf-8"))

    return payload["cases"], payload


# ============================================================
# STAGE 1 - GENERATE SUMMARIES AND RUN THE ASSERTIONS
# ============================================================

def stage_summaries(engine, cases, out=SUMMARIES_PATH):
    """
    Produce one summary per case and run every deterministic check.

    The retrieved context is saved alongside each summary. That is not
    convenience: the judge's single criterion is "does this follow from
    the wording that was retrieved", so judging a summary against a
    freshly-retrieved context would be judging a different question, and
    would quietly become non-reproducible the moment the index changed.
    """

    redactor = Redactor()
    rows = []

    for index, case in enumerate(cases, start=1):

        claim = ClaimFile(
            claim_id=case["id"],
            claim_number=case["claim_number"],
            claimant=case["claimant"],
            date_of_loss=case["date_of_loss"],
            policy_line=case["policy_line"],
            notes=case["notes"],
            form_number=case.get("form_number"),
        ).redacted(redactor)

        _, chunks, trace = engine.prepare(
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

        retrieved_ids = [chunk.id for chunk in chunks]

        results, all_passed = run_assertions(summary, claim, retrieved_ids)

        rows.append({
            "id": case["id"],
            "mode": case["mode"],
            "kind": case.get("kind", "authored"),
            "source_trace_id": case.get("source_trace_id"),
            "claim": claim.as_dict(),
            "notes_as_pasted": claim.as_pasted(),
            "summary": summary,
            "coverage_position": coverage_position(summary),
            "generation_error": is_generation_error(summary),
            "prompt_version": SUMMARY_PROMPT_VERSION,
            "model": params,
            "usage": usage,
            "retrieved": [
                {
                    "chunk_id": chunk.id,
                    "form_number": chunk.form_number,
                    "edition_date": chunk.edition_date,
                    "policy_line": chunk.policy_line,
                    "source": chunk.source,
                    "pages": [chunk.page_start, chunk.page_end],
                    "rerank_score": chunk.rerank_score,
                    # Stored verbatim because the RAGAS metrics score the
                    # summary against the passages, not against a rendered
                    # prompt, and re-retrieving them later would be scoring
                    # a different retrieval than the one that was judged.
                    "text": chunk.text,
                }
                for chunk in chunks
            ],
            # Whether the wording that was retrieved belongs to the policy
            # line of the claim. This is not a quality score and is not used
            # by any pass/fail: it is recorded so the bonus can find the
            # case that is faithful to the wrong form.
            "wrong_policy_line": sorted({
                chunk.policy_line for chunk in chunks
                if chunk.policy_line not in (claim.policy_line, "unspecified")
            }),
            # Frozen so the judge, the RAGAS metrics and any later re-run
            # all see the same wording.
            "context": build_context(chunks),
            "assertions": [item.to_dict() for item in results],
            "assertions_passed": all_passed,
        })

        print(f"  [{index:>2}/{len(cases)}] {case['id']:<8} "
              f"{case['mode']:<28} "
              f"{'PASS' if all_passed else 'FAIL'}  "
              f"{coverage_position(summary)}")

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"prompt_version": SUMMARY_PROMPT_VERSION,
                    "options": RUN_OPTIONS,
                    "rows": rows}, indent=2, default=str),
        encoding="utf-8",
    )

    print(f"\nSaved {len(rows)} summaries to {out}")

    return rows


# ============================================================
# STAGE 2 - RUN THE JUDGE
# ============================================================

def stage_judge(rows, judge="judge_v1", out=None):
    """Ask the judge its one question about every saved summary."""

    prompt = load_judge_prompt(judge)

    verdicts = {}

    for index, row in enumerate(rows, start=1):

        verdict = judge_summary(
            on_wait=_report_wait,
            summary=row["summary"],
            notes=row["notes_as_pasted"],
            context=row["context"],
            case_id=row["id"],
            judge=judge,
            prompt=prompt,
        )

        verdicts[row["id"]] = verdict

        flag = (
            "?" if verdict.faithful is None
            else ("faithful" if verdict.faithful else "UNFAITHFUL")
        )

        print(f"  [{index:>2}/{len(rows)}] {row['id']:<8} {flag}")

    out = Path(out or RESULTS_DIR / f"verdicts_{judge}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({
            "judge": judge,
            "criterion": CRITERION,
            "verdicts": {k: v.to_dict() for k, v in verdicts.items()},
        }, indent=2),
        encoding="utf-8",
    )

    print(f"\nSaved verdicts to {out}")

    return verdicts


def load_verdicts(path):

    payload = json.loads(Path(path).read_text(encoding="utf-8"))

    return {
        case_id: Verdict(**data)
        for case_id, data in payload["verdicts"].items()
    }


def load_labels(path=LABELS_PATH):
    """
    Read the hand labels.

    Only the binary criterion is read. The label file also carries the
    one-line note the labeller wrote per case, which is what makes a
    disagreement readable later, but it is deliberately not used in the
    arithmetic.
    """

    payload = json.loads(Path(path).read_text(encoding="utf-8"))

    return {
        case_id: bool(entry[CRITERION])
        for case_id, entry in payload["labels"].items()
    }, payload


# ============================================================
# REPORTING
# ============================================================

def pass_rate_by_mode(rows, verdicts=None):
    """
    The table. Pass rate per taxonomy mode, never as a single average.

    A single number over 25 cases hides exactly the thing this table
    exists to show: a mode can go to zero while the overall figure moves
    two points, because the modes are not equally sized and the biggest
    one carries the average.
    """

    buckets = defaultdict(list)

    for row in rows:
        buckets[row["mode"]].append(row)

    table = []

    for mode in sorted(buckets):

        group = buckets[mode]

        asserted = sum(1 for row in group if row["assertions_passed"])

        judged = [
            verdicts[row["id"]].faithful
            for row in group
            if verdicts and row["id"] in verdicts
            and verdicts[row["id"]].faithful is not None
        ]

        faithful = sum(1 for value in judged if value)

        overall = sum(
            1 for row in group
            if row["assertions_passed"]
            and verdicts
            and row["id"] in verdicts
            and verdicts[row["id"]].faithful
        )

        table.append({
            "mode": mode,
            "n": len(group),
            "assertions_passed": asserted,
            "assertion_rate": asserted / len(group),
            "judged": len(judged),
            "faithful": faithful,
            "faithful_rate": faithful / len(judged) if judged else None,
            "pass": overall,
            "pass_rate": overall / len(group) if verdicts else None,
        })

    return table


def print_table(table, rows, verdicts=None):

    print()
    print(f"{'taxonomy mode':<30} {'n':>3} {'assert':>8} {'faithful':>9} "
          f"{'pass':>8}")
    print("-" * 62)

    for entry in table:

        faithful = (
            f"{entry['faithful']}/{entry['judged']}"
            if entry["judged"] else "-"
        )

        overall = (
            f"{entry['pass']}/{entry['n']}"
            if entry["pass_rate"] is not None else "-"
        )

        print(
            f"{entry['mode']:<30} {entry['n']:>3} "
            f"{entry['assertions_passed']:>3}/{entry['n']:<4} "
            f"{faithful:>9} {overall:>8}"
        )

    total = len(rows)
    asserted = sum(1 for row in rows if row["assertions_passed"])

    print("-" * 62)
    print(f"{'ALL':<30} {total:>3} {asserted:>3}/{total:<4}", end="")

    if verdicts:
        judged = [v.faithful for v in verdicts.values() if v.faithful is not None]
        overall = sum(
            1 for row in rows
            if row["assertions_passed"]
            and row["id"] in verdicts
            and verdicts[row["id"]].faithful
        )
        print(f" {sum(1 for v in judged if v):>4}/{len(judged):<4} "
              f"{overall:>3}/{total}")
    else:
        print()

    # Per-assertion breakdown. The aggregate "assertions passed" figure
    # says a summary was defective; this says which check caught it,
    # which is the difference between a number and a work item.
    print("\nassertion failures (of "
          f"{total} cases):")

    failures = Counter()

    for row in rows:
        for item in row["assertions"]:
            if not item["passed"]:
                failures[item["name"]] += 1

    for name in ASSERTIONS:
        print(f"  {name:<28} {failures.get(name, 0):>3}")


def main():

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", default="all",
                        choices=("all", "summaries", "judge", "agreement"))
    parser.add_argument("--judge", default="judge_v1")
    parser.add_argument("--cases", default=str(CASES_PATH))
    parser.add_argument("--summaries", default=str(SUMMARIES_PATH))
    parser.add_argument("--labels", default=str(LABELS_PATH))
    parser.add_argument("--verdicts", default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    tolerate_console_encoding()

    cases, payload = load_cases(args.cases)

    print(f"Week 6 Task Set D — {len(cases)} cases, "
          f"{len(set(c['mode'] for c in cases))} taxonomy modes, "
          f"{sum(1 for c in cases if c.get('kind') == 'regression')} "
          "regression cases replayed from real traces.")

    rows = None
    verdicts = None

    if args.stage in ("all", "summaries"):
        engine = RagEngine()
        print()
        rows = stage_summaries(engine, cases, out=args.summaries)
    else:
        rows = json.loads(
            Path(args.summaries).read_text(encoding="utf-8")
        )["rows"]

    if args.stage in ("all", "judge"):

        # The blind protocol, enforced rather than promised. Running the
        # judge before the labels exist would make every agreement figure
        # produced afterwards unverifiable, and no amount of good
        # intentions at the terminal can undo it once the verdicts have
        # been read.
        if not Path(args.labels).exists():
            raise SystemExit(
                f"Refusing to run the judge: no labels at '{args.labels}'.\n"
                "The 25 hand labels must be written and committed BEFORE the "
                "judge runs, or the agreement figure means nothing. Write "
                "them from eval/w6/summaries.json first."
            )

        print()
        verdicts = stage_judge(rows, judge=args.judge, out=args.out)

    elif args.stage == "agreement":
        verdicts = load_verdicts(
            args.verdicts or RESULTS_DIR / f"verdicts_{args.judge}.json"
        )

    table = pass_rate_by_mode(rows, verdicts)
    print_table(table, rows, verdicts)

    if verdicts and Path(args.labels).exists():

        labels, label_payload = load_labels(args.labels)
        scores = agreement(labels, verdicts)

        print(f"\nAGREEMENT with hand labels ({args.judge})")
        print(f"  labelled          : {scores['n_labelled']}")
        print(f"  scored            : {scores['n_scored']}"
              + (f" ({scores['n_unscored']} unscored: {scores['unscored']})"
                 if scores["n_unscored"] else ""))
        print(f"  agreement         : {scores['agreements']}/{scores['n_scored']}"
              f"  =  {scores['agreement_pct']}%")
        print(f"  cells             : {json.dumps(scores['cells'])}")
        print(f"  judge too lenient : {scores['disagreements']['judge_too_lenient']}")
        print(f"  judge too strict  : {scores['disagreements']['judge_too_strict']}")

        out = Path(RESULTS_DIR / f"agreement_{args.judge}.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "judge": args.judge,
            "labels_file": args.labels,
            "labels_sha_note": label_payload.get("committed_before_judge_run"),
            **scores,
        }, indent=2), encoding="utf-8")

        print(f"\nSaved agreement to {out}")


if __name__ == "__main__":
    main()
