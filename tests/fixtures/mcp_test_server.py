#!/usr/bin/env python3
"""Minimal real MCP-style stdio server for tests.

Speaks newline-delimited JSON-RPC 2.0 over stdio:
  initialize           -> server info
  notifications/...    -> ignored (no response, per spec)
  tools/list           -> two tools (echo, fail)
  tools/call           -> executes the tool
Also intentionally prints a non-JSON banner line on startup and writes
chatty stderr — exercises the client's noise-tolerance and stderr drain.
"""
import json
import sys

sys.stderr.write("mcp-test-server starting (chatty stderr is intentional)\n")
sys.stderr.flush()
print("MCP-TEST-SERVER banner (non-JSON noise line)", flush=True)

TOOLS = [
    {
        "name": "echo",
        "description": "Echo the given text back.",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "name": "fail",
        "description": "Always reports an error result.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def handle(method, params, req_id):
    if method == "initialize":
        return {"protocolVersion": "2024-11-05",
                "serverInfo": {"name": "mcp-test-server", "version": "1.0"}}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments", {})
        if name == "echo":
            return {"content": [{"type": "text", "text": f"echo: {args.get('text', '')}"}]}
        if name == "fail":
            return {"content": [{"type": "text", "text": "tool exploded"}], "isError": True}
        return None  # method-level error
    return None


for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        msg = json.loads(line)
    except json.JSONDecodeError:
        continue
    method = msg.get("method", "")
    if method.startswith("notifications/"):
        continue  # fire-and-forget per MCP spec
    req_id = msg.get("id")
    result = handle(method, msg.get("params", {}), req_id)
    if result is None:
        resp = {"jsonrpc": "2.0", "id": req_id,
                "error": {"code": -32601, "message": f"unknown method {method!r}"}}
    else:
        resp = {"jsonrpc": "2.0", "id": req_id, "result": result}
    print(json.dumps(resp), flush=True)
