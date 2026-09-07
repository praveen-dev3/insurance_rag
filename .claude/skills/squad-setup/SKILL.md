---
name: squad-setup
description: Plug-and-play installer for the Squad Up + GitNexus + deep-codebase-explorer stack in any repository. Use when the user wants to set up, install, wire up, or integrate the stack — either a brand-new project or an existing codebase. Triggers on "squad setup", "set up the stack", "install squad up", "integrate gitnexus", "wire up the claude stack", "onboard this repo".
---

# Squad Setup — plug-and-play stack installer

Installs the four-layer Claude stack into whatever repo this `.claude/` folder was dropped into:

1. **squad-up** — multi-phase agent pipeline for non-trivial work (`.claude/skills/squad-up/`).
2. **deep-codebase-explorer** — smart auto-router over skills + graph + sub-agents (`.claude/skills/deep-codebase-explorer/`).
3. **GitNexus** — pre-computed call-graph of the codebase, wired as an MCP server + CLI.
4. **tribal skills** — hand-written per-module knowledge (`.claude/skills/tribal/`), generated for existing code.

The skills and squad agents ship inside this `.claude/` folder — copying the folder in is the "plug". This skill is the "play": it indexes the graph, wires the MCP server, writes starter docs, and (for existing code) generates tribal knowledge.

> **Pin note:** commands below use `gitnexus@latest`. For reproducible installs across a team, pick one version and use `gitnexus@X.Y.Z` everywhere instead.

---

## Step 0 — Pick the flow

Decide which of the two flows applies, then follow that file:

| Signal | Flow | File |
|---|---|---|
| Repo is empty / near-empty, or being scaffolded from scratch (no real source yet) | **New project** | `.claude/skills/squad-setup/new-project.md` |
| Repo already has a real codebase you want the stack to understand | **Existing project** | `.claude/skills/squad-setup/existing-project.md` |

**How to decide without asking:** count source files (exclude `.claude/`, `node_modules/`, `.git/`, build dirs). Roughly < 5 real source files → new; otherwise → existing. If it's genuinely ambiguous, ask the user once: *"New project (fresh scaffold) or existing codebase (has real source to index)?"* — then read the matching flow file and follow it exactly.

Do NOT run both flows. Read one file, then execute its steps.

---

## Step 1 — Preflight (both flows)

Check before doing anything; report any miss and stop if a hard requirement is absent.

- **`git`** — the repo should be a git repo. If not and the user wants it, offer `git init` (ask first — it's a state change).
- **`npx` / Node.js** — required for GitNexus. `npx --version`. If missing, tell the user to install Node.js (https://nodejs.org) and stop.
- **`uvx` (optional)** — only needed if the repo wires a language-server MCP (e.g. Serena). Non-fatal if absent; note it and continue.
- **`.claude/skills/squad-up/` and `.claude/skills/deep-codebase-explorer/` present** — if either is missing, the boilerplate copy is incomplete; tell the user to re-copy the `.claude/` folder.

---

## Step 2 — Run the matching flow

Open the flow file from Step 0 and follow its steps. Both flows converge on the same GitNexus wiring + stack profile; they differ in how they treat existing source (index + document it) vs. a fresh repo (write starter docs, skip tribal until there's code).

---

## Step 3 — Generate the stack profile (both flows)

This is what makes the squad **adapt to the project's tech stack**. Rather than rewriting each agent per project, setup writes ONE file — `.claude/stack-profile.md` — that every squad agent (planner, implementer, verifier, code-reviewer) reads at the start of a lane. A Python project gets pytest/ruff/mypy commands and a Python review lens; a Go project gets `go test`/`go vet` and a goroutine-leak lens; and so on.

Follow **`.claude/skills/squad-setup/stack-profile.md`**: detect the language(s), frameworks, and package manager; resolve the real lint/format/typecheck/test/build commands from the repo's own config; pick the matching review lens from the cheatsheet; and write the filled `.claude/stack-profile.md`. Multi-stack repos get one block per stack, tagged by directory. Leave `TODO:` markers for anything undetermined instead of guessing.

For a **new project** with no real code yet, write the profile from the intended stack (ask the user if unknown) and mark command specifics `TODO:` until the tooling lands.

---

## Step 4 — Verify (both flows)

The install is done only when all of these hold. Run them and report pass/fail:

- `npx -y gitnexus@latest status` returns cleanly (index exists, MCP wired).
- `.claude/skills/squad-up/SKILL.md` and `.claude/skills/deep-codebase-explorer/SKILL.md` exist.
- `.claude/stack-profile.md` exists with the Commands table filled (no leftover `TODO:` on lint/test/build for a project that has real code).
- A root `CLAUDE.md` exists with an **Essential commands** section filled in (or flagged TODO if the repo's commands aren't yet known).
- Asking a normal code question routes through the explorer; typing `squad up [task]` starts the pipeline.

Finish with a short summary: what was installed, what's still a TODO (usually: fill Essential commands, generate tribal for more modules), and the next command to try (`squad up [some real task]`).

---

## HITL boundary

Setup is autonomous within the working tree. Anything beyond it prompts first: `git init`, `git add`/`commit`, MCP wiring that edits global config, or overwriting a file the user already has. Never overwrite an existing `CLAUDE.md`, `AGENTS.md`, or `settings.json` without showing the diff and getting a yes — merge into them instead.
