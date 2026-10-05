# Cost per claim triaged, and the hailstorm-week plan (n=25 completed requests, run `main`)

Model `openai/gpt-oss-120b`. Price: $0.15 / $0.60 per million input / output tokens - Groq's list price as recalled when this was written; **verify before using the dollar figures for anything but a ratio**.

## Cost per claim

- mean **$0.00196** per claim (p50 $0.00192, p95 $0.00283); 11,256 tokens (5.0 model calls per claim)

| stage | as logged (cost of the calls) | attributed (cost of the tokens each stage caused) | median span time |
|---|---:|---:|---:|
| retrieval | $0.00000 | $0.00029 (15%) | 0.53 s |
| generation | $0.00196 | $0.00148 (75%) | 45.09 s |
| tools | $0.00000 | $0.00019 (10%) | 0.01 s |

Attribution method: tools/w11_reports.py `attribute_cost` - a result is charged to the stage that produced it, on every later lap that re-sends it. Retrieval's own cost is nil (local hybrid search); what it costs is the passages it returns, carried through the remaining laps.

- latency p50 **46 s**, p95 99 s per claim. Retrieval and tool spans together are a median 0.54 s, so it is all in the model spans - and a model span cannot tell generation time from a rate-limit wait. An 11,256-token claim against an 8,000-tokens/minute cap cannot run at full speed, so the latency here is partly the limit itself, not just the model.
- MCP hop overhead (client-side span minus the server's own time), 116 calls: median 1.2 ms, p95 2.2 ms - small beside a model call.

## 10x, at catastrophe volume

In a hailstorm week (18,000 FNOLs) the **token rate limit** breaks first: one triage is 11,256 tokens, so a 200,000-tokens/day tier covers 18 claims a day against 2,571 arriving (145x over) - while the bill is $35 for the week and 1.4 requests are in flight.

| resource | steady state (60 FNOLs/day) | hailstorm week (18,000 FNOLs) | limit | verdict |
|---|---|---|---|---|
| tokens/day | 675,379 | 28,944,823 | 200,000 (free tier; from a 429 body) | **breaks - already over at steady state** |
| tokens/minute (even spread over 24 h) | 469 | 20,101 | 8,000 | **breaks** - and storm FNOLs arrive in bursts, not evenly |
| cost | $0.12/day | $35/week | none stated | does not break |
| latency / concurrency | p50 46 s | 1.4 in flight (even spread) | none stated | does not break; but the policy-wording MCP server is one process, so concurrent searches queue behind each other (~1 s each) |

Plan, in the order it would be done: (1) a paid tier or a second provider - the only fix that removes the limit rather than rationing it; (2) cut the tokens that are re-sent: the fixed prompt (system text + six tool schemas) is re-sent on every lap and generation is 75% of attributed cost, so fewer laps (e.g. fetch the in-force check at intake, as the FNOL already is) should be worth more than shorter passages - expected from the attribution, not yet measured; (3) a queue in front of the agent that admits claims at the rate the limit allows and says so, instead of letting 429 waits show up as 10-minute latencies; (4) prompt caching of the fixed prefix where the provider supports it.

Not measured: any of this under concurrent load. The numbers above are single-request measurements scaled by arithmetic.
