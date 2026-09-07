# Flow: New project

Fresh or near-empty repo. There's little or no source to index yet, so the goal is to wire the stack now so it grows with the code. Skip tribal generation until real modules exist.

Follow the numbered steps. Stop and report on any failure.

## 1. Ensure a git repo

The stack keys off git. If `git rev-parse --is-inside-work-tree` fails, ask the user to confirm, then `git init`. Make an initial commit only if the user asks.

## 2. Confirm the brain skills are present

`.claude/skills/squad-up/` and `.claude/skills/deep-codebase-explorer/` came with the boilerplate copy. Confirm both `SKILL.md` files exist. If not, the `.claude/` copy is incomplete — stop and tell the user to re-copy it.

## 3. Write starter CLAUDE.md + AGENTS.md

If a root `CLAUDE.md` already exists, do NOT overwrite it — show what you'd add and merge. Otherwise create it:

```markdown
# CLAUDE.md

Conventions and quick-start for working in this repo with Claude Code.

## The stack

1. **deep-codebase-explorer** — auto-routes any code question through skills + the
   GitNexus graph + sub-agents. Just ask naturally; force a mode with a prefix
   (`ULTIMATE:`, `AG:`, `vanilla:`).
2. **GitNexus** — call-graph of the codebase. CLI: `npx -y gitnexus@latest <command>`.
3. **squad-up** — multi-phase agent pipeline. Trigger with `squad up [task]`.
4. **tribal skills** — per-module knowledge under `.claude/skills/tribal/`. Add one
   whenever you learn a non-obvious gotcha.

## Essential commands

<!-- Fill these in as the project grows. The squad workers read this section to
     know how to lint/test/build; do not leave it blank once commands exist. -->

```bash
# lint    → e.g. npm run lint
# test    → e.g. npm test
# build   → e.g. npm run build
```

## Conventions

- (Add repo conventions here as the team settles them.)
```

Create `AGENTS.md` as a thin mirror if the user wants Codex/other-agent parity:

```markdown
# AGENTS.md

Mirrors CLAUDE.md for other agent runtimes. The four-layer stack lives under
`.claude/skills/`; the skill files are plain markdown and runtime-agnostic.
See CLAUDE.md for the full guide.
```

## 4. Wire GitNexus

Even a small repo benefits from having the graph + MCP wired now, so it's live as code lands.

```bash
npx -y gitnexus@latest analyze --skills   # index + generate cluster skills (fresh repo)
npx -y gitnexus@latest setup              # wire the MCP server into Claude Code (idempotent)
npx -y gitnexus@latest status             # verify
```

If the repo is truly empty, `analyze` may find nothing — that's fine; re-run it (or `squad refresh`) once there's code. Note this in the summary.

## 5. Skip tribal (for now)

There are no established modules to document yet. Leave `.claude/skills/tribal/` as scaffold. Tell the user: once real modules exist, run the **existing-project** flow's tribal step (or just re-invoke `squad setup`) to generate them.

## 6. Generate the stack profile

Do **Step 3 of `SKILL.md`** (generate `.claude/stack-profile.md`). With little code yet, base it on the intended stack — ask the user if it isn't obvious — and mark command specifics `TODO:` until the tooling is in place. This is what makes the squad agents speak the project's stack from day one.

## 7. Hand back to Step 4 of SKILL.md

Return to the shared **Verify** step in `SKILL.md` and report results.
