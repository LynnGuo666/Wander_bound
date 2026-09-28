"""Normalized attraction offers from Spark's Node.js OTA MCP service."""
from __future__ import annotations

from .mcp import data_endpoint, mcp_call


async def search_attractions(city: str, places: list[dict], credentials: dict, priorities: dict) -> list[dict]:
    payload = {"city": city, "places": places[:7], "priorities": priorities}
    result = await mcp_call(data_endpoint(), "travel_search_attractions", payload, credentials=credentials, timeout=35)
    if not result.get("ok") or not isinstance(result.get("offers"), list):
        raise RuntimeError("Spark 景区产品服务响应无效")
    return result["offers"]
