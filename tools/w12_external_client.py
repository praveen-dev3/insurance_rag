"""A stand-alone MCP client for the policy-wording server - the "client that isn't yours".

    python tools/w12_external_client.py                 # spawns the server itself
    python tools/w12_external_client.py --cmd "python tools/w12_policy_server.py"

Standard library only; imports nothing from this repo, so it exercises the
server through the protocol and nothing else. It does what a reviewer from
another squad would do on Thursday: initialize, list the tools, read the
descriptions cold, call each tool, and then try the three calls that most
often go wrong - a missing loss date, a bad product, a loss before any
wording was in force - to see whether the errors tell it how to recover.

This is a *stand-in*. It was written by the same author as the server, so
it cannot find the stumbles a stranger would. The fresh-eyes review the
capstone asks for is a person from another squad running something like
this without reading the server code; see FRESH_EYES_W12.md for what is
and is not done.
"""

import argparse
import json
import os
import subprocess
import sys


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("--cmd", default=f'"{sys.executable}" tools/w12_policy_server.py')
    args = parser.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    proc = subprocess.Popen(args.cmd, shell=True, cwd=root, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
    next_id = [0]

    def rpc(method, params=None, notify=False):
        message = {"jsonrpc": "2.0", "method": method, "params": params or {}}

        if not notify:
            next_id[0] += 1
            message["id"] = next_id[0]

        proc.stdin.write(json.dumps(message) + "\n")
        proc.stdin.flush()

        return None if notify else json.loads(proc.stdout.readline())

    print("== initialize")
    print(json.dumps(rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                        "clientInfo": {"name": "external-reviewer", "version": "0"}})["result"]["serverInfo"]))
    rpc("notifications/initialized", notify=True)

    tools = rpc("tools/list")["result"]["tools"]
    print("\n== tools/list")

    for tool in tools:
        print(f"- {tool['name']}: {tool['description'][:110]}...")
        print(f"    required args: {tool['inputSchema'].get('required')}")

    def call(name, arguments, note):
        reply = rpc("tools/call", {"name": name, "arguments": arguments, "_meta": {"trace_id": "external-client-1"}})
        result = reply["result"]
        body = json.loads(result["content"][0]["text"])
        print(f"\n== {note}\n   {name}({json.dumps(arguments)[:140]})  isError={result.get('isError')}")
        print("   ->", json.dumps(body)[:420])
        return body

    call("search_policy_wording", {"query": "flood exclusion dwelling", "product": "household",
                                   "loss_date": "2024-08-11"}, "wording as at 11 Aug 2024 (old edition)")
    call("search_policy_wording", {"query": "flood exclusion dwelling", "product": "household",
                                   "loss_date": "2025-04-01"}, "wording as at 1 Apr 2025 (new edition, first day)")
    call("search_policy_wording", {"query": "flood exclusion dwelling", "product": "household",
                                   "loss_date": "2025-03-31"}, "wording as at 31 Mar 2025 (day before)")
    call("get_limits", {"policy_number": "POL-H-1001", "loss_date": "2025-04-01", "peril_class": "flood"},
         "three distinct numbers")
    call("search_policy_wording", {"query": "flood", "product": "household"}, "stumble 1: no loss date")
    call("search_policy_wording", {"query": "flood", "product": "marine", "loss_date": "2025-01-01"},
         "stumble 2: unknown product")
    call("search_policy_wording", {"query": "flood", "product": "household", "loss_date": "2023-03-15"},
         "stumble 3: loss before any flood wording existed")

    proc.stdin.close()
    proc.wait(timeout=10)
    return 0


if __name__ == "__main__":
    sys.exit(main())
