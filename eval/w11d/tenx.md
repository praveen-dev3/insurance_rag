# What breaks first at 10x claim volume

At 10x (600 claims/day) a **rate limit** breaks first: one triage costs 7,578 tokens, so the free tier's 200,000-tokens/day cap is hit after 26 claims (23x over at 10x) - while cost is $0.38/day and latency needs only 1.8 concurrent runs.

| resource | at 1x (60 claims/day) | at 10x (600/day) | limit | verdict |
|---|---|---|---|---|
| tokens/day | 454,665 | 4,546,650 | 200,000 (free tier, observed in a 429 body today) | **breaks at 26 claims/day - already over at 1x** |
| tokens/minute at peak | 1,894 | 18,944 | 8,000 | **breaks** (peak = 8-hour day, 2x peak factor: 2.50 claims/min) |
| cost/day | $0.04 | $0.38 | no budget stated | does not break ($11/month) |
| latency | p50 44s | p50 44s, 1.8 runs in flight at peak | none stated | does not break by itself; Week 10's p99 of 4,577 s was a rate-limit wait, i.e. the same limit seen as latency |

Inputs: tokens/query and p50 latency are means/medians over the RED suite's completed 20b traces (n=24); volume is the capstone brief's 1,800 FNOLs/month; the TPM figure is the Week 7 note in tools/w7d_common.py and the TPD figure is from the 429 this repo's own run received on 2026-10-05 (`Limit 200000, Used 199701`). The 8-hour day and 2x peak factor are assumptions, stated here so they can be argued with. The free tier is a stand-in for 'a provider rate limit': a paid tier raises the numbers, it does not remove the question.
