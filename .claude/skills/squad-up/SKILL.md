---
name: squad-up
description: Multi-phase agent pipeline for non-trivial work — features, refactors, investigations. Triggers on "squad up [task]", "squad up ULTIMATE [task]", or "squad up fast [task]". Orchestrates Direction → Plan → Workers → Critic → Verifier → Code Reviewer → Delivery with HITL gates. Phase 1 Planner uses ULTIMATE depth; Phase 2 Workers use AG; Phase 4.5 Code Reviewer uses ULTIMATE.
---

# SQUAD UP - AGENT TEAM SYSTEM

Activate with any variation of: **"squad up [task]"**
Examples: `squad up`, `Squad Up`, `SQUAD UP`, `squad up to [task]`

**"squad up" always triggers the full pipeline. No routing, no complexity checks, no shortcuts.** The full phase sequence runs every time. Use escape hatches (`fast mode`, `solo mode`) only when explicitly requested mid-squad.

Without "squad up", respond normally as a standard Claude session.

---

## Trigger variants

| Trigger | Modes used per phase | When |
|---|---|---|
| `squad up [task]` | Planner=ULTIMATE, Workers=AG, Code Reviewer=ULTIMATE | Default for most work |
| `squad up ULTIMATE [task]` | Every phase uses ULTIMATE depth | Safety-critical / cross-system / security |
| `squad up fast [task]` | Plan→Workers→Critic→Verifier once, no re-delegation | Time-pressured |

## HITL boundaries (apply to every phase)

The squad pipeline is autonomous WITHIN the local working tree. Anything that touches state beyond the local tree is HITL — the user runs it, or Claude Code prompts before running. **Never bypass these.**

- **No git mutations without prompting:** `git checkout`, `git switch`, `git commit`, `git push`, `git pull`, `git merge`, `git rebase`, `git reset`, `git stash push/pop`, `git branch -d/-D`. The repo's `.claude/settings.json` puts these on the `ask` list so they prompt even with `bypassPermissions`.
- **No PR/issue mutations:** `gh pr create`, `gh pr merge`, `gh issue create`, etc. all prompt.
- **No ticketing/wiki writes (Jira/Confluence/Linear/Notion/etc.):** ticket status change, comment, edit, worklog, link, page create/update. All prompt.
- **The pipeline ends with a SQUAD_DELIVERY file and a chat summary.** Branch/commit/push/PR/ticket-update are all manual user actions after delivery, even if Claude has draft commit messages prepared.

## Mode breakdown across the pipeline

| Phase | Mode | Why |
|---|---|---|
| Phase 1 Planner | ULTIMATE | Plans set everything else |
| Phase 2 Workers | AG | Each worker scoped narrow |
| Phase 3 Critic | read-mode | Reviews handoffs, no new context |
| Phase 4 Verifier | read-mode | Same |
| Phase 4.5 Code Reviewer | ULTIMATE | Last line before merge |

---

## PHASE 0 - PROMPT CLINIC + DIRECTION

### Step 1 - Prompt Clinic (AskUserQuestion round 1)

Before writing the strategic brief, interrogate the prompt itself. Make ONE AskUserQuestion call (max 4 questions):

**Question 1 - Harness setup (always asked).** Analyze the prompt against the decision matrix (see `/squad-architect`) and recommend how to run it. Present the most relevant shapes below as the options (AskUserQuestion allows at most 4, so pick the 4 that fit THIS task), recommendation listed FIRST and marked "(Recommended)":
- **Plain squad** - success criteria are judgment-laden; verification lives in the Critic/Verifier lanes
- **Goal-shaped squad** - success is provable by a command. If picked, rewrite the task with a GOAL block before Phase 1: the exact pass command(s), the output that counts as success, and "stop + escalate with partial delivery after N loops". The Verifier must re-run the GOAL command itself; worker claims never satisfy it.
- **Ultracode workflow (or squad + workflow)** - recommend when the task is WIDE and parallelizable: an audit or sweep, a change/migration across many files or endpoints, a blast radius over roughly 15+ files, or an exhaustive find-everything hunt. A deterministic multi-agent Workflow (pipeline/parallel fan-out, loop-until-dry, judge panel) covers ground a linear squad cannot, or runs the squad lanes AS workflow stages. Signals: the prompt says audit/sweep/every/all/migrate, or the change surface is large. Do NOT offer this for a scoped feature or single-endpoint fix - a linear squad wins there. Picking it is the explicit Workflow opt-in.
- **Squad + /loop follow-up** - only when something EXTERNAL needs recurring polling (CI/CodeRabbit after a push, a remote job, a file appearing). The loop never replaces pipeline phases; output the exact /loop command at delivery time for the user to run.
- **Lighter than a squad** - when the decision matrix says solo or a single delegated agent fits better. Only downgrade if the user picks this option; picking it counts as the explicit escape-hatch request, so this does not violate the no-auto-routing rule.

**Questions 2-4 - Prompt-specific clarifications (only if real).** Mine THIS prompt for ambiguities that would change the plan: scope boundaries, what "done" means concretely, mutating vs read-only, target repo/branch, sample sizes, deliverable locations. Skip anything the prompt, memory, or the repo already answers. Zero clarifying questions is fine; never pad to fill the call.

Fold the answers into the work: if goal-shaped, show the upgraded prompt (original intent + GOAL block) inline before the brief; if loop, state the /loop command that will be suggested at delivery.

### Step 2 - Validation workflow ideas (AskUserQuestion round 2)

After round 1 is answered, invent up to 4 validation workflows tailored to THIS task: what a multi-agent Workflow could check about the deliverable that the squad's own lanes will not already prove (independent recomputation of results, adversarial review lenses, parity against a source of truth, regression sweep over consumers). Present them as ONE multiSelect AskUserQuestion; each option = workflow name + what it validates on this task + rough agent count, recommended picks listed first and marked "(Recommended)". Existing `.claude/workflows/` scripts: if the repo has none, no existing-script option appears at all. If one or two are relevant to this task, give each its own option instead of inventing a duplicate. If three or more are relevant, collapse them into a SINGLE option "All matching codebase workflows (N)" with the script names in its description; never burn option slots enumerating a large library. If nothing would add value beyond the pipeline's own Critic/Verifier/Code Reviewer, skip this round entirely; never pad. Do NOT add a "create your own" option (a plain option cannot accept typing); instead the question text must say that checking "Other" lets the user type their own workflow idea inline, and that text is treated as a to-author workflow spec exactly like a checked option.

Checked ideas flow into the plan: the Planner specifies each as either an existing script to run or a one-off to author (as a worker lane), and they execute in Phase 4.5 BEFORE `squad-code-reviewer`, feeding it their confirmed findings. The checkbox selection is the explicit user opt-in required by the Workflow tool (Claude Code's multi-agent orchestration tool, which is what executes these scripts in Phase 4.5). Record the selection in the plan's `## Validation Workflows` section so `squad resume` honors it.

### Step 3 - Strategic brief

Output a strategic brief:

- What are we actually solving?
- What is the riskiest assumption?
- What approach will we take?
- Does any part of this touch **irreversible actions** (send emails, delete data, deploy, make API calls that can't be undone)?
- Does any part of this consume **untrusted external content** (URLs, uploaded docs, third-party APIs, user-submitted data)?

Then ask:

> **"Approve direction? (yes / adjust: [your feedback])"**

-> **STOP. Wait for response before continuing.**

---

## PHASE 1 - PLANNER AGENT

Once direction is approved, the Planner activates.

**PERSONA:** Staff-level engineering lead. Thinks in systems, dependencies, and failure modes. Dispatch to the `squad-planner` subagent. Pre-load relevant tribal skills (`.claude/skills/tribal/`) + query GitNexus for affected modules + dispatch sub-agents to verify tribal invariants before drafting. Plans automatically account for the codebase's documented gotchas — fail-open guards, silent fallbacks, fire-and-forget side effects, bypass paths — as surfaced by the tribal skills and the graph. Every code lane's DoD must name the exact verification command `squad-verifier` will re-run.

Output TWO things simultaneously:
1. The full plan content displayed in chat so you can review it inline
2. The same content saved as a file: **`SQUAD_PLAN_[task-slug]_[YYYY-MM-DD].md`**

---

### Plan File Format

```markdown
# SQUAD PLAN
**Task:** [original request]
**Date:** [YYYY-MM-DD]
**Status:** AWAITING APPROVAL
**Mode:** SEQUENTIAL / PARALLEL / MIXED
**Base Commit:** [git SHA at plan creation, for regression diffing]

---

## Strategic Direction
[2-3 sentences: what we're solving, why this approach, key constraint]

---

## Execution Overview
| Field | Value |
|-------|-------|
| Total Workers | [N] |
| Global Loop Cap | 8 total agent loops max before escalation |
| Est. Handoff Size per Worker | ~1,000-2,000 tokens |
| Irreversible Actions Present | YES / NO |
| Untrusted External Content | YES / NO |

---

## Worker Breakdown

### Worker 1 - [Name]
| Field | Detail |
|-------|--------|
| Persona | [e.g. Senior Backend Engineer] |
| Scope | [exactly what they build or produce] |
| Tools | [code / search / write / analyze] |
| Agent Type | [general-purpose / Explore / code-reviewer / etc.] |
| Depends On | [none / Worker N] |
| Execution | [SEQUENTIAL / PARALLEL] |
| Reversible | YES / NO - [if NO, explain what action and why it can't be undone] |
| Touches Untrusted Content | YES / NO - [if YES, flag for sanitization before handoff] |

**Definition of Done:**
- [ ] [specific, verifiable success criterion 1]
- [ ] [specific, verifiable success criterion 2]
- [ ] [specific, verifiable success criterion 3]

**Output Contract** (max 1,000-2,000 tokens passed forward):
- Delivers: [what gets handed off]
- Format: [schema / file / code / doc]
- Next worker needs: [specific inputs only - no raw dumps]

---

### Worker 2 - [Name]
[repeat pattern]

---

## Execution Trace
[Updated live as workers complete. This is the checkpoint/resume record.]

| Worker | Status | Loop # | Notes |
|--------|--------|--------|-------|
| Worker 1 | PENDING | - | - |
| Worker 2 | PENDING | - | - |

---

## Risk Flags
| # | Risk | Decision Made |
|---|------|---------------|
| 1 | [ambiguous requirement] | [assumed X] |
| 2 | [potential failure point] | [mitigation] |
| 3 | [irreversible action] | [HITL gate will trigger] |
| 4 | [untrusted content source] | [sanitization step added] |

---

## Validation Workflows
[The workflow ideas the user checked in Phase 0 round 2. Each is an existing .claude/workflows/ script to run or a one-off to author. Omit section if none selected.]

| Workflow | Existing / To author | Validates on THIS task | Est. agents |
|----------|----------------------|------------------------|-------------|
| [name] | [existing script path / to author] | [what it checks here] | [N] |

---

## Approval

**Approve:** `yes` or `go`
**Adjust a worker:** `adjust worker [N]: [feedback]`
**Add a worker:** `add worker: [description]`
**Remove a worker:** `remove worker [N]`
**Restart plan:** `replan`

> No workers spin up until you explicitly approve.
```

After outputting the file:

> **"HITL GATE: Plan ready. Review the full plan above.**
> **Reply `yes` to spin up workers, or give me adjustments."**

-> **STOP. Do not execute any workers until approved.**

---

## PHASE 2 - WORKER AGENTS

Only activates after HITL Gate approval. Each worker queries the knowledge graph + loads tribal skills for their lane. Handoff contracts cite real file:line. Confidence scores back themselves with evidence (lint output, tests, GitNexus impact analysis).

### Default Definition of Done (auto-included)

Every worker's DoD automatically includes these baseline checks in addition to task-specific criteria:

**For code-producing workers:**
- [ ] Code compiles/builds with zero new errors. Run the project's linter/analyzer per the repo-root `CLAUDE.md` "Essential commands". Do NOT guess the command.
- [ ] Run existing tests, zero new failures.
- [ ] **New code requires new tests.** For every new function, endpoint, action, or hook, add a sibling test using the repo's existing framework. Do NOT modify or skip existing tests to make new code pass.
- [ ] **For high-stakes paths** (money flow, auth/permissions, security, public APIs, state mutations, SSR hydration), also run the relevant integration/e2e suite. Identify the exact command from the repo-root `CLAUDE.md`.
- [ ] No unrelated modifications outside the worker's scope.

**For non-code workers (research, docs, analysis):**
- [ ] Output matches requested format
- [ ] No hallucinated file paths, function names, or API references (verify they exist)

### Context Isolation Rules (non-negotiable)

- Every worker runs in **isolated context** - it receives only its specific instruction and the handoff contract from its dependency, nothing else
- Workers **never** see the full conversation history or other workers' raw outputs
- Workers **never** trigger compaction mid-task - if approaching context limits, stop immediately, return whatever is complete via the handoff contract, and flag it as partial
- Handoff contracts are **hard-capped at 1,000-2,000 tokens** - compress to essentials, never dump raw output forward
- If a worker consumes **untrusted external content** (flagged in the plan), its output must include an explicit `TRUST FLAG` before being passed to the next worker
- **Parallel code-writing workers** must use `isolation: "worktree"` to avoid file conflicts, with a merge step after completion

### Worker-to-Agent Mapping

Workers should specify which subagent type to use for real parallel execution. Common mappings:

The squad roles are real subagent files in `.claude/agents/`. Prefer them; they carry the `fable-rigor` evidence contract:

| Worker Persona | Agent Type | Fallback |
|---|---|---|
| Phase 1 Planner | `squad-planner` | inline ULTIMATE planning |
| Implementer / builder | `squad-implementer` | `general-purpose` |
| Phase 3 Critic | `squad-critic` | inline read-mode pass |
| Phase 4 Verifier (independent refuter) | `squad-verifier` | `general-purpose` with the refuter contract spelled out |
| Phase 4.5 Code Reviewer | `squad-code-reviewer` | `pr-review-toolkit:code-reviewer` |
| Code researcher / explorer | `code-explorer` | `Explore` |
| DB migration review | `migration-reviewer` | `general-purpose` |
| Architecture designer | `feature-dev:code-architect` | `general-purpose` |

Some repos ship their own domain agents (e.g. a data-parity validator). Use one when the repo provides it; otherwise fall back to `general-purpose` with the check spelled out.

Plugin-namespaced agents (anything with `:` in the type) are only available if the corresponding plugin is installed. Verify with the available-skills list in the system context. If unavailable, use the fallback. Default to `general-purpose` if no clear match. Handoff contract format must be specified in the agent's prompt so output is consistent.

**Verifier independence is non-negotiable:** the agent that produced an artifact never grades it. Phase 3, Phase 4, and Phase 4.5 always run in agents that did not write the code, and `squad-verifier` re-runs every cited verification command itself rather than trusting pasted output.

Not sure whether a task needs a squad at all? Run `/squad-architect [task]` to route it (solo vs delegated agent vs full squad vs goal/loop/workflow) before spinning anything up.

### Build/lint/test commands

Workers must run the right commands for the repo. Do NOT guess:
- Read `.claude/stack-profile.md` first if present — `squad setup` generates it with this project's resolved lint/test/typecheck/build commands, test conventions, and a stack-specific review lens (pytest/ruff for Python, `go test`/`go vet` for Go, etc.).
- Else read the repo-root `CLAUDE.md` "Essential commands" section for the canonical lint/build/test commands.
- If neither has them, infer from `package.json` scripts, `Makefile` targets, `pyproject.toml` / `Cargo.toml` / `go.mod` / `build.gradle`, and the lockfile (for the package manager). In a monorepo, run per-package/per-service from the right directory.
- Surface uncertainty rather than guessing — ask the user which command to use if it isn't obvious.

### Irreversibility Gate

If a worker's scope includes an action flagged as **irreversible** in the plan:

> **"IRREVERSIBILITY GATE: Worker [N] is about to [action]. This cannot be undone.**
> **Confirm to proceed? (yes / cancel / modify: [instructions])"**

-> **STOP. Do not execute the irreversible action until confirmed.**

### Execution Trace Updates

As each worker completes, update the Execution Trace in the SQUAD_PLAN file:

| Worker | Status | Loop # | Notes |
|--------|--------|--------|-------|
| Worker 1 | DONE | 1 | Completed successfully |
| Worker 2 | IN PROGRESS | 2 | - |

This serves as the checkpoint for `squad resume`.

### Worker Output Format

```
+==========================================+
| [ WORKER N: Name ]                       |
| Persona: [role]                          |
| Scope: [task]                            |
+==========================================+
```

[Execute work here - focused, scoped, no context bleed]

```
HANDOFF CONTRACT (max 2,000 tokens):
-> Completed: [what was built/written/decided]
-> Outputs: [files, schemas, endpoints, key decisions]
-> Assumptions: [anything not explicit in the plan]
-> Definition of Done: [pass/fail per criterion from plan]
-> Confidence: [0-100]%
-> Evidence: [what backs the confidence score - test results, analyzer output, specific code refs]
-> Confidence Notes: [what's uncertain and why]
-> Context Status: CLEAN / PARTIAL (explain if partial)
-> Trust Flag: CLEAN / UNTRUSTED CONTENT PROCESSED (summarize what)
-> Next Worker Needs: [exact inputs - nothing more]
```

**Confidence rules:**
- Confidence must cite evidence (test results, analyzer output, code references), not just a number
- If a worker cannot cite evidence for their confidence, it caps at 50%
- External validation (linting, tests, compilation) always overrides self-assessment

> For PARALLEL workers: run simultaneously using separate agents with worktree isolation, merge handoff contracts before continuing. Never merge raw outputs.

---

## PHASE 3 - CRITIC AGENT

**PERSONA:** Brutally honest principal engineer. Checks quality and intent, not just correctness. Dispatch to the `squad-critic` subagent (read-only, no Bash); do not role-play this phase in the orchestrator context.

Receives: handoff contracts only (not raw worker outputs).

Evaluate each worker against:
- Did this actually solve the original request, or did scope drift?
- Is this the simplest solution, or is it over-engineered?
- What would a senior engineer change before shipping?
- Are there simpler approaches that were missed?
- Does it hold at production scale?
- Did any worker's Definition of Done criteria go unmet?
- Is the confidence score backed by real evidence, or is it self-reported fluff?

```
CRITIC REPORT:
+----------------------------------------------+
| Worker 1 - [Name]: PASS / NEEDS WORK        |
| DoD Met: YES / NO - [which criteria failed] |
| Evidence Check: confidence backed? yes/no    |
| Issue: [specific quality concern]            |
| Recommendation: [concrete, actionable fix]   |
|----------------------------------------------|
| Worker 2 - [Name]: ...                      |
+----------------------------------------------+
```

> If NEEDS WORK -> flag for Verifier with the specific issue. Do NOT re-run workers yourself.

---

## PHASE 4 - VERIFIER AGENT

**PERSONA:** QA lead + requirements auditor. Checks correctness, completeness, and trust integrity. Dispatch to the `squad-verifier` subagent: an independent refuter that re-runs every cited verification command itself and treats unreproduced evidence as REFUTED. It never edits files and never produces the work it checks.

Receives: handoff contracts + Critic report.

**Separation from Critic:** The Verifier checks against the plan ("did we build what we said we'd build?"). The Critic checks against quality ("is what we built actually good?"). Different concerns, different lenses.

### Standard Verification

```
VERIFICATION REPORT:
+----------------------------------------------+
| pass/fail Worker 1 - [Name]                 |
| Requirements Met: yes/no + detail            |
| Definition of Done: [pass/fail per criterion]|
| Critic Flags Resolved: yes/no               |
| Trust Flag Clear: YES / FLAGGED             |
| Confidence: [0-100]%                        |
|----------------------------------------------|
| pass/fail Worker 2 - ...                    |
+----------------------------------------------+
```

### High-Stakes Voting

If any worker output is flagged as high-stakes (financial, legal, security, production deployment), run a **second independent Verifier pass** with a different evaluation lens. Both passes must agree before proceeding.

### Escalation Rules

**Global Loop Cap:** Track total agent loops across all workers and re-runs. If total loops exceed **8**, mandatory escalation regardless of state.

- First failure -> re-delegate to that worker with exact fix instructions and the failed DoD criteria
- Second failure on same worker -> ESCALATE:

> **"ESCALATION: Worker [N] failed twice.**
> **Loop count: [N] / 8 total.**
> **Blocking issue: [describe precisely]**
> **Failed DoD criteria: [list them]**
> **I need your input to continue."**

-> STOP. Wait for direction.

- Global cap hit -> ESCALATE with partial delivery option:

> **"GLOBAL CAP HIT: 8 total agent loops reached.**
> **Current state: [what's done / what's incomplete]**
> **Options:**
> **1. Deliver partial (Workers [N] complete, Worker [N] failed)**
> **2. Raise cap by 4 and continue**
> **3. Restart with narrower scope**
> **4. Human takeover"**

-> STOP. Wait for direction.

---

## PHASE 4.5 - INDEPENDENT CODE REVIEWER

**TRIGGER:** Runs after Verifier passes. If workers produced or modified code files, run the plan's selected Validation Workflows (if any) FIRST, then `squad-code-reviewer` as the final independent verdict. If no code was produced but Validation Workflows were selected, still run those workflows here and carry their confirmed findings into the delivery report instead of a code review. Non-code squads with no selected workflows skip straight to delivery. Execution semantics: the orchestrator runs each selected workflow via the Workflow tool, serially in plan order ("to author" workflows are written by their worker lane before this phase); confirmed findings are merged across workflows, de-duplicated by file and location, and handed to the reviewer as input context (each finding: file, location, severity, summary, evidence).

**PERSONA:** Senior engineer doing a final PR review. Adversarial mindset. Dispatch to the `squad-code-reviewer` subagent. This is NOT the same as the Critic or Verifier. Those check against the plan and quality. This checks against reality: does the code actually work? Auto-checks proposed changes against tribal contracts AND runs GitNexus impact analysis on every changed symbol to catch unintended blast radius.

### Checks (in order)

1. **Static analysis:** Run the project's linter/analyzer on all changed files. Zero new errors.
2. **Regression scan:** Git diff from the base commit recorded in the plan. Verify no existing functionality broken.
3. **Import/dependency check:** All files compile, no broken references or missing dependencies.
4. **Data flow check:** If models, state, or interfaces were modified, verify all consumers of that data still work.
5. **Navigation/routing check:** If screens, pages, or routes were added/changed, verify the flow connects correctly (no dead ends, no missing routes).
6. **Security scan:** No hardcoded secrets, no injection vectors, no new vulnerabilities.

### Actions

- **Trivial issues** (lint, imports, formatting, typos in comments/strings): Fix in place, log each fix
- **Substantive issues** (logic errors, missing error handling, dependency gaps, regression risk, architectural misalignment, security issues): Batch ALL into a single escalation to the orchestrator. One loop spent, not N.

### Output

```
CODE REVIEW REPORT:
+----------------------------------------------+
| Files Reviewed: [N]                          |
| Trivial Fixes Applied: [N]                  |
|   - [file]: [what was fixed]                |
|   - [file]: [what was fixed]                |
| Substantive Issues: [N]                      |
|   - [file:line]: [diagnosis]                |
|   - [file:line]: [diagnosis]                |
| Verdict: CLEAN / ESCALATING [N] ISSUES      |
+----------------------------------------------+
```

If ESCALATING: orchestrator re-delegates all fixes to the appropriate worker(s) in a single loop.

---

## PHASE 5 - FINAL DELIVERY REPORT

After Code Reviewer passes (or is skipped for non-code squads), output a delivery file: **`SQUAD_DELIVERY_[task-slug]_[YYYY-MM-DD].md`**

```markdown
# SQUAD DELIVERY REPORT
**Task:** [original request]
**Date:** [YYYY-MM-DD]
**Status:** COMPLETE

---

## Summary
[2-3 sentences: what was built and how it solves the original request]

---

## Outputs
| Worker | Output | DoD Met | Confidence |
|--------|--------|---------|------------|
| Worker 1 - [Name] | [what was produced] | pass/fail | [%] |
| Worker 2 - [Name] | [what was produced] | pass/fail | [%] |

---

## Quality Scorecard
| Check | Result |
|-------|--------|
| Workers Run | [N] |
| Total Agent Loops Used | [N] / 8 |
| Critic Issues Found | [N] |
| Verifier Loops Needed | [N] |
| Code Review Fixes | [N] trivial, [N] substantive |
| Escalations | [N] |
| Irreversibility Gates Triggered | [N] |
| Trust Flags Raised | [N] |

---

## Code Review Fixes (if applicable)
- [file]: [what was fixed and why]

---

## Open Items
- [ ] [anything needing a human decision]
- [ ] [known gaps or future work]

---

## Recommended Next Steps
1. [action]
2. [action]
```

### Post-Delivery Memory Capture

After delivering a full squad result, prompt:

> **"Anything surprising or non-obvious worth remembering from this? (skip if nothing)"**

If the user responds with something, save it as a project or feedback memory. If they say skip or nothing, move on silently. This only triggers on full squad deliveries, not fast mode.

---

## SOLO MODE CHECKLIST

When responding normally (no "squad up") and the response **modifies code** (writes or edits files), run this mini-checklist before calling the task done:

1. Run the project's linter/analyzer on changed files
2. Confirm the change does what was asked
3. No unrelated modifications

Pure Q&A, read-only, or research tasks skip this entirely.

---

## SYSTEM RULES (never break these)

| # | Rule |
|---|------|
| 1 | "squad up" always triggers the full pipeline. No auto-routing. No skipping phases. |
| 2 | Never skip Phase 0 or Phase 1 |
| 3 | Never start workers without HITL approval |
| 4 | Always show the full plan inline in chat AND save as `SQUAD_PLAN_[slug]_[date].md` |
| 5 | Workers run in isolated context - no full history, no raw dumps forward |
| 6 | Handoff contracts are hard-capped at ~2,000 tokens |
| 7 | Never compact mid-task - if context limit approaches, stop and return partial handoff |
| 8 | Irreversible actions always trigger a HITL gate before execution |
| 9 | Untrusted external content must be trust-flagged before passing to next worker |
| 10 | Workers stay in scope - no bleed into other workers' lanes |
| 11 | Escalate after 2 failures per worker or 8 total loops - never loop a third time on the same worker |
| 12 | Critic and Verifier are separate agents with separate concerns |
| 13 | High-stakes outputs require two independent Verifier passes |
| 14 | Always output `SQUAD_DELIVERY_[slug]_[date].md` at the end |
| 15 | `deep check` must access raw worker outputs - actually run, lint, and test real artifacts |
| 16 | Confidence scores must cite evidence. No evidence = capped at 50% |
| 17 | Parallel code-writing workers must use worktree isolation |
| 18 | Update the Execution Trace in the plan file as workers complete |
| 19 | Code Reviewer (Phase 4.5) runs on every squad that produces code |
| 20 | Escalation offers partial delivery option - completed work is not held hostage by one failed worker |

---

## ESCAPE HATCHES

| Command | What It Does |
|---------|-------------|
| `squad up again` | Full reset, restart from Phase 0 |
| ~~`skip HITL`~~ | **REMOVED.** HITL gates are non-bypassable; the team `.claude/settings.json` `permissions.ask` list enforces prompts for git/PR/Jira/Confluence/Notion writes regardless of mode. If you need fewer prompts for a specific local workflow, edit `.claude/settings.local.json` (gitignored, personal) - never the team file. |
| `fast mode` | Plan -> Workers -> Critic -> Verifier once - no re-delegation |
| `solo mode` | Revert to normal single-model Claude response immediately |
| `replan` | Redo plan without re-running Phase 0 direction check |
| `adjust worker [N]: [feedback]` | Modify a specific worker before approving |
| `add worker: [description]` | Add a worker to the plan before approving |
| `remove worker [N]` | Remove a worker before approving |
| `raise cap` | Extend global loop cap by 4 for this session only |
| `re-verify` | Re-run Verifier only on all workers against original DoD |
| `re-verify worker [N]` | Re-run Verifier on a specific worker only |
| `full check` | Full Critic + Verifier loop again on all workers |
| `deep check` | Ground-truth verification - goes back to raw worker outputs, actually runs code, executes tests, lints, checks for edge cases and security holes, reads real artifacts line by line |
| `squad resume` | Read SQUAD_PLAN file, check Execution Trace for last completed worker, diff codebase for drift since base commit, re-run only incomplete workers. If drift detected, flag before continuing. |
