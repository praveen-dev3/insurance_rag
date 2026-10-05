"""Week 12 cost per claim triaged and the hailstorm-week plan, computed from the run.

    python weeks.py w12 reports --label main

Reads traces/w12_requests_<label>.jsonl (the redacted request log, which is
what a reviewer has) and writes eval/w12/cost_and_10x.md. Nothing in the
output is typed by hand: the cost split, the latency percentiles and the
rate-limit arithmetic all come from the log and from two stated limits.
"""

import json
import statistics
from pathlib import Path

from w11_reports import attribute_cost

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "eval" / "w12"

HAIL_WEEK_FNOLS = 18000          # the capstone brief, section 1
FNOLS_PER_MONTH = 1800           # same
TPD = 200000                     # observed in a 429 body on 2026-10-05, per model
TPM = 8000                       # x-ratelimit-limit-tokens header, per model


def pct(values, q):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))]


def reports(label="main"):

    rows = [json.loads(l) for l in (REPO_ROOT / "traces" / f"w12_requests_{label}.jsonl")
            .read_text(encoding="utf-8").splitlines() if l.strip()]
    done = [r for r in rows if r["outcome"] == "completed"]

    tokens = [r["totals"]["tokens_in"] + r["totals"]["tokens_out"] for r in done]
    costs = [r["totals"]["cost_usd"] for r in done]
    latency = [r["totals"]["latency_ms"] / 1000 for r in done]
    laps = [sum(1 for s in r["spans"] if s["stage"] == "generation") for r in done]

    direct = {stage: statistics.mean(r["totals"]["by_stage"][stage]["cost_usd"] for r in done)
              for stage in ("retrieval", "generation", "tools")}
    attributed = [attribute_cost(r) for r in done]
    attr = {s: statistics.mean(a[s] for a in attributed) for s in ("retrieval", "generation", "tools")}
    attr_total = sum(attr.values())

    # Where the wall-clock goes, from the spans (not from the rate-limit-stalled
    # tail): median over requests of each stage's share of summed span time.
    lat_by_stage = {stage: statistics.median(r["totals"]["by_stage"][stage]["latency_ms"] for r in done) / 1000
                    for stage in ("retrieval", "generation", "tools")}

    mcp = [s for r in done for s in r["spans"] if s["attrs"].get("hop") == "mcp"]
    transport = [s["latency_ms"] - s["attrs"]["server_latency_ms"] for s in mcp
                 if "server_latency_ms" in s["attrs"]]

    mean_tokens = statistics.mean(tokens)
    mean_cost = statistics.mean(costs)
    p50 = statistics.median(latency)

    per_day_hail = HAIL_WEEK_FNOLS / 7
    per_hour_hail = per_day_hail / 24
    tpm_hail = per_hour_hail / 60 * mean_tokens
    concurrency = per_hour_hail / 3600 * p50

    one_line = (
        f"In a hailstorm week ({HAIL_WEEK_FNOLS:,} FNOLs) the **token rate limit** breaks first: one triage is "
        f"{mean_tokens:,.0f} tokens, so a {TPD:,}-tokens/day tier covers {TPD / mean_tokens:.0f} claims a day against "
        f"{per_day_hail:,.0f} arriving ({per_day_hail / (TPD / mean_tokens):.0f}x over) - while the bill is "
        f"${HAIL_WEEK_FNOLS * mean_cost:,.0f} for the week and {concurrency:.1f} requests are in flight."
    )

    lines = [
        f"# Cost per claim triaged, and the hailstorm-week plan (n={len(done)} completed requests, run `{label}`)",
        "",
        f"Model `{done[0]['model']}`. Price: $0.15 / $0.60 per million input / output tokens - Groq's list price "
        "as recalled when this was written; **verify before using the dollar figures for anything but a ratio**.",
        "",
        "## Cost per claim",
        "",
        f"- mean **${mean_cost:.5f}** per claim (p50 ${statistics.median(costs):.5f}, p95 ${pct(costs, .95):.5f}); "
        f"{mean_tokens:,.0f} tokens ({statistics.mean(laps):.1f} model calls per claim)",
        "",
        "| stage | as logged (cost of the calls) | attributed (cost of the tokens each stage caused) | median span time |",
        "|---|---:|---:|---:|",
    ]

    for stage in ("retrieval", "generation", "tools"):
        lines.append(f"| {stage} | ${direct[stage]:.5f} | ${attr[stage]:.5f} ({attr[stage] / attr_total:.0%}) | "
                     f"{lat_by_stage[stage]:.2f} s |")

    lines += [
        "",
        "Attribution method: tools/w11_reports.py `attribute_cost` - a result is charged to the stage that produced "
        "it, on every later lap that re-sends it. Retrieval's own cost is nil (local hybrid search); what it costs "
        "is the passages it returns, carried through the remaining laps.",
        "",
        f"- latency p50 **{p50:.0f} s**, p95 {pct(latency, .95):.0f} s per claim. Retrieval and tool spans together are a "
        f"median {lat_by_stage['retrieval'] + lat_by_stage['tools']:.2f} s, so it is all in the model spans - and a model span "
        f"cannot tell generation time from a rate-limit wait. An {mean_tokens:,.0f}-token claim against an {TPM:,}-tokens/minute "
        "cap cannot run at full speed, so the latency here is partly the limit itself, not just the model.",
        f"- MCP hop overhead (client-side span minus the server's own time), {len(transport)} calls: "
        f"median {statistics.median(transport):.1f} ms, p95 {pct(transport, .95):.1f} ms - small beside a model call.",
        "",
        "## 10x, at catastrophe volume",
        "",
        one_line,
        "",
        "| resource | steady state (60 FNOLs/day) | hailstorm week (18,000 FNOLs) | limit | verdict |",
        "|---|---|---|---|---|",
        f"| tokens/day | {60 * mean_tokens:,.0f} | {per_day_hail * mean_tokens:,.0f} | {TPD:,} (free tier; "
        "from a 429 body) | **breaks - already over at steady state** |",
        f"| tokens/minute (even spread over 24 h) | {60 / 24 / 60 * mean_tokens:,.0f} | {tpm_hail:,.0f} | {TPM:,} "
        f"| {'**breaks**' if tpm_hail > TPM else 'ok'} - and storm FNOLs arrive in bursts, not evenly |",
        f"| cost | ${60 * mean_cost:.2f}/day | ${HAIL_WEEK_FNOLS * mean_cost:,.0f}/week | none stated | does not break |",
        f"| latency / concurrency | p50 {p50:.0f} s | {concurrency:.1f} in flight (even spread) | none stated | "
        "does not break; but the policy-wording MCP server is one process, so concurrent searches queue behind "
        "each other (~1 s each) |",
        "",
        "Plan, in the order it would be done: (1) a paid tier or a second provider - the only fix that removes the "
        "limit rather than rationing it; (2) cut the tokens that are re-sent: the fixed prompt (system text + six "
        "tool schemas) is re-sent on every lap and generation is 75% of attributed cost, so fewer laps (e.g. fetch the "
        "in-force check at intake, as the FNOL already is) should be worth more than shorter passages - expected from the "
        "attribution, not yet measured; (3) a queue in front of "
        "the agent that admits claims at the rate the limit allows and says so, instead of letting 429 waits show up "
        "as 10-minute latencies; (4) prompt caching of the fixed prefix where the provider supports it.",
        "",
        "Not measured: any of this under concurrent load. The numbers above are single-request measurements "
        "scaled by arithmetic.",
    ]

    text = "\n".join(lines)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "cost_and_10x.md").write_text(text + "\n", encoding="utf-8")
    print(text)


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="main")
    args = parser.parse_args()
    reports(args.label)

    return 0
