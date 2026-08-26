"""Bonus: RAGAS faithfulness and context precision over the same summaries.

    python tools/w6_ragas.py
    python tools/w6_ragas.py --summaries eval/w6/summaries.json

Two metrics, both computed by the RAGAS library against the Groq endpoint:

  faithfulness                     of the claims the summary makes, what
                                   share are entailed by the retrieved
                                   passages?
  llm_context_precision_without_reference
                                   of the passages that were retrieved,
                                   what share were relevant, weighted by
                                   where they ranked?

The point of running them is not to add two more numbers to a report. It
is that faithfulness is computed *against the retrieved passages*, so it
cannot see whether those passages were the right ones. A summary that
reasons impeccably from the dwelling-fire exclusion table about a
homeowners claim scores near 1.0, because every sentence it wrote really
is entailed by the wording it was shown. The wording was simply the wrong
policy line, and no amount of faithfulness will say so.

This script therefore reports faithfulness next to `wrong_policy_line`,
which is recorded at generation time by comparing each retrieved chunk's
policy_line to the claim's. The pair is the finding; either number alone
is reassuring and wrong.
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.config import GROQ_BASE_URL, UTILITY_MODEL, require_api_key  # noqa: E402


def build_evaluator_llm(model=None):
    """
    Wrap the Groq endpoint so RAGAS can drive it.

    RAGAS speaks LangChain, and the Groq endpoint is OpenAI-compatible, so
    a ChatOpenAI pointed at the Groq base URL is the whole adapter. Imports
    are local to this function so that the rest of the project keeps
    running when the bonus dependencies are not installed.
    """

    from langchain_openai import ChatOpenAI
    from ragas.llms import LangchainLLMWrapper

    return LangchainLLMWrapper(ChatOpenAI(
        model=model or UTILITY_MODEL,
        base_url=GROQ_BASE_URL,
        api_key=require_api_key(),
        temperature=0,
        max_retries=3,
    ))


def score(rows, model=None):
    """Run both metrics over every case that retrieved anything."""

    from ragas import EvaluationDataset, SingleTurnSample, evaluate
    from ragas.metrics import (
        Faithfulness,
        LLMContextPrecisionWithoutReference,
    )

    evaluator = build_evaluator_llm(model)

    scored_rows = [
        row for row in rows
        if row.get("retrieved") and not row.get("generation_error")
    ]

    skipped = [
        row["id"] for row in rows if row not in scored_rows
    ]

    dataset = EvaluationDataset(samples=[
        SingleTurnSample(
            user_input=row["notes_as_pasted"],
            response=row["summary"] or "",
            retrieved_contexts=[
                chunk["text"] for chunk in row["retrieved"]
            ],
        )
        for row in scored_rows
    ])

    result = evaluate(
        dataset=dataset,
        metrics=[
            Faithfulness(llm=evaluator),
            LLMContextPrecisionWithoutReference(llm=evaluator),
        ],
        llm=evaluator,
        show_progress=True,
    )

    frame = result.to_pandas()

    per_case = []

    for row, (_, scores) in zip(scored_rows, frame.iterrows()):

        per_case.append({
            "id": row["id"],
            "mode": row["mode"],
            "claim_policy_line": row["claim"]["policy_line"],
            "wrong_policy_line": row.get("wrong_policy_line") or [],
            "coverage_position": row.get("coverage_position"),
            "faithfulness": _as_float(scores.get("faithfulness")),
            "context_precision": _as_float(
                scores.get("llm_context_precision_without_reference")
            ),
        })

    return per_case, skipped


def _as_float(value):

    try:
        value = float(value)
    except (TypeError, ValueError):
        return None

    return None if value != value else round(value, 4)


def summarise(per_case):
    """Averages, and then the cases the averages are hiding."""

    faithful = [c["faithfulness"] for c in per_case if c["faithfulness"] is not None]
    precision = [c["context_precision"] for c in per_case if c["context_precision"] is not None]

    confidently_wrong = sorted(
        [
            c for c in per_case
            if c["wrong_policy_line"]
            and c["faithfulness"] is not None
            and c["faithfulness"] >= 0.9
        ],
        key=lambda c: -c["faithfulness"],
    )

    return {
        "n": len(per_case),
        "mean_faithfulness": (
            round(sum(faithful) / len(faithful), 4) if faithful else None
        ),
        "mean_context_precision": (
            round(sum(precision) / len(precision), 4) if precision else None
        ),
        "cases_retrieving_a_foreign_policy_line": sorted(
            c["id"] for c in per_case if c["wrong_policy_line"]
        ),
        "confidently_faithfully_wrong": confidently_wrong,
        "per_case": per_case,
    }


def main():

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summaries", default="eval/w6/summaries.json")
    parser.add_argument("--out", default="eval/w6/ragas.json")
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass

    os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")

    rows = json.loads(
        Path(args.summaries).read_text(encoding="utf-8")
    )["rows"]

    print(f"Scoring {len(rows)} summaries with RAGAS "
          f"(evaluator model: {args.model or UTILITY_MODEL})...\n")

    per_case, skipped = score(rows, args.model)

    report = summarise(per_case)

    print(f"\n{'case':<8} {'mode':<28} {'faith':>7} {'ctx-p':>7}  wording line")
    print("-" * 76)

    for case in per_case:

        flag = (
            f"WRONG LINE ({','.join(case['wrong_policy_line'])})"
            if case["wrong_policy_line"] else "own line"
        )

        print(
            f"{case['id']:<8} {case['mode']:<28} "
            f"{_fmt(case['faithfulness']):>7} "
            f"{_fmt(case['context_precision']):>7}  {flag}"
        )

    print("-" * 76)
    print(f"mean faithfulness      : {report['mean_faithfulness']}")
    print(f"mean context precision : {report['mean_context_precision']}")

    if skipped:
        print(f"skipped (no retrieval or generation error): {skipped}")

    print("\nCases faithful to the WRONG policy line (faithfulness >= 0.9):")

    if not report["confidently_faithfully_wrong"]:
        print("  none in this run")

    for case in report["confidently_faithfully_wrong"]:
        print(
            f"  {case['id']}  faithfulness={case['faithfulness']}  "
            f"context_precision={case['context_precision']}  "
            f"claim line={case['claim_policy_line']}  "
            f"retrieved line={','.join(case['wrong_policy_line'])}  "
            f"position={case['coverage_position']}"
        )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"\nSaved to {out}")


def _fmt(value):
    return "-" if value is None else f"{value:.3f}"


if __name__ == "__main__":
    main()
