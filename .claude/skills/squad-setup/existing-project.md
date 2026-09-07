# Flow: Existing project

The repo already has a real codebase. Goal: index it, wire the MCP server, capture the repo's commands, and generate tribal knowledge for its modules so the stack actually understands the code.

Follow the numbered steps. Stop and report on any failure. Never clobber files the repo already has — merge, don't overwrite.

## 1. Confirm the brain skills are present

`.claude/skills/squad-up/` and `.claude/skills/deep-codebase-explorer/` came with the boilerplate copy. Confirm both `SKILL.md` files exist; if not, the copy is incomplete — stop.

## 2. Capture the repo's real commands into CLAUDE.md

The squad workers and verifier read the root `CLAUDE.md` **Essential commands** section to know how to lint/test/build. Get this right — guessing here poisons every downstream lane.

- If a root `CLAUDE.md` exists: read it. If it already lists lint/test/build, keep them. Add a short "The stack" section (see new-project.md step 3) if absent. Do NOT overwrite existing content — merge.
- If none exists: create one (template in new-project.md step 3), then fill **Essential commands** by inspecting the repo:
  - `package.json` `scripts` (npm/pnpm/yarn), `Makefile` targets, `pyproject.toml` / `tox.ini`, `Cargo.toml`, `go.mod`, `build.gradle`, etc.
  - Detect the package manager from the lockfile (`pnpm-lock.yaml`, `yarn.lock`, `package-lock.json`, `poetry.lock`, `uv.lock`).
  - For a monorepo, note the per-package/per-service command and the directory to run it from.
- If a command isn't discoverable, write it as a TODO and tell the user rather than inventing one.

## 3. Wire GitNexus (index + MCP)

Order matters — index first, then wire, then verify.

```bash
# If the repo has NO committed gitnexus skills and NO local .nexus/ index → full generate:
npx -y gitnexus@latest analyze --skills

# If gitnexus cluster skills are already committed (e.g. via a prior PR) but there's no
# local index yet → build the index only, so you don't overwrite committed skills:
npx -y gitnexus@latest analyze

# Then wire + verify (idempotent):
npx -y gitnexus@latest setup
npx -y gitnexus@latest status
```

Detect the state first: `.nexus/` present → index already built, skip `analyze`. `.claude/skills/gitnexus/` present → skills committed, use plain `analyze` (no `--skills`).

Indexing a large repo takes ~1 minute. If `analyze` fails, the brain skills still work in skills-only mode — report the failure and continue.

## 4. Generate tribal knowledge for the modules

This is what makes the stack understand *this* codebase's gotchas. One tribal `SKILL.md` per module.

**Detect module candidates** (first match wins): top-level dirs under `apps/`, else `packages/`, else `src/`, else the repo's own top-level source dirs (excluding `.claude`, `node_modules`, `dist`, `build`, `coverage`, `vendor`, `.git`).

Show the candidate list to the user and ask which to generate for (`all` / a subset / `skip`) and a depth (`minimal` / `standard` / `deep`). Then, for each selected module, dispatch a sub-agent (Task tool, `subagent_type: Explore`, run in parallel, max ~8 concurrent) with this prompt:

> You are generating a tribal-knowledge skill for the module at `<MODULE_PATH>`.
>
> **Discipline:** read the module's files (line-by-line at `deep` depth); cite real `file:line`; never invent paths or symbols; if something is unclear, say so instead of inventing.
>
> Write `.claude/skills/tribal/<MODULE_NAME>/SKILL.md` with exactly:
>
> ```markdown
> ---
> name: <MODULE_NAME>
> description: Tribal knowledge for <MODULE_NAME>. Use when working on <one-line summary>.
> ---
>
> # <MODULE_NAME>
>
> ## Business Purpose
> One paragraph: what real-world problem this solves.
>
> ## Why It Exists
> Architectural/historical context NOT derivable from the code.
>
> ## Gotchas
> Specific traps a fresh engineer would hit, each citing `file.ext:line`
> (fail-open behavior, silent fallbacks, ordering constraints, race conditions,
> kill switches, fire-and-forget, security invariants).
>
> ## Flow
> The canonical happy-path execution, each step linked to `file:line`.
> ```
>
> **Depth:** `minimal` = 3-5 key gotchas only; `standard` = thorough gotchas + a flow walkthrough; `deep` = line-by-line read of every file >50 lines, every non-obvious constant/guard/magic-string.
>
> **Avoid:** restating what the code obviously does, hallucinated references, generic platitudes, dumping raw code.

After the sub-agents finish, list each `SKILL.md` created with a one-line summary. Don't paste full contents back.

## 5. Generate the stack profile

Do **Step 3 of `SKILL.md`** (generate `.claude/stack-profile.md`). Detect the language(s), frameworks, and package manager; resolve the real lint/format/typecheck/test/build commands from the repo's own config (not guesses); and pick the matching review lens from the cheatsheet in `.claude/skills/squad-setup/stack-profile.md`. This is what makes the implementer, verifier, and code-reviewer behave according to *this* stack — pytest/ruff for Python, `go test`/`go vet` for Go, etc. Multi-stack repo → one block per stack, tagged by directory.

The command values here should agree with the `CLAUDE.md` "Essential commands" you filled in step 2; the stack profile adds the test conventions and the stack-specific review lens on top.

## 6. Confirm settings / HITL (optional)

If the repo has no `.claude/settings.json`, the boilerplate's generic one (git/PR/ticketing writes on the `ask` list) already applies. If the repo has its own, leave it — don't merge HITL rules unasked; just note that the squad relies on those `ask` rules to keep git/PR/ticket mutations behind a prompt.

## 7. Hand back to Step 4 of SKILL.md

Return to the shared **Verify** step in `SKILL.md` and report results, including which tribal modules were generated and which were skipped.
