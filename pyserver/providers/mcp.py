"""JSON RPC transport and runtime MCP tool discovery."""
from __future__ import annotations

import json
import httpx

async def mcp_request(endpoint: str, method: str, params: dict | None = None) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(endpoint, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
                                     headers={"Accept": "application/json, text/event-stream"})
        response.raise_for_status()
        data = response.json()
    if data.get("error"):
        raise RuntimeError(str(data["error"].get("message") or "MCP error"))
    return data.get("result") or {}


async def list_mcp_tools(endpoint: str | None) -> dict:
    if not endpoint:
        return {"kind": "MCP", "discovery": "unavailable", "tools": [], "metadataSource": "tools/list"}
    try:
        result = await mcp_request(endpoint, "tools/list")
        return {"kind": "MCP", "discovery": "runtime", "tools": [{"name": t.get("name"), "description": t.get("description", ""),
                "inputSchema": t.get("inputSchema")} for t in result.get("tools", [])], "metadataSource": "tools/list"}
    except Exception:
        return {"kind": "MCP", "discovery": "failed", "tools": [], "metadataSource": "tools/list"}


async def mcp_call(endpoint: str, name: str, args: dict) -> object:
    result = await mcp_request(endpoint, "tools/call", {"name": name, "arguments": args})
    if result.get("isError"):
        raise RuntimeError("MCP 工具执行失败")
    import json
    text = next((item.get("text", "") for item in result.get("content", []) if item.get("type") == "text"), "")
    return json.loads(text)

