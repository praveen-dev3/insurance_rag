# Week 10 Task Set D: verdict - KEEP

Pass rate tied at 7/10 both arms; token multiplier 0.9x (63081 vs 72469 tokens, -13%) - the orchestrator did NOT cost more here, contrary to the usual expectation for splitting one call into three hand-offs.
p99 latency favors the orchestrator by a wide margin (64.0s vs 4577.3s) - but that single-agent outlier is one Groq free-tier rate-limit stall on c01, not evidence the architecture itself is slower.
Dominant cost: `orchestrator -> exclusions-worker`, 84% of orchestrator tokens - splitting the notes summary out did not pay for itself in savings, the multi-lap exclusions search still is the bill, same as the single agent's search loop.
**Sunk-cost warning, named out loud:** two weeks (7-9) of tooling were built for the single agent - that history is not a reason to keep it now that a cheaper option ties it on pass rate, and it is equally not a reason to switch just because the orchestrator is newer.
**Verdict: KEEP** - tied pass rate (7/10 both) is not itself a reason to switch, but a strictly cheaper bill (0.9x, not >1x) with no latency downside is: the narrow-prompt-fewer-tools worker split earns its keep on cost alone here, even though it did not buy a single extra correct claim.
