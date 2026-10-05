"""Trace-aware MCP plumbing for the capstone: one trace id across the hop.

tools/w9d_mcp.py is the protocol (JSON-RPC over stdio) and is reused as is.
What the capstone needs on top of it is that a request which crosses the
agent -> MCP-server boundary is still *one request* in the logs:

  * the client sends the agent's trace id in `params._meta.trace_id` - the
    spec's own extension point for out-of-band metadata, so it is not a
    private argument smuggled through the tool's input schema (which would
    show up in the model-visible tool description);
  * the server times its handler, writes a span row tagged with that id to
    traces/w12_mcp_spans.jsonl, and returns the same span in
    `result._meta.server_span`, so the agent can fold the server-side time
    into its own request log without a join across files;
  * the server's stdout is the protocol, so anything the handler (or the
    RagEngine it embeds) prints is diverted to stderr. One stray `print`
    otherwise corrupts the JSON-RPC stream and surfaces as a baffling
    parse error in the *client*.

The server span log never contains tool arguments or results - only the
trace id, tool name, argument *names*, latency and sizes - so it cannot be
a second place PII leaks to.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

from w9d_mcp import PROTOCOL_VERSION, REPO_ROOT, MCPClient, MCPServer

SPAN_LOG = REPO_ROOT / "traces" / "w12_mcp_spans.jsonl"
STDERR_LOG_DIR = REPO_ROOT / "traces"


class TracedMCPServer(MCPServer):

    def __init__(self, name, version="1.0.0", wire_guard=None):
        super().__init__(name, version)
        self.wire_guard = wire_guard

    def _handle(self, msg):

        if msg.get("method") != "tools/call":
            return super()._handle(msg)

        params = msg.get("params") or {}
        trace_id = (params.get("_meta") or {}).get("trace_id")
        tool = self.tools.get(params.get("name"))
        started = time.perf_counter()

        reply = super()._handle(msg)

        if tool is None or reply is None or "result" not in reply:
            return reply

        result = reply["result"]

        # Defence in depth on the way out: the handler is trusted to return
        # a redacted view, and the guard re-checks that it did, because the
        # question the brief asks is what the server *handed over*, not what
        # it meant to.
        if self.wire_guard is not None:

            text = result["content"][0]["text"]
            violations = self.wire_guard(text)

            if violations:
                result["content"][0]["text"] = json.dumps({
                    "error": "response withheld: it contained personal data "
                             f"({len(violations)} item(s)) that this server must "
                             "not return."
                })
                result["isError"] = True

        span = {
            "trace_id": trace_id,
            "server": self.name,
            "tool": tool.name,
            "arg_names": sorted((params.get("arguments") or {}).keys()),
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "result_chars": len(result["content"][0]["text"]),
            "is_error": bool(result.get("isError")),
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
        }

        SPAN_LOG.parent.mkdir(parents=True, exist_ok=True)

        with SPAN_LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(span) + "\n")

        result["_meta"] = {"server_span": span}

        return reply

    def serve_forever(self):

        wire = sys.stdout
        sys.stdout = sys.stderr

        for line in sys.stdin:
            line = line.strip()

            if not line:
                continue

            reply = self._handle(json.loads(line))

            if reply is not None:
                wire.write(json.dumps(reply) + "\n")
                wire.flush()


class TracedMCPClient(MCPClient):
    """MCPClient that carries a trace id and keeps the server's stderr."""

    def __init__(self, server_label, command, args, log=None):

        self.server_label = server_label
        resolved = sys.executable if command in ("python", "python3") else command

        # stderr to a file, not a pipe nobody reads: a server that logs more
        # than the OS pipe buffer (the embedded RagEngine's progress bars do)
        # blocks on its own stderr write and the client hangs forever.
        STDERR_LOG_DIR.mkdir(parents=True, exist_ok=True)
        self._stderr = open(STDERR_LOG_DIR / f"w12_{server_label}.stderr.log", "a",
                            encoding="utf-8")

        self._proc = subprocess.Popen(
            [resolved, *args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._stderr,
            text=True,
            bufsize=1,
            cwd=REPO_ROOT,
        )
        self._next_id = 1
        self._log = log

    def call_tool_traced(self, name, arguments, trace_id):
        """Returns (result_dict, server_span_or_None)."""

        response = self._request("tools/call", {
            "name": name,
            "arguments": arguments,
            "_meta": {"trace_id": trace_id},
        })

        if "error" in response:
            return {"error": response["error"]["message"]}, None

        result = response["result"]
        text = result["content"][0]["text"]

        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = {"text": text}

        return payload, (result.get("_meta") or {}).get("server_span")

    def close(self):
        super().close()
        try:
            self._stderr.close()
        except OSError:
            pass
