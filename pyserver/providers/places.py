"""Verified POI lookup using Amap or the remote OTA MCP."""
from __future__ import annotations

import os
import httpx
from .mcp import data_endpoint, mcp_call
from .amap_quota import consume as consume_quota

async def search_places(city: str, key: str | None) -> list[dict]:
    if not city:
        return []
    if not key:
        payload = await mcp_call(data_endpoint(), "travel_search_places", {"city": city})
        if not payload.get("ok") or not isinstance(payload.get("places"), list):
            raise RuntimeError("飞猪地点查询响应无效")
        return payload["places"]
    # 高德 POI 搜索计费项，先记账再发起请求。
    await consume_quota("poi")
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get("https://restapi.amap.com/v3/place/text", params={"key": key, "keywords": "景点", "city": city,
                        "citylimit": "true", "offset": 20, "page": 1, "extensions": "all"})
        response.raise_for_status()
        payload = response.json()
    if payload.get("status") != "1":
        raise RuntimeError("高德地点查询失败")
    places = []
    for row in payload.get("pois", []):
        try:
            lng, lat = (float(value) for value in row["location"].split(","))
        except (KeyError, ValueError, AttributeError):
            continue
        places.append({"id": str(row["id"]), "name": str(row.get("name", "")), "lat": lat, "lng": lng,
                       "area": str(row.get("adname") or city), "category": str(row.get("type") or "景点").split(";")[0],
                       "duration": None, "description": str(row.get("address") or ""), "source": "高德"})
    return places
