# Trace continuity - one trace id, FNOL in to referral out

- requests checked: **25**; requests whose id survived the agent hop *and* the MCP hop with every server span accounted for: **25/25**
- checks per request: request-log line exists; referral trace id == log trace id; every MCP call has a server span on disk under the same id; the server spans are also folded into the request log; every span carries latency, tokens and cost

Example, `req-a0c11c419245` (case w27):

| span | stage | latency ms | tokens in/out | cost USD | server ms |
|---|---|---|---|---|---|
| mcp.get_fnol | tools | 3.1 | 0/0 | 0.000000 | 0.6 |
| llm.lap1 | generation | 1708.5 | 1524/48 | 0.000257 | - |
| mcp.get_fnol | tools | 1.3 | 0/0 | 0.000000 | 0.2 |
| llm.lap2 | generation | 695.7 | 1674/47 | 0.000279 | - |
| mcp.check_coverage_in_force | tools | 1.1 | 0/0 | 0.000000 | 0.1 |
| llm.lap3 | generation | 696.4 | 1816/127 | 0.000349 | - |
