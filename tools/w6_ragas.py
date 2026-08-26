"""Bonus: faithfulness and context precision, and the case they both miss.

    python tools/w6_ragas.py
    python tools/w6_ragas.py --limit 12 --model qwen/qwen3.6-27b

Two metrics, computed to the RAGAS definitions:

  faithfulness              decompose the summary into atomic claims, then
                            ask of each whether it can be inferred from the
                            retrieved passages.
                                faithfulness = supported / total_claims

  context_precision         (the reference-free, LLM-judged variant) rank
                            each retrieved passage relevant or not to the
                            answer, then average precision@k over the
                            relevant ranks.
                                sum_k (precision@k * v_k) / sum_k v_k

NOT the `ragas` package. Installing it into this project's venv failed
repeatedly - a locked `jiter` .pyd left the environment without `openai`
at all and the pipeline had to be repaired - so the metrics are computed
here, against the published definitions, rather than risk the environment
that produced every other number in this repo. That is a real difference
and it is stated rather than glossed: these are RAGAS-defined metrics, not
RAGAS-library outputs, and a value here may not match the library's to the
third decimal.

Two implementation choices worth naming:

  * claim decomposition and claim verification are ONE model call, not two.
    RAGAS uses two. One call is cheaper by half against an 8,000
    tokens-per-minute ceiling, and the reason it is safe here is that the
    model is asked to emit the claim list and the per-claim verdict in the
    same JSON object, so it cannot quietly drop a claim it could not
    support - the denominator is visible in the output.
  * relevance for all retrieved passages is one call rather than one per
    passage, for the same reason.

The point of running these at all is not two more numbers. Faithfulness is
computed *against the passages that were retrieved*, so it is structurally
incapable of seeing whether those were the right passages, or all of them.
A summary that reasons impeccably from five of a table's ten rows scores
near 1.0 while the sixth row decides the claim.
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openai import OpenAIError  # noqa: E402

from rag.llm import complete  # noqa: E402

DEFAULT_MODEL = "qwen/qwen3.6-27b"


FAITHFULNESS_PROMPT = """Break the SUMMARY into atomic factual claims about what the policy
covers, excludes, limits or requires. Ignore restatements of the adjuster's
facts; only claims ABOUT THE POLICY count.

Then, for each claim, decide whether it can be inferred from the RETRIEVED
PASSAGES alone. A claim is supported only if the passages state it or
directly entail it. Do not use your own knowledge of insurance.

Reply with JSON only, as two parallel arrays of the SAME length - the
claim text, and 1 for supported or 0 for unsupported:

{{"claims": ["<claim 1>", "<claim 2>"], "supported": [1, 0]}}

Keep each claim under 20 words. Emit at most 12 claims.

RETRIEVED PASSAGES:
{context}

SUMMARY:
{summary}

JSON:"""


PRECISION_PROMPT = """For each retrieved passage below, decide whether it was USEFUL in
arriving at the ANSWER - that is, whether the answer draws on it. A passage
that is merely about the same document but contributes nothing the answer
uses is not useful.

Reply with JSON only: a single array of 1 (useful) or 0 (not useful), one
entry per passage, in the order the passages are given.

{{"useful": [1, 0, 1]}}

PASSAGES:
{passages}

ANSWER:
{summary}

JSON:"""


def _json_call(prompt, model, on_wait=None):
    """One JSON-mode completion, or None if it could not be produced."""

    try:
        # reasoning_effort="none" is load-bearing, not a cost saving. This
        # is a reasoning model, and left to itself it spent the whole
        # completion budget thinking and emitted no JSON at all - Groq then
        # rejects the call with json_validate_failed and an EMPTY
        # failed_generation, which reads like a malformed prompt rather
        # than a truncated one. With reasoning off the same prompt answers
        # in about 145 tokens.
        response = complete(
            model=model,
            temperature=0,
            max_tokens=3000,
            reasoning_effort="none",
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
            on_wait=on_wait,
        )
    except (OpenAIError, ValueError) as error:
        print(f"      call failed: {str(error)[:100]}")
        return None

    try:
        return json.loads(response.choices[0].message.content or "{}")
    except json.JSONDecodeError:
        return None


def faithfulness(row, model, on_wait=None):
    """
    Supported claims / total claims, and the unsupported ones by name.

    Returns None rather than a default when the model cannot be reached, so
    an outage cannot be mistaken for a perfect score.
    """

    payload = _json_call(
        FAITHFULNESS_PROMPT.format(
            context=row["context"], summary=row["summary"] or ""
        ),
        model,
        on_wait,
    )

    if not payload:
        return None, [], 0

    claims = payload.get("claims")
    flags = payload.get("supported")

    if not isinstance(claims, list) or not isinstance(flags, list):
        return None, [], 0

    # Two parallel arrays rather than a list of objects: this model fails
    # strict JSON validation on the nested form often enough to lose half
    # the run. Truncate to the shorter of the two rather than guessing,
    # so a ragged reply costs claims instead of silently misaligning a
    # verdict with the wrong claim.
    pairs = list(zip(claims, flags))

    if not pairs:
        return None, [], 0

    supported = [c for c, f in pairs if f in (1, True, "1", "true")]

    unsupported = [
        str(c)[:160] for c, f in pairs
        if f not in (1, True, "1", "true")
    ]

    return round(len(supported) / len(pairs), 4), unsupported, len(pairs)


def context_precision(row, model, on_wait=None):
    """
    Mean precision@k over the ranks that held a useful passage.

    This is the reference-free variant: relevance is judged against the
    answer rather than against a ground-truth passage, because there is no
    ground-truth passage for a free-text claim summary.
    """

    passages = "\n\n".join(
        f"PASSAGE {index}:\n{chunk['text'][:1400]}"
        for index, chunk in enumerate(row["retrieved"], start=1)
    )

    payload = _json_call(
        PRECISION_PROMPT.format(
            passages=passages, summary=row["summary"] or ""
        ),
        model,
        on_wait,
    )

    if not payload or not isinstance(payload.get("useful"), list):
        return None

    # Flat array, for the same reason as the faithfulness prompt: this
    # model fails strict JSON validation on an array of objects often
    # enough to lose the run.
    flags = [
        v in (1, True, "1", "true") for v in payload["useful"]
    ][: len(row["retrieved"])]

    if not flags or not any(flags):
        return 0.0

    running = 0
    total = 0.0

    for index, useful in enumerate(flags, start=1):
        if useful:
            running += 1
            total += running / index

    return round(total / running, 4)


def _report_wait(seconds):
    print(f"      rate limited; waiting {seconds:.0f}s", flush=True)


def main():

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summaries", default="eval/w6/summaries.json")
    parser.add_argument("--out", default="eval/w6/ragas.json")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass

    rows = json.loads(
        Path(args.summaries).read_text(encoding="utf-8")
    )["rows"]

    # Policy-backed cases only: a case that retrieved nothing but the flood
    # manual has no policy wording to be faithful to, and scoring it would
    # put a 1.0 or a 0.0 into the average for a reason that has nothing to
    # do with the summary.
    scored_rows = [
        row for row in rows
        if row.get("retrieved") and not row.get("generation_error")
        and any(c["policy_line"] != "unspecified" for c in row["retrieved"])
    ]

    skipped = [row["id"] for row in rows if row not in scored_rows]

    if args.limit:
        scored_rows = scored_rows[: args.limit]

    print(f"Scoring {len(scored_rows)} policy-backed cases "
          f"(evaluator: {args.model})")
    print(f"Skipped (no policy wording retrieved): {skipped}\n")

    results = []

    for index, row in enumerate(scored_rows, start=1):

        faith, unsupported, n_claims = faithfulness(
            row, args.model, _report_wait
        )
        precision = context_precision(row, args.model, _report_wait)

        results.append({
            "id": row["id"],
            "mode": row["mode"],
            "claim_policy_line": row["claim"]["policy_line"],
            "wrong_policy_line": row.get("wrong_policy_line") or [],
            "coverage_position": row.get("coverage_position"),
            "faithfulness": faith,
            "context_precision": precision,
            "n_claims": n_claims,
            "unsupported_claims": unsupported,
        })

        print(f"  [{index:>2}/{len(scored_rows)}] {row['id']:<8} "
              f"faith={'-' if faith is None else f'{faith:.3f}'}  "
              f"ctx_p={'-' if precision is None else f'{precision:.3f}'}  "
              f"({n_claims} claims)")

    faiths = [r["faithfulness"] for r in results if r["faithfulness"] is not None]
    precs = [r["context_precision"] for r in results
             if r["context_precision"] is not None]

    report = {
        "evaluator_model": args.model,
        "implementation": (
            "RAGAS-defined metrics computed locally; NOT the ragas package "
            "(its install broke this venv). See the module docstring."
        ),
        "n_scored": len(results),
        "skipped_no_policy_wording": skipped,
        "mean_faithfulness": (
            round(sum(faiths) / len(faiths), 4) if faiths else None
        ),
        "mean_context_precision": (
            round(sum(precs) / len(precs), 4) if precs else None
        ),
        "per_case": results,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"\nmean faithfulness      : {report['mean_faithfulness']}")
    print(f"mean context precision : {report['mean_context_precision']}")
    print(f"\nSaved to {out}")


if __name__ == "__main__":
    main()
