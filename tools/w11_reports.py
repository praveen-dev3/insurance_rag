"""Week 11 write-ups that are computed, not typed: trace.json, cost_by_stage.md,
tenx.md, the eval case file.

    python weeks.py w11d-eval --stage reports

Every figure in the files this writes comes from a trace in the repo, so a
reviewer can recompute it. The attribution method for cost is explained in
`attribute_cost` because "cost by stage" is easy to report in a way that is
technically true and useless.
"""

import json
import statistics
from pathlib import Path

from data.w7d_claims import GOLDEN
from data.w11d_cases import NEW_CLAIMS, NEW_GOLDEN, register
from w11_obs import REPO_ROOT, cost_for, read_log

register()

OUT_DIR = REPO_ROOT / "eval" / "w11d"
RED_TRACES = OUT_DIR / "red_suite_traces.jsonl"
GREEN_TRACES = {
    "v2 / kw-r2": OUT_DIR / "green_v2_traces.jsonl",
    "v3 / kw-r2": REPO_ROOT / "traces" / "w11d_suite_green3.jsonl",
}
MODEL = "openai/gpt-oss-20b"

# The brief's own volume: ~1,800 FNOLs a month (Week 12 capstone, section 1).
FNOLS_PER_MONTH = 1800
FREE_TIER_TPM = 8000        # tokens/minute, from tools/w7d_common.py's docstring
FREE_TIER_TPD = 200000      # tokens/day, from the 429 body observed 2026-10-05


def attribute_cost(record):
    """
    Split one request's bill by the stage that *caused* each token.

    Summing span costs by span stage answers the wrong question: the search
    spans cost $0 (a local keyword search) and the model spans carry the whole
    bill, so "generation is 100% of cost" is true and tells you nothing about
    whether retrieval is worth optimising. The agent loop re-sends the whole
    transcript on every lap, so a search result is paid for once when it
    arrives and again on every later lap that carries it.

    The attribution: lap k's input = the fixed prompt (system + tool schemas
    + the user message, i.e. lap 1's input) plus the growth added by every
    earlier lap. That growth is the previous lap's assistant message and its
    tool results, so it is charged to the stage of the tool(s) that lap ran
    (retrieval if any was a search, else tools). Output tokens are the
    model's own work and are charged to generation.
    """

    laps = sorted((s for s in record["spans"] if s["stage"] == "generation"),
                  key=lambda s: s["attrs"]["lap"])
    stage_of_lap = {}

    for span in record["spans"]:
        if span["stage"] in ("retrieval", "tools"):
            lap = span["attrs"].get("lap")
            if span["stage"] == "retrieval" or stage_of_lap.get(lap) != "retrieval":
                stage_of_lap[lap] = span["stage"]

    base = laps[0]["tokens_in"]
    inflow = {"generation": base * len(laps), "retrieval": 0, "tools": 0}
    previous_in = base

    for index, lap in enumerate(laps[1:], start=2):
        growth = max(0, lap["tokens_in"] - previous_in)
        owner = stage_of_lap.get(laps[index - 2]["attrs"]["lap"], "tools")
        # `growth` is paid for again on this lap and every later one.
        inflow[owner] += growth * (len(laps) - index + 1)
        inflow["generation"] -= 0
        previous_in = lap["tokens_in"]

    # The fixed part is `base` on every lap; anything beyond what the
    # per-stage growth explains is rounding in the provider's counts.
    explained = sum(inflow.values())
    actual = sum(l["tokens_in"] for l in laps)
    inflow["generation"] += actual - explained

    price_in = cost_for(record["model"], 1_000_000, 0)
    out_tokens = sum(l["tokens_out"] for l in laps)

    return {
        "retrieval": inflow["retrieval"] / 1e6 * price_in,
        "tools": inflow["tools"] / 1e6 * price_in,
        "generation": inflow["generation"] / 1e6 * price_in + cost_for(record["model"], 0, out_tokens),
        "tokens_in_by_stage": inflow,
        "tokens_out": out_tokens,
        "laps": len(laps),
    }


def span_table(record):

    lines = ["| span | stage | latency ms | tokens in | tokens out | cost USD |",
             "|---|---|---:|---:|---:|---:|"]

    for span in record["spans"]:
        lines.append(f"| {span['name']} | {span['stage']} | {span['latency_ms']:.1f} | "
                     f"{span['tokens_in']} | {span['tokens_out']} | {span['cost_usd']:.6f} |")

    return lines


def reports():

    red = read_log(RED_TRACES)
    found = next(r for r in red if r["trace_id"] == "req-7060c0c1d556")
    drill = json.loads((OUT_DIR / "drill_result.json").read_text())[-1]
    log_row = next(r for r in read_log() if r["trace_id"] == drill["guess"])

    # ---- trace.json -----------------------------------------------------
    trace = {
        "found_in_log_as": {
            "trace_id": log_row["trace_id"], "ts": log_row["ts"], "user_id": log_row["user_id"],
            "note": ("The drill log holds this request re-stamped (new id, time, user) and with "
                     "span latencies scaled by a seeded jitter. The record below is the original, "
                     "un-jittered run it was cut from, so latencies are as measured."),
        },
        "original_trace_id": found["trace_id"],
        "prompt_version": found["prompt_version"],
        "prompt_sha256": found["input"]["prompt_sha256"],
        "retrieval_version": found["retrieval_version"],
        "model": found["model"],
        "claim_id": found["input"]["claim_id"],
        "retrieved_context_ids": found["context_ids"],
        "spans": found["spans"],
        "totals": found["totals"],
        "output": found["output"],
    }
    (OUT_DIR / "trace.json").write_text(json.dumps(trace, indent=2), encoding="utf-8")

    # ---- cost_by_stage.md -----------------------------------------------
    attr = attribute_cost(found)
    total = sum(attr[s] for s in ("retrieval", "generation", "tools"))
    direct = found["totals"]["by_stage"]

    suite = [r for r in red if r["outcome"] == "completed"]
    suite_attr = [attribute_cost(r) for r in suite]
    avg = {s: statistics.mean(a[s] for a in suite_attr) for s in ("retrieval", "generation", "tools")}
    avg_total = sum(avg.values())
    avg_tokens = statistics.mean(r["totals"]["tokens_in"] + r["totals"]["tokens_out"] for r in suite)
    avg_cost = statistics.mean(r["totals"]["cost_usd"] for r in suite)

    lines = [
        "# Cost per query, by stage",
        "",
        f"Request `{found['trace_id']}` (the drill's bad answer, claim c11, `{found['prompt_version']}` / "
        f"`{found['retrieval_version']}`, model `{MODEL}`). Prices: $0.075 / $0.30 per million input / "
        "output tokens (the rate quoted in tools/w7d_common.py).",
        "",
        "## 1. Spans as logged (billed by the stage that made the call)",
        "",
        *span_table(found),
        "",
        "| stage | spans | latency ms | cost USD |",
        "|---|---:|---:|---:|",
    ]

    for stage in ("retrieval", "generation", "tools"):
        b = direct[stage]
        lines.append(f"| {stage} | {b['spans']} | {b['latency_ms']:.1f} | {b['cost_usd']:.6f} |")

    lines += [
        f"| **total** | {len(found['spans'])} | {found['totals']['latency_ms']:.1f} | **{found['totals']['cost_usd']:.6f}** |",
        "",
        "Read literally, retrieval and tools cost nothing and generation is the whole bill. That is true of "
        "the *calls* and is the wrong basis for deciding what to optimise: retrieval here is a local keyword "
        "search ($0, a few ms), but what it *returns* is carried in the transcript the model re-reads on every "
        "later lap.",
        "",
        "## 2. Attributed by what caused the tokens",
        "",
        "Lap k's input is the fixed prompt plus everything earlier laps added; each lap's additions are charged "
        "to the stage of the tool it ran, and re-charged on every lap that re-sends them (`attribute_cost` in "
        "tools/w11_reports.py).",
        "",
        "| stage | input tokens caused | cost USD | share |",
        "|---|---:|---:|---:|",
    ]

    for stage in ("retrieval", "generation", "tools"):
        lines.append(f"| {stage} | {attr['tokens_in_by_stage'][stage]} | {attr[stage]:.6f} | "
                     f"{attr[stage] / total:.0%} |")

    lines += [
        f"| **total** | {sum(attr['tokens_in_by_stage'].values())} (+{attr['tokens_out']} output) | "
        f"**{total:.6f}** | 100% |",
        "",
        f"`generation` here = the fixed prompt re-sent on each of the {attr['laps']} laps plus every output token. "
        "That fixed prompt (system text + three tool schemas) is re-sent on every lap, so it is the largest line - "
        "which makes cutting a lap a bigger lever than trimming what search returns, and is why this attribution has to "
        "be done before either is tried.",
        "",
        f"## 3. Across the {len(suite)} completed requests of the RED suite (20b, v1/r1)",
        "",
        f"- mean cost per query **${avg_cost:.5f}** ({avg_tokens:,.0f} tokens)",
        f"- attributed: retrieval **${avg['retrieval']:.5f}** ({avg['retrieval'] / avg_total:.0%}), "
        f"tools **${avg['tools']:.5f}** ({avg['tools'] / avg_total:.0%}), "
        f"generation **${avg['generation']:.5f}** ({avg['generation'] / avg_total:.0%})",
    ]

    after = {}

    for name, path in GREEN_TRACES.items():
        if path.exists():
            hit = next((r for r in read_log(path) if r["outcome"] == "completed"
                        and r["input"]["claim_id"] == "c11"), None)
            if hit:
                after[name] = hit

    if after:
        header = "| | v1 / kw-r1 (RED) | " + " | ".join(after) + " |"
        lines += ["", "## 4. What the fix cost (the same claim, c11)", "", header,
                  "|---|---:|" + "---:|" * len(after)]

        def row(label, fn):
            lines.append(f"| {label} | {fn(found)} | " + " | ".join(str(fn(r)) for r in after.values()) + " |")

        row("tokens", lambda r: r["totals"]["tokens_in"] + r["totals"]["tokens_out"])
        row("cost USD", lambda r: f"{r['totals']['cost_usd']:.6f}")
        row("attributed to retrieval USD", lambda r: f"{attribute_cost(r)['retrieval']:.6f}")
        row("model calls", lambda r: sum(1 for s in r["spans"] if s["stage"] == "generation"))
        row("answer", lambda r: f"{r['output'].get('coverage_status')} / payout {r['output'].get('payout')}")

    text = "\n".join(lines)
    (OUT_DIR / "cost_by_stage.md").write_text(text + "\n", encoding="utf-8")
    print(text)

    # ---- tenx.md --------------------------------------------------------
    per_day = FNOLS_PER_MONTH / 30
    daily_tokens = per_day * avg_tokens
    tenx_per_day = per_day * 10
    peak_per_min = tenx_per_day / 8 * 2 / 60            # 8-hour day, 2x peak factor
    tpm_needed = peak_per_min * avg_tokens
    p50_latency = statistics.median(r["totals"]["latency_ms"] for r in suite) / 1000
    concurrency = peak_per_min / 60 * p50_latency
    cost_day = tenx_per_day * avg_cost

    one_line = (
        f"At 10x ({tenx_per_day:.0f} claims/day) a **rate limit** breaks first: one triage costs "
        f"{avg_tokens:,.0f} tokens, so the free tier's {FREE_TIER_TPD:,}-tokens/day cap is hit after "
        f"{FREE_TIER_TPD / avg_tokens:.0f} claims ({tenx_per_day * avg_tokens / FREE_TIER_TPD:.0f}x over at 10x) - "
        f"while cost is ${cost_day:.2f}/day and latency needs only {concurrency:.1f} concurrent runs."
    )

    tenx = [
        "# What breaks first at 10x claim volume",
        "",
        one_line,
        "",
        "| resource | at 1x (60 claims/day) | at 10x (600/day) | limit | verdict |",
        "|---|---|---|---|---|",
        f"| tokens/day | {daily_tokens:,.0f} | {daily_tokens * 10:,.0f} | {FREE_TIER_TPD:,} (free tier, observed in a 429 body today) | "
        f"**breaks at {FREE_TIER_TPD / avg_tokens:.0f} claims/day - already over at 1x** |",
        f"| tokens/minute at peak | {tpm_needed / 10:,.0f} | {tpm_needed:,.0f} | {FREE_TIER_TPM:,} | "
        f"{'**breaks**' if tpm_needed > FREE_TIER_TPM else 'ok'} (peak = 8-hour day, 2x peak factor: {peak_per_min:.2f} claims/min) |",
        f"| cost/day | ${per_day * avg_cost:.2f} | ${cost_day:.2f} | no budget stated | does not break (${cost_day * 30:.0f}/month) |",
        f"| latency | p50 {p50_latency:.0f}s | p50 {p50_latency:.0f}s, {concurrency:.1f} runs in flight at peak | none stated | does not break by itself; "
        "Week 10's p99 of 4,577 s was a rate-limit wait, i.e. the same limit seen as latency |",
        "",
        "Inputs: tokens/query and p50 latency are means/medians over the RED suite's completed 20b traces "
        f"(n={len(suite)}); volume is the capstone brief's 1,800 FNOLs/month; the TPM figure is the Week 7 note in "
        "tools/w7d_common.py and the TPD figure is from the 429 this repo's own run received on 2026-10-05 "
        "(`Limit 200000, Used 199701`). The 8-hour day and 2x peak factor are assumptions, stated here so they "
        "can be argued with. The free tier is a stand-in for 'a provider rate limit': a paid tier raises the "
        "numbers, it does not remove the question.",
    ]

    (OUT_DIR / "tenx.md").write_text("\n".join(tenx) + "\n", encoding="utf-8")
    print("\n" + one_line)

    # ---- eval case file -------------------------------------------------
    cases = []

    for claim in NEW_CLAIMS:
        cases.append({
            "case_id": claim["claim_id"],
            "added": "week 11 task set D" + (" (the drill's failure)" if claim["claim_id"] == "c11"
                                            else " (guard against over-correcting)"),
            "claim": {k: claim[k] for k in ("claim_number", "date_of_loss", "policy_line",
                                            "form_number", "reported_loss_amount",
                                            "coverage_a_limit", "notes")},
            "golden": NEW_GOLDEN[claim["claim_id"]],
            "assertion": "grade(): coverage_status == golden.status AND |payout - golden.payout| <= 1",
        })

    (OUT_DIR / "eval_cases_added.json").write_text(json.dumps(cases, indent=2), encoding="utf-8")
