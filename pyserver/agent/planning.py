"""Build a dated itinerary exclusively from verified place IDs."""
from __future__ import annotations

from datetime import date, timedelta
from ..trips import now
from .state import _error
from .schedule import day_windows, capacity, select_outbound, select_return

async def draft_plan(args: dict, state: dict) -> dict:
    if not state["destination"] or not state["startDate"] or not isinstance(state["days"], int):
        return _error("incomplete_spec", "先确定目的地、日期和总天数")
    ids = args.get("placeIds")
    catalog = {item["id"]: item for item in state["places"]}
    if not isinstance(ids, list) or any(not isinstance(item, str) for item in ids) or len(set(ids)) != len(ids):
        return _error("unverified_place", "地点 ID 必须是没有重复的列表")
    unknown = [item for item in ids if item not in catalog]
    if unknown:
        valid = ", ".join(f"{item['id']}={item['name']}" for item in state["places"][:30])
        return _error("unverified_place", f"未核实的地点 ID：{', '.join(str(item) for item in unknown[:8])}。可用 ID：{valid}")
    start = date.fromisoformat(state["startDate"])
    dates = [(start + timedelta(days=index)).isoformat() for index in range(state["days"])]
    windows = day_windows(state)
    if not windows and (ids or state["days"] > 1):
        return _error("infeasible_trip", "真实去返程时刻没有留下可游玩的时间，请调整日期、天数或交通方式")
    if len(ids) > sum(capacity(window) for window in windows.values()):
        return _error("too_many_places", "已选地点超过真实去返程时刻允许的游玩容量，请减少地点")
    assignments = args.get("dayAssignments")
    if assignments is not None:
        if not isinstance(assignments, list) or any(not isinstance(item, dict) or item.get("date") not in dates or not isinstance(item.get("placeIds"), list) for item in assignments):
            return _error("invalid_schedule", "逐日日期或地点列表无效")
        if len({item["date"] for item in assignments}) != len(assignments):
            return _error("invalid_schedule", "同一日期重复编排")
        if any(item["placeIds"] and (item["date"] not in windows or len(item["placeIds"]) > capacity(windows[item["date"]])) for item in assignments):
            return _error("invalid_schedule", "所选日期的景点超过抵达与返程之间的可游玩时间")
        chosen = [item for assignment in assignments for item in assignment["placeIds"]]
        if len(set(chosen)) != len(chosen) or set(chosen) != set(ids):
            return _error("invalid_schedule", "逐日地点必须与已选地点一致且不可重复")
        if any("夜" in catalog[place_id]["name"] and windows[item["date"]][1].hour < 21
               for item in assignments for place_id in item["placeIds"]):
            return _error("invalid_schedule", "夜游项目必须安排在返程时刻允许的晚上")
        for assignment in assignments:
            if any(catalog[item]["city"] != assignment.get("city") for item in assignment["placeIds"]):
                return _error("invalid_city", "逐日城市与地点来源不一致")
        scheduled = {item["date"]: item for item in assignments}
    else:
        # Arrival and return days can hold one place when the supplier timetable allows it.
        use_dates = [day for day in dates if day in windows]
        scheduled = {day: {"date": day, "city": next((stay["city"] for stay in state["requiredStays"]
                      if stay["from"] <= day <= stay["to"]), state["destination"]), "placeIds": []} for day in dates}
        for place_id in ids:
            day = next((day for day in sorted(use_dates, key=lambda candidate: len(scheduled[candidate]["placeIds"]))
                        if scheduled[day]["city"] == catalog[place_id]["city"]
                        and ("夜" not in catalog[place_id]["name"] or windows[day][1].hour >= 21)
                        and len(scheduled[day]["placeIds"]) < (min(1, capacity(windows[day])) if day in {dates[0], dates[-1]} and len(dates) > 1 else capacity(windows[day]))), None)
            if day is None:
                return _error("too_many_places", "可游玩日期不足，请减少地点")
            scheduled[day]["placeIds"].append(place_id)
    itinerary = []
    recommendations = args.get("recommendedDurations") or {}
    if not isinstance(recommendations, dict) or any(key not in catalog or type(value) is not int or not 30 <= value <= 360
                                                    for key, value in recommendations.items()):
        return _error("invalid_duration", "游玩时长建议应按已核实地点 ID 提供 30–360 分钟")
    for index in range(state["days"]):
        day = dates[index]
        assignment = scheduled.get(day) or {"city": state["destination"], "placeIds": []}
        required = next((stay for stay in state["requiredStays"] if stay["from"] <= day <= stay["to"]), None)
        if required and assignment["city"] != required["city"]:
            return _error("required_stay", f"{day} 必须停留在 {required['city']}")
        stops = [{**catalog[item], "recommendedDurationMinutes": recommendations.get(item),
                  "start": None, "travelMinutes": None, "travelSource": None}
                 for item in assignment["placeIds"]]
        itinerary.append({"day": index + 1, "date": day, "city": assignment["city"], "requiredStay": bool(required),
                          "title": f"{assignment['city']} · 第 {index + 1} 天", "stops": stops})
    areas = {}
    for item in (stop for day in itinerary for stop in day["stops"]):
        if item.get("area"):
            areas[item["area"]] = areas.get(item["area"], 0) + 1
    if areas:
        area_name = max(areas, key=areas.get)
        area_stops = [stop for day in itinerary for stop in day["stops"] if stop.get("area") == area_name
                      and isinstance(stop.get("lat"), (int, float)) and isinstance(stop.get("lng"), (int, float))]
        stay_area = {"name": f"{area_name}住宿区域（待选酒店）", "area": area_name,
                     "lat": sum(stop["lat"] for stop in area_stops) / len(area_stops) if area_stops else None,
                     "lng": sum(stop["lng"] for stop in area_stops) / len(area_stops) if area_stops else None,
                     "approximate": True}
    else:
        stay_area = None
    outbound = select_outbound(state)
    returning = select_return(state)
    mode = "train" if outbound in (state.get("trains") or []) else "flight"
    plan = {"destination": state["destination"], "originCity": state["originCity"], "startDate": state["startDate"],
            "endDate": (start + timedelta(days=state["days"] - 1)).isoformat(), "days": state["days"],
            "intro": "根据已确认的约束与已核实地点编排", "revisit": False, "skippedPlaces": [], "itinerary": itinerary,
            "stayArea": stay_area, "flights": state.get("flights") or [], "returnFlights": state.get("returnFlights") or [],
            "trains": state["trains"], "returnTrains": state.get("returnTrains") or [], "hotels": state["hotels"],
            "attractionOffers": [], "dining": [], "groundJourneys": [], "providerStatus": state.get("providerStatus") or {},
            "transportPreference": (state.get("preferences") or {}).get("transportPreference") or mode,
            "selectedTransportMode": mode, "hotelBrands": (state.get("preferences") or {}).get("hotelBrands") or [],
            "generatedAt": now(), "locationDetected": False, "requiredStays": state["requiredStays"],
            "totalBudgetCny": state["totalBudgetCny"],
            "startLocation": (state.get("request") or {}).get("location"),
            "recommendedOutboundTrainId": outbound.get("id") if outbound and mode == "train" else None,
            "recommendedOutboundFlightId": outbound.get("id") if outbound and mode == "flight" else None,
            "recommendedReturnTrainId": returning.get("id") if returning and returning in (state.get("returnTrains") or []) else None,
            "recommendedReturnFlightId": returning.get("id") if returning and returning in (state.get("returnFlights") or []) else None}
    state["plan"] = plan
    state["enrichmentDone"] = False
    return {"ok": True, "days": itinerary, "selectedPlaceIds": ids}
