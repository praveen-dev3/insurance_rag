"""The MCP-client agent: discovers every tool from every server named in an
MCP config, then runs an LLM tool-calling loop over whatever it discovered.

This module names no tool and no server anywhere in it - not in the system
prompt, not in a schema, not in a dispatch table. It only reads a config
(tools/data/w9d_mcp_config.json by default), spawns each listed server,
calls tools/list on each, and hands the model whatever came back. Adding,
removing, or swapping a server is a change to that config file alone; see
eval/w9d/agent_diff.txt (this file, diffed against
eval/w9d/w9d_agent.step1_snapshot.py - a copy taken while the config named
only the policy-docs server) and eval/w9d/config_diff.txt (the config, over
the same span) for the proof.

Deliberately reuses w7d_common.py's call_llm/Budget/cost_usd rather than
rag.llm - see that module's own docstring for why an MCP exercise has no
reason to import chromadb and sentence-transformers to make a chat
completion call.
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from w7d_common import DEFAULT_BUDGET, MODEL, REASONING_EFFORT, call_llm, cost_usd
from w9d_mcp import MCPClient

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "data" / "w9d_mcp_config.json"

SYSTEM_PROMPT = """You are a claims triage assistant. You have no built-in knowledge of any
claim, of the claims system, or of policy wording - everything you know about them has to
come from calling the tools available to you this session, whatever those turn out to be.
Read each tool's own description before calling it; do not assume a tool exists, what it is
named, or what it returns, beyond what the tool list actually gave you.

Use the tools you have to answer the user's question fully and precisely, citing what each
tool actually returned rather than what you'd expect it to say. If a tool call fails, read
the error message it gives you - it is written to say what went wrong and how to correct
the next call - and try again correctly instead of giving up or repeating the identical
failing call.

Once you have enough information to answer, stop calling tools and answer in plain prose."""


def load_config(path=None):
    return json.loads(Path(path or DEFAULT_CONFIG_PATH).read_text(encoding="utf-8"))


class MCPToolRouter:
    """Every live server's tools/list, aggregated into one function-calling
    menu, with enough of a name->server map to dispatch a call back to
    whichever server actually offered it.

    One instance per run: tools/list only has to happen once per server, at
    the top of the run, not once per lap of the loop below.
    """

    def __init__(self, config, log=None):
        self.clients = {}
        self._owner = {}
        self.openai_tools = []

        for server_label, spec in config.get("mcpServers", {}).items():
            client = MCPClient(server_label, spec["command"], spec.get("args", []), log=log)
            client.initialize()
            self.clients[server_label] = client

            for tool in client.list_tools():
                self._owner[tool["name"]] = server_label
                self.openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool["description"],
                        "parameters": tool["inputSchema"],
                    },
                })

    def dispatch(self, name, arguments):
        server_label = self._owner.get(name)

        if server_label is None:
            return {"error": f"no such tool: {name!r}"}

        return self.clients[server_label].call_tool(name, arguments)

    def tool_report(self):
        """{server_label: [tool names]} - requirement 3's before/after, by name."""

        report = {}
        for name, server_label in self._owner.items():
            report.setdefault(server_label, []).append(name)
        return report

    def close(self):
        for client in self.clients.values():
            client.close()


@dataclass
class AgentRun:
    outcome: str  # "completed" | "budget_exceeded" | "error"
    budget_reason: str | None = None
    final_text: str | None = None
    iterations: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    wall_clock_s: float = 0.0
    tool_calls: list = field(default_factory=list)
    transcript: list = field(default_factory=list)

    @property
    def total_tokens(self):
        return self.prompt_tokens + self.completion_tokens

    @property
    def cost_usd(self):
        return cost_usd(self.prompt_tokens, self.completion_tokens)


def run_agent(user_message, config=None, config_path=None, budget=None, log=None):

    budget = budget or DEFAULT_BUDGET
    config = config or load_config(config_path)
    router = MCPToolRouter(config, log=log)

    try:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        result = AgentRun(outcome="error")
        start = time.perf_counter()
        iteration = 0

        while True:

            iteration += 1
            result.iterations = iteration
            result.wall_clock_s = time.perf_counter() - start

            if iteration > budget.max_iterations:
                result.outcome, result.budget_reason = "budget_exceeded", "max_iterations"
                break
            if result.wall_clock_s > budget.max_wall_clock_s:
                result.outcome, result.budget_reason = "budget_exceeded", "wall_clock"
                break
            if result.total_tokens > budget.max_tokens:
                result.outcome, result.budget_reason = "budget_exceeded", "max_tokens"
                break
            if result.cost_usd > budget.max_cost_usd:
                result.outcome, result.budget_reason = "budget_exceeded", "max_cost"
                break

            # This is the one place in the whole run where the model gets
            # called - see eval/w9d/wire.json's model_call_location. Nothing
            # in tools/w9d_mcp.py, tools/w9d_policy_server.py or
            # tools/w9d_claims_server.py ever imports an LLM client.
            response = call_llm(
                model=MODEL,
                messages=messages,
                tools=router.openai_tools,
                tool_choice="auto",
                reasoning_effort=REASONING_EFFORT,
            )

            usage = response.usage
            result.prompt_tokens += usage.prompt_tokens
            result.completion_tokens += usage.completion_tokens

            message = response.choices[0].message
            messages.append(message.model_dump(exclude_none=True))

            if not message.tool_calls:
                result.outcome = "completed"
                result.final_text = message.content
                result.transcript.append(f"[lap {iteration}] final answer: {message.content!r}")
                break

            for call in message.tool_calls:
                args = json.loads(call.function.arguments or "{}")
                tool_result = router.dispatch(call.function.name, args)

                result.tool_calls.append({
                    "name": call.function.name,
                    "server": router._owner.get(call.function.name),
                    "arguments": args,
                    "result": tool_result,
                })
                result.transcript.append(
                    f"[lap {iteration}] tool {call.function.name}({args}) -> {tool_result}"
                )

                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(tool_result),
                })

        return result

    finally:
        router.close()
