# Week 9 Practical — Task Set D

## Bolt on the claims-system server without touching the agent

**Agent under test:** `tools/w9d_agent.py`'s `run_agent` — a new, Week 9-shaped agent
(not a reuse of Week 7's hand-dispatched `w7d_agent.py`): it discovers tools from an MCP
config instead of importing a fixed tool module, over a hand-built stdio JSON-RPC client
(`tools/w9d_mcp.py` — no third-party `mcp` package; see that module's own docstring for
why this exercise is easier to prove honestly without one). Two servers back it:
`tools/w9d_policy_server.py` (server one, ours — policy-document search) and
`tools/w9d_claims_server.py` (server two — the claims-system server, framed as the
platform team's, not ours; see §6).

Reproduce everything below with:

```
python weeks.py w9d-eval --stage discover   # tool counts before -> after, by name
python weeks.py w9d-eval --stage query      # the one query that proves a claims-system tool ran
python weeks.py w9d-eval --stage wire       # raw initialize/tools-list/tools-call, annotated
python weeks.py w9d-eval --stage errors     # docstring-as-prompt + recoverable error, before/after
```

`agent_diff.txt` and the config diff are one-off `git diff --no-index` calls against
fixtures already on disk — see §2.

---

## 1. Config-only server swap: 1 tool -> 3 tools

`eval/w9d/tool_counts.md`, taken from `tools/list` against each config, not from notes:

| | tools | names |
|---|---:|---|
| before (`w9d_mcp_config.step1.json`) | **1** | `search_policy` |
| after (`w9d_mcp_config.json`) | **3** | `search_policy`, `get_claim_status`, `get_adjuster_notes` |

The two new tools came from adding one block to the config:

```diff
     "policy-docs": {
       "command": "python",
       "args": ["tools/w9d_policy_server.py"]
+    },
+    "claims-system": {
+      "command": "python",
+      "args": ["tools/w9d_claims_server.py"]
     }
```
(full output: `eval/w9d/config_diff.txt`)

---

## 2. Zero lines changed in the agent module

`eval/w9d/w9d_agent.step1_snapshot.py` is a copy of `tools/w9d_agent.py` taken while the
config named only `policy-docs`. It has not been touched since; `tools/w9d_agent.py`
has not been touched since either — the file that changed between "before" and "after"
above is `tools/data/w9d_mcp_config.json`, nothing else.

```
$ git diff --no-index eval/w9d/w9d_agent.step1_snapshot.py tools/w9d_agent.py
(no output — 0 lines changed)
```

Full command output, including the confirming `diff -q`: `eval/w9d/agent_diff.txt`.

This is possible because `tools/w9d_agent.py` names no tool and no server anywhere in
it — not in `SYSTEM_PROMPT`, not in a schema, not in a dispatch table. It reads
`tools/data/w9d_mcp_config.json`, spawns whatever servers are listed, calls `tools/list`
on each, and hands the model whatever came back (`MCPToolRouter.__init__` in
`tools/w9d_agent.py`). Discovery was the only thing standing between one server and two.

---

## 3. The proof query

```
"What is the status of claim CLM-7004, and can you summarize what the adjuster notes
say about the cause of loss?"
```

Trace (`eval/w9d/proof_query.json`):

```
[lap 1] tool get_claim_status({'claim_number': 'CLM-7004'}) -> {'status': 'open - under review', ...}
[lap 2] tool get_adjuster_notes({'claim_number': 'CLM-7004'}) -> {'notes': 'Heavy rain overnight...'}
[lap 3] final answer: cites both results, no fabricated status or notes
```

Both tool names in that trace — `get_claim_status`, `get_adjuster_notes` — exist nowhere
except on the newly-added `claims-system` server. Requirement 1's "provably calls a tool
from it" is that trace line, not a claim about it.

---

## 4. The raw wire, annotated

`eval/w9d/wire.json` captures the literal JSON-RPC 2.0 lines exchanged with
`claims-system` for `initialize -> notifications/initialized -> tools/list -> tools/call
get_claim_status`, each with a field-by-field annotation (what `id` correlates, why
`notifications/initialized` carries no `id` and gets no reply, what `isError` means vs. a
top-level JSON-RPC `error`, and so on).

**Where the model is called, in one line** (also the file's own `model_call_location`
field): inside `tools/w9d_agent.py`'s `run_agent`, in the `call_llm(...)` call — once per
lap, in the agent process, after a `tools/list` response has been folded into the
function-calling menu and before the next `tools/call` is sent. **Where it is not
called:** anywhere in `tools/w9d_claims_server.py` or `tools/w9d_policy_server.py` — both
processes run deterministic Python and return data; nothing under `tools/w9d_*server.py`
imports an LLM client. That is the exact split the Task Set D "common mistakes" list
warns against blurring: an MCP server exposes a capability, the host runs the model.

---

## 5. Docstring rewrite + recoverable error, on OUR OWN server

Rewrote `search_policy`'s description (`tools/w9d_policy_server.py`,
`SEARCH_POLICY_DESCRIPTION`) from a flat capability statement into a prompt — when to
call it, what to do with a form redirect, the actual list of valid form numbers — and
changed its unrecognized-`form_number` error from `"unknown form_number: 'X'"` to one
that states the valid list and the recovery move (`form_number=null`).

Same failing call (`search_policy(query=..., form_number="HO-1234")`, a form with no
close valid neighbor, for a user question that never names a form number either), 4
trials each side, ordinary sampling — a single transcript would not be honest evidence of
a model's next move either way (`eval/w9d/error_before_after.md`):

| | tally (4 trials) |
|---|---|
| **before** (old description + old error) | 2 hallucinated a different real form number, 2 fell back to `form_number=null` |
| **after** (new description + new error) | 4 fell back to `form_number=null` |

The old error state ("unknown form_number: 'HO-1234'") gives the model nothing to
correct toward, so half the time it guessed again, blind, into a real-but-wrong form —
the "swallowed into a dead end" failure the common-mistakes list names, one lap away from
returning someone else's deductible with total confidence. The new error states the
actual valid list in the same sentence, and every trial fell back to the one move
guaranteed correct when the form is genuinely unknown: search everything. The rewrite
changed what the retry was grounded in, not just its wording.

---

## 6. Supply-chain risk: the claims-system server

`eval/w9d/risk_note.md` (5 lines): written by the platform team, not us, and unaudited by
us; reaches every open claim's status and full, unsanitized adjuster-note history by
claim number alone; logs what it logs on infrastructure we can't see once it's networked,
which our own `wire.json` capture (our side of the pipe only) cannot tell us; a stolen
token in a networked deployment reads every note on every claim, unscoped; **verdict:
don't ship as configured** — only behind a gateway that scopes the token to
`get_claim_status` and audit-logs every call (the bonus challenge, not implemented here).

---

## 7. Bonus challenge

Not attempted. A single gateway process fanning both servers out behind one front door,
with a per-call audit line and a token scoped to deny `get_adjuster_notes` while keeping
`get_claim_status`, is a real next step (§6's risk note names exactly this as the ship
condition) — left out here rather than claimed and under-built.

---

## 8. Submission checklist

- [x] `eval/w9d/agent_diff.txt` — 0 changed lines in `tools/w9d_agent.py` — §2
- [x] `eval/w9d/config_diff.txt` — the config-only diff adding `claims-system` — §1
- [x] `eval/w9d/wire.json` — raw initialize/tools-list/tools-call, annotated, model-call location stated — §4
- [x] Tool count line: 1 -> 3, with names, from `tools/list` — §1, `eval/w9d/tool_counts.md`
- [x] `eval/w9d/error_before_after.md` — same failing call, old vs new docstring/error, tallied over 4 trials each — §5
- [x] `eval/w9d/risk_note.md` — exactly 5 lines — §6
- [ ] Bonus: gateway, audit log, scoped-token denial — not attempted, §7
