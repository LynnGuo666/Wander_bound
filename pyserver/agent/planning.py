"""Build a dated itinerary exclusively from verified place IDs."""
from __future__ import annotations

from datetime import date, timedelta
from ..trips import now
from .state import _error

async def draft_plan(args: dict, state: dict) -> dict:
    if not state["destination"] or not state["startDate"] or not isinstance(state["days"], int):
        return _error("incomplete_spec", "先确定目的地、日期和总天数")
    ids = args.get("placeIds")
    catalog = {item["id"]: item for item in state["places"]}
    if not isinstance(ids, list) or len(set(ids)) != len(ids) or any(item not in catalog for item in ids):
        return _error("unverified_place", "只能使用 discover_places 返回的地点 ID")
    start = date.fromisoformat(state["startDate"])
    dates = [(start + timedelta(days=index)).isoformat() for index in range(state["days"])]
    assignments = args.get("dayAssignments")
    if assignments is not None:
        if not isinstance(assignments, list) or any(not isinstance(item, dict) or item.get("date") not in dates or not isinstance(item.get("placeIds"), list) for item in assignments):
            return _error("invalid_schedule", "逐日日期或地点列表无效")
        if len({item["date"] for item in assignments}) != len(assignments):
            return _error("invalid_schedule", "同一日期重复编排")
        chosen = [item for assignment in assignments for item in assignment["placeIds"]]
        if len(set(chosen)) != len(chosen) or set(chosen) != set(ids):
            return _error("invalid_schedule", "逐日地点必须与已选地点一致且不可重复")
        for assignment in assignments:
            if any(catalog[item]["city"] != assignment.get("city") for item in assignment["placeIds"]):
                return _error("invalid_city", "逐日城市与地点来源不一致")
        scheduled = {item["date"]: item for item in assignments}
    else:
        # Leave the arrival and departure days light, then spread verified places across the trip.
        use_dates = dates[1:-1] or dates
        scheduled = {day: {"date": day, "city": state["destination"], "placeIds": []} for day in dates}
        for index, place_id in enumerate(ids):
            day = use_dates[index % len(use_dates)]
            scheduled[day]["placeIds"].append(place_id)
    itinerary = []
    for index in range(state["days"]):
        day = dates[index]
        assignment = scheduled.get(day) or {"city": state["destination"], "placeIds": []}
        required = next((stay for stay in state["requiredStays"] if stay["from"] <= day <= stay["to"]), None)
        if required and assignment["city"] != required["city"]:
            return _error("required_stay", f"{day} 必须停留在 {required['city']}")
        stops = [{**catalog[item], "start": "19:00" if "夜" in catalog[item]["name"] else f"{9 + slot * 2:02d}:00",
                  "travelMinutes": None, "travelSource": None} for slot, item in enumerate(assignment["placeIds"])]
        itinerary.append({"day": index + 1, "date": day, "city": assignment["city"], "requiredStay": bool(required),
                          "title": f"{assignment['city']} · 第 {index + 1} 天", "stops": stops})
    plan = {"destination": state["destination"], "originCity": state["originCity"], "startDate": state["startDate"],
            "endDate": (start + timedelta(days=state["days"] - 1)).isoformat(), "days": state["days"],
            "intro": "根据已确认的约束与已核实地点编排", "revisit": False, "skippedPlaces": [], "itinerary": itinerary,
            "stayArea": None, "flights": state.get("flights") or [], "returnFlights": state.get("returnFlights") or [],
            "trains": state["trains"], "returnTrains": state.get("returnTrains") or [], "hotels": state["hotels"],
            "attractionOffers": [], "dining": [], "groundJourneys": [], "providerStatus": state.get("providerStatus") or {}, "transportPreference": "train",
            "hotelBrands": [], "generatedAt": now(), "locationDetected": False, "requiredStays": state["requiredStays"],
            "totalBudgetCny": state["totalBudgetCny"], "recommendedOutboundTrainId": next((item["id"] for item in state["trains"] if item["totalPrice"] is not None), None)}
    state["plan"] = plan
    state["enrichmentDone"] = False
    return {"ok": True, "days": itinerary, "selectedPlaceIds": ids}
