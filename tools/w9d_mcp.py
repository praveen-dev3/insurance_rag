"""A minimal, spec-shaped MCP implementation: JSON-RPC 2.0, one message per
line, over a subprocess's stdin/stdout. No third-party `mcp` package.

Week 9 Task Set D asks for the raw initialize -> tools/list -> tools/call
exchange annotated by hand (see eval/w9d/wire.json) - that is much harder to
show honestly through an SDK's abstractions than through a client this small,
where every line this process writes or reads is exactly what appears in the
capture. What is implemented mirrors the real protocol closely enough that
swapping this module for the official SDK later would not change any other
file in tools/w9d_*.py: `initialize`, `notifications/initialized`,
`tools/list`, `tools/call`, `resources/list`, `resources/read`, and nothing
else - this repo's servers use nothing else.
"""

import json
import subprocess
import sys
from pathlib import Path

PROTOCOL_VERSION = "2024-11-05"

# Config args are repo-relative ("tools/w9d_policy_server.py") so the config
# file reads the same regardless of which directory an agent happens to be
# launched from - the client pins the child's cwd here rather than asking
# every config author to know or care where the parent process's cwd is.
REPO_ROOT = Path(__file__).resolve().parent.parent


class Tool:
    """One MCP tool: a name, a description the model reads as its only
    documentation, a JSON Schema for its arguments, and the Python callable
    that runs when the model invokes it."""

    def __init__(self, name, description, input_schema, handler):
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.handler = handler

    def to_mcp(self):
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


class Resource:
    """App-attached context, never model-invoked - see the "common mistakes"
    warning against exposing context like an exclusions schedule as a tool."""

    def __init__(self, uri, name, description, mime_type, reader):
        self.uri = uri
        self.name = name
        self.description = description
        self.mime_type = mime_type
        self.reader = reader

    def to_mcp(self):
        return {
            "uri": self.uri,
            "name": self.name,
            "description": self.description,
            "mimeType": self.mime_type,
        }


class MCPServer:
    """Speaks MCP over stdin/stdout: reads one JSON-RPC message per line,
    dispatches it, writes one JSON-RPC reply per line (notifications get no
    reply, matching the spec)."""

    def __init__(self, name, version="1.0.0"):
        self.name = name
        self.version = version
        self.tools = {}
        self.resources = {}

    def add_tool(self, tool):
        self.tools[tool.name] = tool

    def add_resource(self, resource):
        self.resources[resource.uri] = resource

    def _reply(self, msg_id, result=None, error=None):
        if msg_id is None:
            return None  # a notification never gets a reply
        if error is not None:
            return {"jsonrpc": "2.0", "id": msg_id, "error": error}
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    def _handle(self, msg):
        method = msg.get("method")
        msg_id = msg.get("id")

        if method == "initialize":
            return self._reply(msg_id, {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {
                    "tools": {},
                    **({"resources": {}} if self.resources else {}),
                },
                "serverInfo": {"name": self.name, "version": self.version},
            })

        if method == "notifications/initialized":
            return None

        if method == "tools/list":
            return self._reply(msg_id, {"tools": [t.to_mcp() for t in self.tools.values()]})

        if method == "tools/call":
            params = msg.get("params") or {}
            tool = self.tools.get(params.get("name"))

            if tool is None:
                return self._reply(msg_id, error={
                    "code": -32602, "message": f"unknown tool: {params.get('name')!r}",
                })

            try:
                result = tool.handler(params.get("arguments") or {})
                is_error = isinstance(result, dict) and "error" in result
            except Exception as exc:  # a tool bug is a tool-execution error, not a protocol error
                result, is_error = {"error": str(exc)}, True

            return self._reply(msg_id, {
                "content": [{"type": "text", "text": json.dumps(result)}],
                "isError": is_error,
            })

        if method == "resources/list":
            return self._reply(msg_id, {"resources": [r.to_mcp() for r in self.resources.values()]})

        if method == "resources/read":
            params = msg.get("params") or {}
            resource = self.resources.get(params.get("uri"))

            if resource is None:
                return self._reply(msg_id, error={
                    "code": -32602, "message": f"unknown resource: {params.get('uri')!r}",
                })

            return self._reply(msg_id, {
                "contents": [{"uri": resource.uri, "mimeType": resource.mime_type, "text": resource.reader()}],
            })

        return self._reply(msg_id, error={"code": -32601, "message": f"unknown method: {method!r}"})

    def serve_forever(self):
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            reply = self._handle(json.loads(line))
            if reply is not None:
                sys.stdout.write(json.dumps(reply) + "\n")
                sys.stdout.flush()


class MCPClient:
    """Launches one MCP server as a subprocess and talks JSON-RPC to it over
    its stdin/stdout, one message per line.

    `log`, when given a list, gets every raw JSON-RPC message appended to it
    in wire order (direction + the exact dict sent or received) - that list
    is eval/w9d/wire.json's source before hand annotation, not a re-typed
    approximation of it.
    """

    def __init__(self, server_label, command, args, log=None):
        self.server_label = server_label
        resolved = sys.executable if command in ("python", "python3") else command

        self._proc = subprocess.Popen(
            [resolved, *args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=REPO_ROOT,
        )
        self._next_id = 1
        self._log = log

    def _send(self, msg):
        if self._log is not None:
            self._log.append({"server": self.server_label, "direction": "client->server", "raw": msg})
        self._proc.stdin.write(json.dumps(msg) + "\n")
        self._proc.stdin.flush()

    def _recv(self):
        line = self._proc.stdout.readline()
        if not line:
            stderr = self._proc.stderr.read()
            raise RuntimeError(f"{self.server_label} closed its stdout unexpectedly. stderr:\n{stderr}")
        msg = json.loads(line)
        if self._log is not None:
            self._log.append({"server": self.server_label, "direction": "server->client", "raw": msg})
        return msg

    def _request(self, method, params=None):
        msg_id = self._next_id
        self._next_id += 1
        self._send({"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params or {}})
        return self._recv()

    def _notify(self, method, params=None):
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def initialize(self, client_name="w9d-agent", client_version="1.0.0"):
        response = self._request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": client_name, "version": client_version},
        })
        self._notify("notifications/initialized")
        return response["result"]

    def list_tools(self):
        return self._request("tools/list")["result"]["tools"]

    def call_tool(self, name, arguments):
        response = self._request("tools/call", {"name": name, "arguments": arguments})

        if "error" in response:
            return {"error": response["error"]["message"]}

        text = response["result"]["content"][0]["text"]

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"text": text}

    def list_resources(self):
        return self._request("resources/list")["result"]["resources"]

    def read_resource(self, uri):
        response = self._request("resources/read", {"uri": uri})
        return response["result"]["contents"][0]["text"]

    def close(self):
        try:
            self._proc.stdin.close()
        except OSError:
            pass
        try:
            self._proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._proc.kill()
