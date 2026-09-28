"""Amap REST data for dining and ground navigation (non-MCP)."""
from __future__ import annotations

import asyncio
import math

import httpx

from .amap_quota import consume as consume_quota


async def _get(path: str, params: dict, timeout: float = 8) -> dict:
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(f"https://restapi.amap.com/v3/{path}", params=params)
        response.raise_for_status()
        payload = response.json()
    if payload.get("status") != "1":
        raise RuntimeError(str(payload.get("info") or "高德数据查询失败"))
    return payload


def _number(value) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (ValueError, TypeError):
        return None


async def search_dining(city: str, anchors: list[dict], key: str | None) -> list[dict]:
    if not key:
        return []
    points = [point for point in anchors if _number(point.get("lat")) is not None and _number(point.get("lng")) is not None][:7]

    async def around(point: dict):
        # 每次周边检索计一次 POI 搜索配额（place/around 属于 POI 搜索计费项）。
        await consume_quota("poi")
        data = await _get("place/around", {"key": key, "location": f"{point['lng']:.6f},{point['lat']:.6f}",
                                           "city": city, "types": "050000", "radius": 1800, "sortrule": "weight",
                                           "offset": 15, "extensions": "all"})
        return [(row, point["day"]) for row in data.get("pois") or []]

    results = await asyncio.gather(*(around(point) for point in points), return_exceptions=True)
    if results and all(isinstance(result, Exception) for result in results):
        raise results[0]
    dishes = []
    for result in results:
        if isinstance(result, Exception):
            continue
        for row, day in result:
            if not row.get("id") or not row.get("name"):
                continue
            try:
                lng, lat = (_number(item) for item in str(row.get("location") or "").split(","))
            except ValueError:
                continue
            if lng is None or lat is None:
                continue
            extension = row.get("biz_ext") or {}
            rating, cost = _number(extension.get("rating")), _number(extension.get("cost"))
            photos = [{"url": photo["url"], "caption": str(photo.get("title") or photo.get("titile") or ""), "kind": "poi-photo"}
                      for photo in row.get("photos") or [] if str(photo.get("url") or "").startswith("https://")][:2]
            dishes.append({"id": f"amap-{row['id']}", "providerPlaceId": str(row["id"]), "name": str(row["name"]),
                           "day": day, "lat": lat, "lng": lng, "address": str(row.get("address") or ""),
                           "type": str(row.get("type") or ""), "rating": rating if rating and 0 < rating <= 5 else None,
                           "averageCost": cost if cost and cost > 0 else None, "currency": "CNY", "photos": photos,
                           "source": "高德餐饮 POI", "sourceRecords": [{"provider": "高德", "placeId": str(row["id"]),
                           "rating": rating, "averageCost": cost, "currency": "CNY", "kind": "place-data"}]})
    return dishes


def _distance_km(a: dict, b: dict) -> float:
    lat1, lat2 = math.radians(a["lat"]), math.radians(b["lat"])
    lng1, lng2 = math.radians(a["lng"]), math.radians(b["lng"])
    return 6371 * 2 * math.asin(math.sqrt(math.sin((lat2 - lat1) / 2) ** 2
                                      + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2))


async def route_minutes(origin: dict, destination: dict, city: str, key: str) -> dict | None:
    walking = _distance_km(origin, destination) < 1.8
    params = {"key": key, "origin": f"{origin['lng']},{origin['lat']}",
              "destination": f"{destination['lng']},{destination['lat']}"}
    if not walking:
        params["city"] = city
    # 路径规划属于基础 LBS 计费项。
    await consume_quota("lbs")
    payload = await _get("direction/walking" if walking else "direction/transit/integrated", params)
    route = payload.get("route") or {}
    path = ((route.get("paths") or [None])[0] if walking else (route.get("transits") or [None])[0])
    if not path or not (_number(path.get("duration")) or 0) > 0:
        return None
    segments = ([{"mode": "walk", "instruction": str(step.get("instruction") or "")[:160],
                  "distanceMeters": _number(step.get("distance"))} for step in (path.get("steps") or [])[:8]]
                if walking else [])
    if not walking:
        for item in (path.get("segments") or [])[:8]:
            walk = (item.get("walking") or {}).get("distance")
            if (_number(walk) or 0) > 0:
                segments.append({"mode": "walk", "distanceMeters": _number(walk)})
            line = ((item.get("bus") or {}).get("buslines") or [None])[0]
            if line:
                segments.append({"mode": "transit", "line": str(line.get("name") or "")[:100],
                                 "board": (line.get("departure_stop") or {}).get("name"),
                                 "alight": (line.get("arrival_stop") or {}).get("name")})
    return {"minutes": math.ceil(float(path["duration"]) / 60), "source": "高德步行路线" if walking else "高德公共交通",
            "mode": "walk" if walking else "transit", "walkingMeters": _number(path.get("distance" if walking else "walking_distance")),
            "fare": None if walking else _number(path.get("cost")), "currency": None if walking else "CNY", "segments": segments}


async def enrich_routes(plan: dict, key: str | None) -> dict:
    if not key:
        return plan
    journeys = []
    for day_index, day in enumerate(plan["itinerary"]):
        for index, stop in enumerate(day["stops"]):
            origin = day["stops"][index - 1] if index else (plan.get("stayArea") if day_index else None)
            if not origin or any(_number(point.get(coord)) is None for point in (origin, stop) for coord in ("lat", "lng")):
                continue
            try:
                route = await route_minutes(origin, stop, day["city"], key)
            except (httpx.HTTPError, RuntimeError):
                continue
            if not route:
                continue
            stop["travelMinutes"] = route["minutes"]
            stop["travelSource"] = route["source"]
            journeys.append({"day": day["day"], "from": origin["name"], "to": stop["name"],
                             "fromCoordinate": {"lat": origin["lat"], "lng": origin["lng"]},
                             "toCoordinate": {"lat": stop["lat"], "lng": stop["lng"]}, **route,
                             "imagery": {"status": "check-on-device", "provider": "Apple MapKit Look Around"}})
    return {**plan, "groundJourneys": journeys}
