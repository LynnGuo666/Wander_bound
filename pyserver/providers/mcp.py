"""JSON RPC transport and runtime MCP tool discovery."""
from __future__ import annotations

import json
import httpx
import os

def data_endpoint() -> str:
    endpoint = os.getenv("TRAVEL_DATA_MCP_URL", "")
    if not endpoint:
        raise RuntimeError("TRAVEL_DATA_MCP_URL 未配置")
    if not (endpoint.startswith("http://127.0.0.1:") or endpoint.startswith("http://localhost:")
            or endpoint.startswith("https://") or ".ts.net:" in endpoint):
        raise ValueError("Spark MCP 必须使用本机隧道、HTTPS 或 Tailscale 私网")
    return endpoint


async def mcp_request(endpoint: str, method: str, params: dict | None = None,
                      headers: dict | None = None, timeout: float = 20) -> dict:
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=8)) as client:
        response = await client.post(endpoint, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
                                     headers={"Accept": "application/json, text/event-stream", **(headers or {})})
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


async def mcp_call(endpoint: str, name: str, args: dict, *, credentials: dict | None = None,
                   timeout: float = 95) -> object:
    keys = {"tuniu": "X-Tuniu-Key", "dida": "X-Dida-Key", "flyai": "X-FlyAI-Key", "duffel": "X-Duffel-Key"}
    headers = {header: credentials[key] for key, header in keys.items() if credentials and credentials.get(key)}
    result = await mcp_request(endpoint, "tools/call", {"name": name, "arguments": args}, headers, timeout)
    if result.get("isError"):
        raise RuntimeError("MCP 工具执行失败")
    if isinstance(result.get("structuredContent"), dict):
        return result["structuredContent"]
    text = next((item.get("text", "") for item in result.get("content", []) if item.get("type") == "text"), "")
    return json.loads(text)
