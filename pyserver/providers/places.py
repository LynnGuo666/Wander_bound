"""Verified POI lookup using Amap or the remote OTA MCP."""
from __future__ import annotations

import os
import httpx
from .mcp import mcp_call

async def search_places(city: str, key: str | None) -> list[dict]:
    if not city:
        return []
    if not key:
        endpoint = os.getenv("TRAVEL_OTA_MCP_URL")
        if not endpoint:
            return []
        payload = await mcp_call(endpoint, "flyai_search_poi", {"city": city})
        if payload.get("status") != 0:
            raise RuntimeError(str(payload.get("message") or "飞猪地点查询失败"))
        places = []
        for row in (payload.get("data") or {}).get("itemList") or []:
            try:
                lat, lng = float(row["latitude"]), float(row["longitude"])
            except (KeyError, TypeError, ValueError):
                continue
            if not row.get("id") or not row.get("name"):
                continue
            places.append({"id": f"flyai-{row['id']}", "name": str(row["name"]), "lat": lat, "lng": lng,
                           "area": city, "category": str(row.get("category") or "景点"), "duration": None,
                           "description": str(row.get("address") or ""), "source": "飞猪 FlyAI"})
        return places
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
