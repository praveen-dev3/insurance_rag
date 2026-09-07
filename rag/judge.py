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

Why an LLM judge here at all, when everything else is deterministic: the
cheap checks were already taken away from it. Claim number echoed, date
format, exclusion code present, citations resolving - all of those are
string work, and they live in rag/assertions.py where they cost nothing
and cannot disagree with themselves. What is left is the one question no
regex can answer: does this prose overstate what the wording supports.
Paying a model to check a date format is how LLM-judge setups become
expensive and unfalsifiable at the same time.
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from openai import OpenAIError

from rag.config import JUDGE_MODEL
from rag.llm import complete

JUDGE_DIR = Path("eval")

# v1, not the later v2, is what a bare call gets. Both scored the same
# 80.0% agreement (20/25) on the Week 6 set, and v2 is passed explicitly by
# the runner - so the effect of leaving v1 here is that the published
# `agreement_before` figure is what anyone reproduces with no arguments.
# The two prompts differ in *which* five cases they miss, not how many:
# v2 catches all five unfaithful summaries where v1 missed two, and pays
# for it elsewhere. That is visible only because both files are kept.
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
            # A judge that gives a different verdict on a re-run cannot be
            # compared to a fixed set of human labels: the agreement figure
            # would move on its own, and every prompt edit would be
            # unfalsifiable. Determinism is not a nicety here, it is what
            # makes agreement_before vs agreement_after mean anything.
            temperature=0,
            # Room for the verdict plus a paragraph of reasoning. Generous
            # rather than tuned - a truncated response is not a strict
            # judge, it is unparseable JSON, which lands in the `unscored`
            # bucket and quietly shrinks the sample the agreement figure is
            # computed over.
            max_tokens=1600,
            # Ask the API to constrain the output to JSON rather than
            # parsing prose for a yes/no. A judge whose verdict has to be
            # extracted by regex from a sentence adds a second thing that
            # can be wrong, on top of the thing being measured.
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
        # Truncated because the reason is read by a human triaging
        # disagreements, and it is stored per case in the results file. A
        # model given room to write an essay will, and 400 characters is
        # about as much as anyone reads in a comparison table.
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

    # Raw agreement, deliberately not Cohen's kappa. Kappa corrects for
    # chance agreement and is the better statistic in general - on 25 cases
    # with a lopsided class balance its confidence interval is wider than
    # the effect being measured, so it would add authority without adding
    # information. The four confusion cells below are reported instead,
    # because they are countable and a reader can check them by hand.
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
