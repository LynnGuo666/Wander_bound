"""Post-plan non-MCP dining and ground data from Amap."""
from __future__ import annotations

from ..providers import amap


async def search_dining(plan: dict, key: str | None) -> dict:
    if not key:
        plan["providerStatus"]["dining"] = {"configured": False, "result": "未配置", "label": "高德餐饮 POI"}
        return {"ok": True, "suggestions": []}
    anchors = [{**day["stops"][-1], "day": day["day"]} for day in plan["itinerary"] if day["stops"]]
    try:
        candidates = await amap.search_dining(plan["destination"], anchors, key)
        by_day = {}
        for candidate in candidates:
            current = by_day.get(candidate["day"])
            if current is None or (candidate.get("rating") or 0) > (current.get("rating") or 0):
                by_day[candidate["day"]] = candidate
        plan["dining"] = [by_day[day] for day in sorted(by_day)]
        plan["providerStatus"]["dining"] = {"configured": True, "result": "ok" if by_day else "本次无可核实餐饮结果", "label": "高德餐饮 POI"}
        return {"ok": True, "suggestions": [{field: row.get(field) for field in ("id", "name", "day", "rating", "averageCost", "source")}
                                          for row in plan["dining"]]}
    except Exception as exc:
        plan["providerStatus"]["dining"] = {"configured": True, "error": True, "result": str(exc)[:160], "label": "高德餐饮 POI"}
        return {"ok": False, "code": "dining_failed", "message": str(exc)[:160]}


async def explore_ground(plan: dict, key: str | None) -> dict:
    if not key:
        plan["providerStatus"]["ground"] = {"configured": False, "result": "未配置", "label": "高德步行与公交"}
        return {"ok": True, "verifiedLegs": 0}
    try:
        plan.update(await amap.enrich_routes(plan, key))
        journeys = plan.get("groundJourneys") or []
        plan["providerStatus"]["ground"] = {"configured": True, "result": "ok" if journeys else "本次无可核实路线", "label": "高德步行与公交"}
        return {"ok": True, "verifiedLegs": len(journeys), "legs": [{field: item.get(field) for field in ("day", "from", "to", "minutes", "mode", "source")}
                                                                for item in journeys[:12]]}
    except Exception as exc:
        plan["providerStatus"]["ground"] = {"configured": True, "error": True, "result": str(exc)[:160], "label": "高德步行与公交"}
        return {"ok": False, "code": "ground_failed", "message": str(exc)[:160]}
