"""Amap REST data for dining and ground navigation (non-MCP)."""
from __future__ import annotations

import asyncio
import math

import httpx

from .amap_quota import consume as consume_quota
from .coordinates import wgs_to_gcj


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
    geometry = []
    def append_geometry(polyline):
        for pair in str(polyline or "").split(";"):
            try:
                lng, lat = (float(value) for value in pair.split(","))
                if -180 <= lng <= 180 and -90 <= lat <= 90 and (not geometry or geometry[-1] != {"lat": lat, "lng": lng}):
                    geometry.append({"lat": lat, "lng": lng})
            except (TypeError, ValueError):
                continue
    segments = ([{"mode": "walk", "instruction": str(step.get("instruction") or "")[:160],
                  "distanceMeters": _number(step.get("distance"))} for step in (path.get("steps") or [])[:8]]
                if walking else [])
    if walking:
        for step in path.get("steps") or []:
            append_geometry(step.get("polyline"))
    if not walking:
        for item in (path.get("segments") or [])[:8]:
            walking_part = item.get("walking") or {}
            walk = walking_part.get("distance")
            if (_number(walk) or 0) > 0:
                segments.append({"mode": "walk", "distanceMeters": _number(walk)})
            for step in walking_part.get("steps") or []:
                append_geometry(step.get("polyline"))
            line = ((item.get("bus") or {}).get("buslines") or [None])[0]
            if line:
                append_geometry(line.get("polyline"))
                segments.append({"mode": "transit", "line": str(line.get("name") or "")[:100],
                                 "board": (line.get("departure_stop") or {}).get("name"),
                                 "alight": (line.get("arrival_stop") or {}).get("name")})
    return {"minutes": math.ceil(float(path["duration"]) / 60), "source": "高德步行路线" if walking else "高德公共交通",
            "mode": "walk" if walking else "transit", "walkingMeters": _number(path.get("distance" if walking else "walking_distance")),
            "fare": None if walking else _number(path.get("cost")), "currency": None if walking else "CNY", "segments": segments,
            "geometry": geometry, "coordinateSystem": "GCJ-02"}


async def terminal_point(label: str, city: str, key: str) -> dict | None:
    """Resolve a supplier terminal label to a POI; never use the city centre as an airport."""
    if not label or not city:
        return None
    if not any(word in label.lower() for word in ("机场", "站", "airport", "station")) and not (len(label) == 3 and label.isascii() and label.isupper()):
        return None
    await consume_quota("poi")
    payload = await _get("place/text", {"key": key, "keywords": label,
                                           "city": city, "citylimit": "true", "offset": 5})
    for row in payload.get("pois") or []:
        name = str(row.get("name") or "")
        if not ("机场" in name or "站" in name):
            continue
        try:
            lng, lat = (float(value) for value in str(row.get("location") or "").split(","))
        except ValueError:
            continue
        return {"name": name, "lat": lat, "lng": lng, "coordinateSystem": "GCJ-02", "source": "高德 POI"}
    return None


async def hotel_point(label: str, city: str, key: str) -> dict | None:
    if not label or not city:
        return None
    await consume_quota("poi")
    payload = await _get("place/text", {"key": key, "keywords": label, "city": city,
                                           "citylimit": "true", "offset": 5})
    for row in payload.get("pois") or []:
        if label not in str(row.get("name") or "") and str(row.get("name") or "") not in label:
            continue
        try:
            lng, lat = (float(value) for value in str(row.get("location") or "").split(","))
        except ValueError:
            continue
        return {"name": str(row["name"]), "lat": lat, "lng": lng, "approximate": False,
                "coordinateSystem": "GCJ-02", "source": "高德 POI"}
    return None


async def enrich_routes(plan: dict, key: str | None) -> dict:
    if not key:
        return plan
    journeys = []
    outbound = next((item for item in (plan.get("flights") or []) + (plan.get("trains") or [])
                     if item.get("id") in {plan.get("recommendedOutboundFlightId"), plan.get("recommendedOutboundTrainId")}), None)
    returns = (plan.get("returnFlights") or []) + (plan.get("returnTrains") or [])
    inbound = next((item for item in returns if item.get("id") in
                    {plan.get("recommendedReturnFlightId"), plan.get("recommendedReturnTrainId")}), None)
    if inbound is None:
        inbound = next((item for item in returns if item.get("departureAt")), None)
    terminals = {}
    for role, offer, label, city in (("outboundOrigin", outbound, "origin", plan.get("originCity")),
                                      ("outboundDestination", outbound, "destination", plan.get("destination")),
                                      ("returnOrigin", inbound, "origin", plan.get("destination"))):
        if offer:
            try:
                terminals[role] = await terminal_point(str(offer.get(label) or ""), city, key)
            except (httpx.HTTPError, RuntimeError):
                terminals[role] = None
    plan["terminals"] = terminals
    stay = plan.get("stayArea") or {}
    start = plan.get("startLocation") or {}
    if _number(start.get("lat")) is not None and _number(start.get("lng")) is not None:
        start = {"name": "出发地点", **wgs_to_gcj(start["lat"], start["lng"]), "coordinateSystem": "GCJ-02"}
    async def add(day: dict, origin: dict | None, destination: dict | None, purpose: str):
        if not origin or not destination or any(_number(point.get(coord)) is None for point in (origin, destination) for coord in ("lat", "lng")):
            journeys.append({"day": day["day"], "purpose": purpose, "from": (origin or {}).get("name"),
                             "to": (destination or {}).get("name"), "minutes": None, "status": "unknown"})
            return
        try:
            route = await route_minutes(origin, destination,
                                        plan.get("originCity") if purpose == "to-terminal" else day["city"], key)
        except (httpx.HTTPError, RuntimeError):
            route = None
        if route is None:
            journeys.append({"day": day["day"], "purpose": purpose, "from": origin["name"], "to": destination["name"],
                             "fromCoordinate": {"lat": origin["lat"], "lng": origin["lng"]},
                             "toCoordinate": {"lat": destination["lat"], "lng": destination["lng"]},
                             "minutes": None, "status": "unknown"})
            return
        journeys.append({"day": day["day"], "purpose": purpose, "from": origin["name"], "to": destination["name"],
                         "fromCoordinate": {"lat": origin["lat"], "lng": origin["lng"]},
                         "toCoordinate": {"lat": destination["lat"], "lng": destination["lng"]},
                         "status": "estimated", **route,
                         "imagery": {"status": "check-on-device", "provider": "Apple MapKit Look Around"}})
        if purpose == "to-place":
            destination["travelMinutes"] = route["minutes"]
            destination["travelSource"] = route["source"]
    arrival_day = str((outbound or {}).get("arrivalAt") or "")[:10]
    for day_index, day in enumerate(plan["itinerary"]):
        if day_index == 0 and outbound:
            await add(day, {"name": "出发地点", **start} if start else None, terminals.get("outboundOrigin"), "to-terminal")
        if outbound and day["date"] == arrival_day:
            await add(day, terminals.get("outboundDestination"), stay, "arrival-to-stay")
        elif day_index == 0 and stay:
            await add(day, None, stay, "arrival-to-stay")
        previous = stay
        for index, stop in enumerate(day["stops"]):
            await add(day, previous, stop, "to-place")
            previous = stop
        if day["stops"]:
            await add(day, previous, stay, "return-to-stay")
        if day_index == len(plan["itinerary"]) - 1 and inbound:
            await add(day, stay, terminals.get("returnOrigin"), "to-return-terminal")
    return {**plan, "groundJourneys": journeys}
