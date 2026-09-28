"""Normalized attraction offers from Spark's Node.js OTA MCP service."""
from __future__ import annotations

from .js_api import post_configured


async def search_attractions(city: str, places: list[dict], credentials: dict, priorities: dict) -> list[dict]:
    payload = {"city": city, "places": places[:7],
               "credentials": {key: credentials[key] for key in ("flyai", "tuniu") if credentials.get(key)},
               "priorities": priorities}
    result = await post_configured("TRAVEL_ATTRACTIONS_API_URL", payload, timeout=35)
    if not result.get("ok") or not isinstance(result.get("offers"), list):
        raise RuntimeError("Spark 景区产品服务响应无效")
    return result["offers"]
