"""Hotel results from Spark's Node.js Docker MCP adapter."""
from __future__ import annotations

from .mcp import data_endpoint, mcp_call


async def search_stays(city: str, area: str, check_in: str, nights: int,
                       budget: float | None, credentials: dict) -> dict:
    payload = {"city": city, "area": area, "checkInDate": check_in, "stayNights": nights, "budget": budget}
    result = await mcp_call(data_endpoint(), "travel_search_stays", payload, credentials=credentials, timeout=30)
    if not result.get("ok") or not isinstance(result.get("hotels"), list):
        raise RuntimeError("Spark 酒店服务响应无效")
    return result
