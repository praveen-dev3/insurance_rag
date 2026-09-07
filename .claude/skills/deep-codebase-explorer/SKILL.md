---
name: deep-codebase-explorer
description: Use when the user asks any cross-module, debugging, refactoring, blast-radius, or production-incident question about this codebase. Auto-routes to the right combination of tribal skills (.claude/skills/tribal/), GitNexus knowledge graph (CLI: `npx -y gitnexus@1.6.4-rc.90`), and RLM sub-agent dispatch. Routes to the lightest mode that fully answers the question — most code prompts are answered by reading the relevant file(s) directly — and escalates to ULTIMATE (tribal + graph + sub-agents) only for genuinely high-stakes or cross-module work (production/incident, blast-radius/refactor, money-flow); GitNexus steps run only when a live index is confirmed. Manual override prefixes: `ULTIMATE:`, `vanilla:`, `skills only:`, `RLM:`.
---

# Deep Codebase Explorer (Smart Auto-Router)

## What this skill does

Routes any code question through the right combination of three layers — tribal skills (semantic), GitNexus (structural graph), and RLM (recursive sub-agents) — without requiring the user to type prefixes for 95% of cases.

## Routing logic

### Step 1: Check for explicit prefix

If the user's question starts with one of these prefixes, strip the prefix, **announce the mode on line 1 of your response**, and use that mode. Do NOT auto-route.

| Prefix | Mode | Behavior |
|---|---|---|
| `vanilla:` | vanilla | Just Read/Grep. No skills, no graph, no sub-agents. |
| `skills only:` / `skill only:` / `skills:` | skills only | Tribal skills only. |
| `graph only:` / `nexus:` | graph only | GitNexus only. |
| `RLM:` | pure RLM | Sub-agents only. |
| `skills + graph:` / `AG:` | AG | Skills + graph (no RLM). |
| `RLM + skill:` / `RLM + skills:` | hybrid | Skills + RLM. |
| `graph + RLM:` | graph+RLM | Graph + RLM. |
| `ULTIMATE:` | ULTIMATE | All three layers. |

### Step 2: No prefix? Auto-route by question shape

**Default = the lightest mode that fully answers the question.** Most code prompts (a single-symbol lookup, a localized edit, "where is X", "what does this function do") are answered best by reading the relevant file(s) directly — that IS the grounding. Reserve heavier modes for questions that genuinely span the codebase. Load a tribal skill when the question touches that module's business rules/gotchas; consult GitNexus when you need cross-module structure AND the index is live (see "GitNexus availability" below); dispatch sub-agents only when there is real, independent breadth to fan out. Escalate to ULTIMATE for the high-stakes shapes listed below. The failure mode to avoid is over-grounding — wrapping a one-line answer in unrelated tribal caveats, an empty graph call, and a sub-agent chain that reasons from second-hand notes — at least as much as under-grounding.

**Stay at vanilla (no skills / graph / sub-agents) when the prompt has nothing in the codebase to explore:**

- Pure conversational, opinion, or planning chat → **vanilla** or **skills only**
- Trivial non-code lookup (`typo`, `log line` wording, a one-line string) → **vanilla**

**Extra-careful signals — escalate to ULTIMATE, and never stop early or skip a layer:**

- **Production / risk:** `production`, `incident`, `outage`, `regression`, `kill switch`, `fail open`, `audit`, `compliance`, `security`
- **Blast radius:** `rename`, `refactor`, `blast radius`, `what depends on`, `what breaks`, `every code path`, `all callers`, `safe to change`
- **Money flow:** `refund`, `charge`, `rebill`, `dispute`, `chargeback`, `idempotency`, `race condition`

These are the prompt shapes to escalate to ULTIMATE for (up from the lighter default); on them, never skip a layer or stop at partial findings — that is especially dangerous here.

**Question shape:**

- Multi-module / cross-system / trace / debug / dependency / refactor / blast-radius question → **ULTIMATE** (or **AG** when the graph is live and no synthesis is needed)
- Single-symbol factual lookup or localized edit → read the file directly (**vanilla**); add a tribal skill only if the symbol sits on a money / security / kill-switch path
- Pure chat / non-code / trivial string → **vanilla**

### Step 3: Self-detect what's available in the current repo

Before invoking layers:
- Check `.claude/skills/tribal/` exists → Skills layer available
- Confirm a **live** GitNexus index — `mcp__gitnexus__list_repos` returns this repo (non-empty), or `npx -y gitnexus@1.6.4-rc.90 status` reports it indexed → Graph layer available. Do NOT infer availability from `.claude/skills/generated/` existing: that directory persists even when the index is empty or stale, and (per the worktree note in the repo `CLAUDE.md`) a `git worktree` is its own index path that is usually absent.
- Sub-agents always available

If a chosen layer isn't available, gracefully degrade:
- AG selected but no graph index → fall back to skills-only AND tell user "re-run the claude-stack bootstrap to enable graph mode"
- ULTIMATE selected but no graph → fall back to skills + RLM

### Step 4: Fall-forward

If AG is running and hits a question the graph + skills cannot answer (cross-system reasoning, runtime behavior, deployment specifics, error message content, code-body details the graph doesn't expose), escalate to ULTIMATE rather than guessing. Note the fall-forward in your audit trail.

## Mode behaviors

### AG (skills + graph) — grounding floor, no sub-agents

1. Identify which tribal skills match the question (read SKILL.md files in `.claude/skills/tribal/` whose name or description matches).
2. Use GitNexus tools first for structural questions:
   - `npx -y gitnexus@1.6.4-rc.90 context <symbol> -f <path>` → 360-degree view (callers, callees)
   - `npx -y gitnexus@1.6.4-rc.90 impact <symbol>` → blast radius with confidence scores
   - `npx -y gitnexus@1.6.4-rc.90 cypher "<query>"` → custom graph traversal
3. Read code body via `Read` tool only when needed for body details.
4. NO sub-agent dispatch.

### ULTIMATE — full stack

Order of operations (always):

1. **Load relevant tribal skills first.** Read SKILL.md files from `.claude/skills/tribal/` whose names or descriptions match. These give you the "why" — gotchas, fail-open behavior, business invariants, kill switches.
2. **Use GitNexus for structural questions when the index is live.** `context`, `impact`, `cypher`, `query`, `detect_changes` — pre-computed, with confidence scores. First confirm the index exists: `mcp__gitnexus__list_repos` must be non-empty. If it returns `[]` or any gitnexus tool errors "No indexed repositories", the graph is NOT built — fall back to Grep / the TypeScript LSP and say so, rather than calling a dead tool or trusting quoted symbol counts.
3. **Before editing a symbol, read its callers.** When the index is live, `impact` gives a risk-scored blast radius — surface HIGH/CRITICAL risk and pause for confirmation. When it is not, get the callers from the LSP (find-references / call-hierarchy) or Grep. The requirement is "know who calls this before you change it," not "the gitnexus tool specifically." Never fabricate a blast radius from memory or quoted counts.
4. **Before committing, verify scope.** `gitnexus_detect_changes()` if the index is live; otherwise `git diff` plus the repo's typecheck/build command — the stronger, always-available check. Abort and re-investigate if the affected scope is broader than expected.
5. **Dispatch sub-agents only for synthesis or graph gaps.** When you need to confirm a fact in code body, resolve a tribal-vs-graph disagreement, or do cross-system reasoning the graph cannot represent. See "RLM Pattern" below for the discipline.

**Disagreement is a finding.** If GitNexus says X depends on Y but a tribal skill says they are decoupled, surface the disagreement explicitly in your answer. Do not silently pick a side.

### Hybrid modes (`RLM+skills`, `graph+RLM`)

Treat these as ULTIMATE with one layer omitted. Apply the RLM Pattern below for sub-agent discipline. The omitted layer is the variable being isolated (usually for measurement/comparison runs); answer questions about that omitted layer's gap honestly.

### Pure RLM mode

Use ONLY sub-agents (no tribal skills, no GitNexus). Apply the RLM Pattern below. Useful for measurement runs that isolate sub-agent value.

### vanilla

Default Claude. No skills loaded, no graph queries, no sub-agents. Just Read/Grep/Bash.

## RLM Pattern (applies to RLM, hybrid, and ULTIMATE modes)

When dispatching sub-agents (Task tool with `subagent_type: Explore` for read-only work, `general-purpose` otherwise), follow these rules. They are what made the bake-off results work; skipping them causes context bloat and token burn.

1. **Delegate for breadth, not depth.** Spawn a sub-agent when there are many independent files/areas to cover in parallel. For the file(s) load-bearing to your answer, Read them directly — you must see the real code (exact guards, sentinel values, integer-cents handling) to be correct, and the repo's own rule is "never assert a behavior exists without reading it." Do not fan out a sub-agent merely to read one file you could read yourself.
2. **Narrow question, short answer cap.** Each sub-agent gets ONE focused question and a 1-3 sentence answer cap. If a sub-agent returns more than ~5 sentences, your prompt was too broad. Narrow it next time.
3. **Keep notes, not content.** After each sub-agent return, write a one-line note in your reasoning about what you learned. Plan the next step from notes, never from raw file content.
4. **Aim for 5-15 sub-agent calls.** ULTIMATE mode usually needs FEWER because GitNexus answers structural questions deterministically (callers, callees, blast radius).
5. **Hard stop at 20.** If exploration would need more than ~20 sub-agent calls, stop and report partial findings. Don't burn tokens chasing diminishing returns.
6. **Independence only.** Parallel sub-agents must NOT share state. If work is ordered or dependent, run sequentially.
7. **Synthesize from notes, then answer.** Never paste raw sub-agent output into your final response. The audit trail counts each sub-agent call.

### Tool preference (RLM, hybrid, ULTIMATE)

When in any mode that uses sub-agents, prefer GitNexus tools over Bash grep for structural questions. The graph is deterministic and pre-computed; grep is slow and noisy in comparison.

Use GitNexus first:
- `mcp__gitnexus__impact` (or `npx -y gitnexus@1.6.4-rc.90 impact <symbol>`) for "what depends on X" / blast radius
- `mcp__gitnexus__query` (or `npx -y gitnexus@1.6.4-rc.90 query "<text>"`) for process-grouped semantic search
- `mcp__gitnexus__context` (or `npx -y gitnexus@1.6.4-rc.90 context <name> -f <path>`) for the 360-degree view (callers, callees, processes)
- `mcp__gitnexus__detect_changes` for git-diff impact mapping
- `mcp__gitnexus__cypher` for custom graph traversals

Fall back to Bash + sub-agents only when:
- The question is about tribal knowledge (gotchas, business rules, fail-open behavior) → read the relevant `.claude/skills/tribal/` SKILL.md.
- The graph cannot answer (cross-system reasoning, runtime behavior, deployment specifics, error message content).
- You need to read actual code body to confirm something the graph found.

### Red flags (stop and reconsider)

- **NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.** STOP and address before proceeding with any edit.
- **NEVER rename symbols with find-and-replace or grep-based refactors.** Use `gitnexus_rename` (or `npx -y gitnexus@1.6.4-rc.90 rename`), which understands the call graph. STOP if you catch yourself drafting a rename via `sed`, `Edit replace_all`, or `grep -lr`.
- **NEVER commit without running `detect_changes`.** STOP if you are about to call `git commit` without verifying affected scope first.
- About to edit a symbol without running `impact` first → STOP, run impact analysis.
- About to fan out a sub-agent to read a single file central to your answer → just Read it yourself; you need the real code, not a paraphrase.
- About to dump an entire 500-line file into reasoning when you need one function → Read with a line range, or ask a sub-agent a narrow question if it is one of many files.
- Sub-agent count climbing past 20 → stop, report partial findings.
- In ULTIMATE but reaching for Bash grep before GitNexus → stop, the graph has the answer for structural questions.
- In pure RLM mode but tempted to read a tribal skill or call GitNexus → stop, that is hybrid or ULTIMATE.
- Forgot to announce the mode on line 1 of your response → fix before continuing.
- Routing to ULTIMATE for a single-symbol lookup or a localized edit → over-escalation; read the file directly and answer.
- Skipping the file read on a money / security / kill-switch question, or answering it from memory or a stale skill → under-grounding; read the code (and load the tribal skill) before answering.

## Worked example (ULTIMATE)

Q: `ULTIMATE: Trace what happens when [some user action] triggers [some domain operation].`

1. Load tribal skills: `Read .claude/skills/tribal/<area-1>/SKILL.md`, `<area-2>/SKILL.md`, `<area-3>/SKILL.md`. These give the kill-switch / fail-open / fire-and-forget gotchas and the business invariants.
2. GitNexus structural map: `npx -y gitnexus@1.6.4-rc.90 context <symbol> -f <path>` → returns the canonical UID. Then `context --uid` for callers (incoming) and callees (outgoing). Get the call graph deterministically without reading any file.
3. GitNexus blast radius: `npx -y gitnexus@1.6.4-rc.90 impact <Symbol.method>` → identifies every dependent caller (webhook, cron, controller, etc.). Confidence scores included.
4. Confirm in code body only where graph + skills disagree, or where you need a literal value (constant, enum, response shape). Sub-agent on a single function with a 2-sentence answer cap.
5. Synthesize from notes. Surface any tribal-vs-graph disagreement explicitly.

Typical ULTIMATE counts: 2-4 GitNexus tool calls, 0-3 sub-agent calls, 0 Bash searches, 0-2 Reads.

## Output format

For ULTIMATE / multi-agent / high-stakes runs, end with an audit trail so the work is not a black box. For light answers (a direct read, a single-symbol lookup), skip it — a one-line answer should not carry a multi-section ledger (this honors the repo's "prose by default" rule).

```
---
**Audit trail**
- Mode: <AG / ULTIMATE / hybrid / etc.> (note any fall-forward)
- Tribal skills loaded: <list>
- Files investigated: <list>
- Sub-agent questions: <numbered list>
- GitNexus tool calls: <numbered list with exact tool + arg>
- Tool counts: { GitNexus: N, Task: N, Bash: N, Read: N }
- Estimated tokens: ~<N>
```
