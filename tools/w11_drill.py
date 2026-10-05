"""The find-it drill: seed yesterday's log, start a clock, slice, answer.

    python tools/w11_drill.py seed [--seed N] [--plant-claim C] [--plant-index K]
    python tools/w11_drill.py start
    python tools/w11_drill.py find [--date D] [--hours A-B] [--user U] [--prompt V]
                                   [--type T] [--text REGEX] [--cost-outliers]
                                   [--flag F] [--show ID [--resolve]]
    python tools/w11_drill.py answer TRACE_ID --slice "..." --by NAME

Why there is a seed step at all: the brief has a squadmate plant one bad
answer and describe it only as vaguely as the real complaint was. `seed`
plays that squadmate. It takes one *real* failing trace out of a suite run
(never a hand-written fake - the spans, tokens and context ids in the log
are the ones the live app produced), re-stamps it to a random time
yesterday under a random user, and buries it among ~150 other requests.
Only a sha256 of the planted trace id is written to disk, so `answer` can
mark a guess right or wrong without the log, or the sealed file, giving
the place away.

What this does NOT replace: a human squadmate doing the planting and the
timing. The time `answer` prints is the wall clock between `start` and
`answer` on whoever ran it; it is only the brief's mm:ss if that person is
the finder and did not read the seed code first. drill.md says who actually
ran it.
"""

import argparse
import hashlib
import json
import random
import re
import statistics
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from data.w7d_claims import GOLDEN
from data.w11d_cases import register
from w7d_policy_corpus import _CHUNKS
from w11_obs import DEFAULT_LOG_PATH, REPO_ROOT, Redactor, read_log

register()

OUT_DIR = REPO_ROOT / "eval" / "w11d"
SEALED = OUT_DIR / ".sealed_plant.json"
CLOCK = OUT_DIR / ".drill_clock.json"
RESULTS = OUT_DIR / "drill_result.json"
SOURCE_LOG = REPO_ROOT / "traces" / "w11d_suite_red.jsonl"

TODAY = datetime(2026, 10, 5, tzinfo=timezone.utc)
YESTERDAY = (TODAY - timedelta(days=1)).date().isoformat()

USERS = [f"u-{n}" for n in (1042, 1077, 1103, 1150, 1188, 1214, 1260, 1291)]

CHUNK_BY_ID = {chunk["id"]: chunk for chunk in _CHUNKS}


def is_bad_coverage(record):
    """Said covered where the hand-computed golden says excluded."""

    claim_id = record.get("input", {}).get("claim_id")
    status = record.get("output", {}).get("coverage_status")

    return (
        status == "covered"
        and claim_id in GOLDEN
        and GOLDEN[claim_id]["status"] != "covered"
    )


# ---- seeding ---------------------------------------------------------------

def _business_hour_ts(rng, day):
    """A timestamp on `day`, weighted toward working hours."""

    hour = int(rng.triangular(6, 20, 11.5))
    moment = datetime(day.year, day.month, day.day, hour,
                      rng.randrange(60), rng.randrange(60), tzinfo=timezone.utc)

    return moment.isoformat(timespec="seconds")


def _restamp(record, rng, user, ts, jitter=True):
    """A copy of a real record under a new id, time and user."""

    copy = json.loads(json.dumps(record))
    copy["trace_id"] = f"req-{rng.getrandbits(48):012x}"
    copy["ts"] = ts
    copy["user_id"] = user

    if jitter:
        factor = rng.uniform(0.8, 1.35)

        for span in copy["spans"]:
            span["latency_ms"] = round(span["latency_ms"] * factor, 1)

        copy["totals"]["latency_ms"] = round(copy["totals"]["latency_ms"] * factor, 1)

    return copy


def _synthetic(rng, kind, user, ts):
    """
    A non-triage request: a policy question or a claim summary.

    These carry no coverage decision, but the policy-question answers say
    "covered" in passing, because real Q&A traffic does and a text slice on
    that word that returned only the one bad answer would be a toy.
    """

    answers = {
        "policy_question": [
            "Sudden and accidental discharge from a supply line is covered under HO-0304 clause 2.1, subject to the deductible.",
            "The sump back-up form HO-0521 applies only where a secondary power source is fitted.",
            "A claim must be reported within one year of the storm event under HO-0412 clause 4.1.",
            "Home-sharing income is covered for up to fourteen rented days a year under HO-0633 clause 4.1.",
        ],
        "claim_summary": [
            "Summary: water loss reported, adjuster inspected, reserve set, awaiting contractor estimate.",
            "Summary: roof loss reported after storm, roofer quote attached, referral pending.",
        ],
    }[kind]

    prompt = {"policy_question": "qa-v2", "claim_summary": "summary-v3"}[kind]
    tokens_in = rng.randint(900, 2600)
    tokens_out = rng.randint(120, 520)
    retr = round(rng.uniform(8, 40), 1)
    gen = round(rng.uniform(1800, 9000), 1)
    cost = round(tokens_in / 1e6 * 0.075 + tokens_out / 1e6 * 0.30, 6)

    return {
        "log_schema": "2",
        "trace_id": f"req-{rng.getrandbits(48):012x}",
        "ts": ts,
        "user_id": user,
        "input_type": kind,
        "claim_number": None,
        "prompt_version": prompt,
        "retrieval_version": "kw-r1",
        "model": "openai/gpt-oss-20b",
        "input": {"question_sha256": f"{rng.getrandbits(64):016x}"},
        "context_ids": [f"HO-0{rng.choice([304, 412, 521, 633])}#{rng.randint(0, 60)}"
                        for _ in range(3)],
        "spans": [
            {"span_id": "sp-01", "name": "tool.search_policy", "stage": "retrieval",
             "t_start_ms": 0.0, "latency_ms": retr, "tokens_in": 0, "tokens_out": 0,
             "cost_usd": 0.0, "attrs": {}},
            {"span_id": "sp-02", "name": "llm.lap1", "stage": "generation",
             "t_start_ms": retr, "latency_ms": gen, "tokens_in": tokens_in,
             "tokens_out": tokens_out, "cost_usd": cost, "attrs": {"lap": 1}},
        ],
        "totals": {"latency_ms": round(retr + gen, 1), "tokens_in": tokens_in,
                   "tokens_out": tokens_out, "cost_usd": cost, "by_stage": {}},
        "output": {"text": rng.choice(answers)},
        "outcome": "completed",
    }


def seed(args):

    if not SOURCE_LOG.exists():
        sys.exit(f"{SOURCE_LOG} not found - run the RED suite first "
                 "(python weeks.py w11d-eval --stage suite --label red ...)")

    rng = random.Random(args.seed)
    real = [r for r in read_log(SOURCE_LOG) if r["outcome"] == "completed"]

    bad = [r for r in real if is_bad_coverage(r)]
    good = [r for r in real if not is_bad_coverage(r)]

    if not bad:
        sys.exit("the source log holds no bad coverage answer to plant")

    if args.plant_claim:
        bad = [r for r in bad if r["input"]["claim_id"] == args.plant_claim]

        if not bad:
            sys.exit(f"no bad answer for {args.plant_claim} in the source log")

    plant_src = bad[args.plant_index % len(bad)]

    yesterday = TODAY - timedelta(days=1)
    plant = _restamp(plant_src, rng, rng.choice(USERS),
                     _business_hour_ts(rng, yesterday))

    rows = []

    for _ in range(args.background):

        day = TODAY - timedelta(days=rng.choices([0, 1, 2, 3], [1, 3, 3, 2])[0])
        ts = _business_hour_ts(rng, day)
        user = rng.choice(USERS)
        roll = rng.random()

        if roll < 0.45:
            rows.append(_restamp(rng.choice(good), rng, user, ts))
        elif roll < 0.8:
            rows.append(_synthetic(rng, "policy_question", user, ts))
        else:
            rows.append(_synthetic(rng, "claim_summary", user, ts))

    # A few runaway-cost distractors, so "cost outlier" is a slice with
    # more than one hit in it and the planted record is not the only one a
    # cost sort surfaces.
    for _ in range(4):
        spike = _restamp(rng.choice(good), rng, rng.choice(USERS),
                         _business_hour_ts(rng, yesterday))
        for span in spike["spans"]:
            if span["stage"] == "generation":
                span["tokens_in"] *= 3
                span["cost_usd"] = round(span["cost_usd"] * 3, 6)
                span["latency_ms"] = round(span["latency_ms"] * 2.4, 1)
        spike["totals"]["cost_usd"] = round(sum(s["cost_usd"] for s in spike["spans"]), 6)
        spike["totals"]["tokens_in"] = sum(s["tokens_in"] for s in spike["spans"])
        rows.append(spike)

    rows.append(plant)
    rows.sort(key=lambda row: row["ts"])

    DEFAULT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    with DEFAULT_LOG_PATH.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")

    SEALED.write_text(json.dumps({
        "sha256_of_trace_id": hashlib.sha256(plant["trace_id"].encode()).hexdigest(),
        "note": "Only the hash is stored. `answer` compares against it.",
    }), encoding="utf-8")

    CLOCK.unlink(missing_ok=True)
    RESULTS.unlink(missing_ok=True)

    print(f"seeded {len(rows)} requests into {DEFAULT_LOG_PATH.relative_to(REPO_ROOT)}; "
          "one bad coverage answer planted (sealed). Run `start` when ready.")


# ---- the clock -------------------------------------------------------------

def start(_args):
    CLOCK.write_text(json.dumps({"t0": time.time()}), encoding="utf-8")
    print("clock started. Complaint: 'an adjuster says it told a claimant "
          "something was covered when the policy excludes it, sometime yesterday.'")


def answer(args):

    if not CLOCK.exists():
        sys.exit("no clock running - `start` first")

    elapsed = time.time() - json.loads(CLOCK.read_text())["t0"]
    minutes, seconds = divmod(int(round(elapsed)), 60)

    sealed = json.loads(SEALED.read_text())
    correct = hashlib.sha256(args.trace_id.encode()).hexdigest() == sealed["sha256_of_trace_id"]

    result = {
        "guess": args.trace_id,
        "correct": correct,
        "time_to_find": f"{minutes:02d}:{seconds:02d}",
        "seconds": round(elapsed, 1),
        "slice": args.slice,
        "timed_by": args.by,
        "under_5_minutes": elapsed < 300,
    }

    existing = json.loads(RESULTS.read_text()) if RESULTS.exists() else []
    existing.append(result)
    RESULTS.write_text(json.dumps(existing, indent=2), encoding="utf-8")

    print(json.dumps(result, indent=2))

    if not correct:
        print("not the planted answer - clock keeps running")
    else:
        CLOCK.unlink(missing_ok=True)


# ---- the slices ------------------------------------------------------------

def _matches(row, args, cost_cut):

    if args.date and not row["ts"].startswith(args.date):
        return False

    if args.hours:
        low, high = (int(part) for part in args.hours.split("-"))
        if not low <= int(row["ts"][11:13]) < high:
            return False

    if args.user and row["user_id"] != args.user:
        return False

    if args.prompt and row["prompt_version"] != args.prompt:
        return False

    if args.type and row["input_type"] != args.type:
        return False

    if args.text and not re.search(args.text, json.dumps(row.get("output", {})), re.I):
        return False

    if args.flag and args.flag not in row.get("flags", []):
        return False

    if cost_cut is not None and row["totals"]["cost_usd"] < cost_cut:
        return False

    return True


def find(args):

    rows = read_log()

    if args.show:
        _show(next((r for r in rows if r["trace_id"] == args.show), None), args.resolve)
        return

    cost_cut = None

    if args.cost_outliers:
        costs = [r["totals"]["cost_usd"] for r in rows]
        cost_cut = statistics.mean(costs) + 2 * statistics.pstdev(costs)

    hits = [r for r in rows if _matches(r, args, cost_cut)]

    print(f"{len(hits)} of {len(rows)} requests match")

    for row in hits[: args.limit]:
        out = row.get("output", {})
        print(f"{row['trace_id']}  {row['ts']}  {row['user_id']:<7} {row['input_type']:<15} "
              f"{row['prompt_version']:<10} ${row['totals']['cost_usd']:.5f}  "
              f"status={out.get('coverage_status')}  "
              f"claim={row.get('input', {}).get('claim_id')}  "
              f"flags={row.get('flags', [])}")


def _show(row, resolve):

    if row is None:
        print("no such trace id")
        return

    print(json.dumps({k: v for k, v in row.items() if k != "spans"}, indent=2))

    for span in row["spans"]:
        print(f"  {span['span_id']} {span['name']:<24} {span['stage']:<10} "
              f"{span['latency_ms']:>9.1f} ms  in={span['tokens_in']:<5} "
              f"out={span['tokens_out']:<5} ${span['cost_usd']:.6f}")

    if resolve:
        print("\ncontext ids resolved:")
        for chunk_id in row["context_ids"]:
            chunk = CHUNK_BY_ID.get(chunk_id)
            print(f"  {chunk_id:<12} {chunk['clause'][:70] if chunk else '?'}")


# ---- derived field (the bonus) ---------------------------------------------

EXCLUSION_IDS = {
    chunk["id"] for chunk in _CHUNKS
    if "(E-" in chunk["clause"] or "(note)" in chunk["clause"]
}


def enrich_exclusion_check(record):
    """
    Stamp `flags` and `exclusion_rows_in_context` on a record at write time.

    The field the first drill lacked. A coverage answer is logged with the
    ids of what it was shown, but "was any exclusion row among them?" was a
    question a person had to answer per candidate by resolving ids to
    clauses by hand. Computed once on write, it is a flag that can be
    filtered on: `covered_without_exclusions_seen` is exactly the shape of
    the complaint - said covered, and was never shown a row that excludes.
    """

    seen = [cid for cid in record.get("context_ids", []) if cid in EXCLUSION_IDS]
    record["exclusion_rows_in_context"] = len(seen)

    # The first version of this field only asked "were ANY exclusion rows in
    # context", and it missed the second plant: that answer was shown four of
    # the HO-0412 table's ten rows (E-32/33/35/37) and not the two that
    # controlled (E-34/E-36). Any-rows is the wrong test; the right one is
    # whether the governing form's table was shown in full.
    forms = {cid.split("#")[0] for cid in record.get("context_ids", [])}
    total = {cid for cid in EXCLUSION_IDS if cid.split("#")[0] in forms}
    unseen = total - set(seen)
    record["exclusion_rows_unseen"] = len(unseen)

    flags = []

    if record.get("output", {}).get("coverage_status") == "covered":
        if not seen:
            flags.append("covered_without_exclusions_seen")
        if unseen:
            flags.append("covered_with_unseen_exclusion_rows")

    if flags:
        record["flags"] = flags

    return record


def reindex(_args):
    """Back-fill the derived field onto an existing log, in place."""

    rows = [enrich_exclusion_check(r) for r in read_log()]

    with DEFAULT_LOG_PATH.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")

    flagged = sum(1 for r in rows if r.get("flags"))
    print(f"re-indexed {len(rows)} records; {flagged} flagged covered_without_exclusions_seen")


def main():

    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("seed")
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--plant-index", type=int, default=0)
    p.add_argument("--plant-claim", default=None)
    p.add_argument("--background", type=int, default=150)
    p.set_defaults(fn=seed)

    sub.add_parser("start").set_defaults(fn=start)
    sub.add_parser("reindex").set_defaults(fn=reindex)

    p = sub.add_parser("answer")
    p.add_argument("trace_id")
    p.add_argument("--slice", required=True)
    p.add_argument("--by", required=True)
    p.set_defaults(fn=answer)

    p = sub.add_parser("find")
    p.add_argument("--date")
    p.add_argument("--hours")
    p.add_argument("--user")
    p.add_argument("--prompt")
    p.add_argument("--type")
    p.add_argument("--text")
    p.add_argument("--flag")
    p.add_argument("--cost-outliers", action="store_true")
    p.add_argument("--limit", type=int, default=40)
    p.add_argument("--show")
    p.add_argument("--resolve", action="store_true")
    p.set_defaults(fn=find)

    args = parser.parse_args()

    if getattr(args, "seed", 0) is None:
        args.seed = int(time.time()) % 100000

    args.fn(args)


if __name__ == "__main__":
    main()
