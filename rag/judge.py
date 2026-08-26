"""The one criterion left for a model to decide, and the machinery to
check whether it decides it the way a human does.

After the split in rag/assertions.py the judge has exactly one job: given
a claim summary and the policy wording that was retrieved to write it, say
whether every coverage statement in the summary follows from that wording.
Binary. Not a 1-10 score — the model cannot reliably tell a 6 from a 7,
and neither can the person checking it, so a scored judge produces an
agreement figure that is really a measure of how wide a tolerance the
author chose.

The judge prompt lives in a file (eval/judge_v1.txt, eval/judge_v2.txt)
rather than in this module. That is what makes iterating on it a diff
rather than a code change, and it is what lets the eval name the exact
prompt version a number came from.

`agreement` is the whole point of the week. A judge that has never been
compared to a human is a number generator; the comparison is what turns it
into a measurement, and it has to be done against labels written before
the judge ran or it is not a comparison at all.
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from openai import OpenAIError

from rag.config import JUDGE_MODEL
from rag.llm import complete

JUDGE_DIR = Path("eval")

DEFAULT_JUDGE = "judge_v1"

# The single criterion. Named as a constant because the label file, the
# judge output and the agreement computation all have to mean the same key, and a
# typo in one of three string literals is a silent zero.
CRITERION = "coverage_faithful"


@dataclass
class Verdict:
    """One judge ruling on one summary."""

    case_id: str
    faithful: bool | None
    reason: str = ""
    judge: str = DEFAULT_JUDGE
    error: str | None = None

    def to_dict(self):
        return asdict(self)


def load_judge_prompt(name=DEFAULT_JUDGE, directory=None):
    """
    Read a judge prompt from disk.

    Missing file is a hard error. Falling back to a built-in default would
    let a run report an agreement figure for a prompt that was never on
    disk, which is the one thing the version-in-a-file arrangement exists
    to prevent.
    """

    path = Path(directory or JUDGE_DIR) / f"{name}.txt"

    if not path.exists():
        raise FileNotFoundError(
            f"No judge prompt at '{path}'. Available: "
            f"{sorted(p.stem for p in Path(directory or JUDGE_DIR).glob('judge_v*.txt'))}"
        )

    return path.read_text(encoding="utf-8")


def judge_summary(summary, notes, context, case_id="", judge=DEFAULT_JUDGE,
                  prompt=None, model=None, on_wait=None):
    """
    Ask the judge its one question about one summary.

    Errors come back as a Verdict with `faithful=None` rather than as an
    exception or as a default of True. A judge that silently returns True
    when the API is down produces an agreement figure that improves during
    an outage, and that is a worse failure than a crash.
    """

    template = prompt if prompt is not None else load_judge_prompt(judge)

    rendered = template.format(
        context=context or "(no policy wording was retrieved)",
        notes=notes,
        summary=summary or "(no summary was produced)",
    )

    try:
        response = complete(
            model=model or JUDGE_MODEL,
            temperature=0,
            max_tokens=1600,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": rendered}],
            on_wait=on_wait,
        )

        payload = json.loads(response.choices[0].message.content or "{}")

    except (OpenAIError, json.JSONDecodeError, ValueError) as error:
        return Verdict(case_id, None, judge=judge, error=str(error))

    if CRITERION not in payload:
        return Verdict(
            case_id, None, judge=judge,
            error=f"judge returned no '{CRITERION}' key: {list(payload)}",
        )

    return Verdict(
        case_id=case_id,
        faithful=bool(payload[CRITERION]),
        reason=str(payload.get("reason", ""))[:400],
        judge=judge,
    )


# ============================================================
# AGREEMENT
# ============================================================

def agreement(labels, verdicts):
    """
    How often the judge and the human said the same thing.

    Reported as raw agreement plus the confusion cells, because raw
    agreement alone hides the asymmetry that matters. A judge that is
    wrong only by calling unfaithful summaries faithful is dangerous in a
    way that one wrong in the other direction is not: the first ships a
    payout, the second wastes an adjuster's afternoon.

    Cases the judge could not rule on are excluded from the denominator
    and counted separately. Scoring them as disagreements would make an
    outage look like a judge quality problem; scoring them as agreements
    would let one improve the number.
    """

    scored = []
    unscored = []

    for case_id, human in labels.items():

        verdict = verdicts.get(case_id)

        if verdict is None or verdict.faithful is None:
            unscored.append(case_id)
            continue

        scored.append((case_id, bool(human), bool(verdict.faithful)))

    matches = [case for case, human, model in scored if human == model]

    # human / judge
    both_faithful = [c for c, h, m in scored if h and m]
    both_unfaithful = [c for c, h, m in scored if not h and not m]
    judge_too_lenient = [c for c, h, m in scored if not h and m]
    judge_too_strict = [c for c, h, m in scored if h and not m]

    total = len(scored)

    return {
        "n_labelled": len(labels),
        "n_scored": total,
        "n_unscored": len(unscored),
        "unscored": unscored,
        "agreements": len(matches),
        "agreement": round(len(matches) / total, 4) if total else 0.0,
        "agreement_pct": (
            round(100 * len(matches) / total, 1) if total else 0.0
        ),
        "cells": {
            "human_faithful_judge_faithful": len(both_faithful),
            "human_unfaithful_judge_unfaithful": len(both_unfaithful),
            "human_unfaithful_judge_faithful": len(judge_too_lenient),
            "human_faithful_judge_unfaithful": len(judge_too_strict),
        },
        "disagreements": {
            "judge_too_lenient": judge_too_lenient,
            "judge_too_strict": judge_too_strict,
            "all": sorted(judge_too_lenient + judge_too_strict),
        },
    }
