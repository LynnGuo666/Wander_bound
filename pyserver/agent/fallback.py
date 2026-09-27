"""Bounded server-side completion when Step ends without a tool call."""
from __future__ import annotations

from datetime import date, timedelta

from .handlers import execute
from .schedule import day_windows, capacity


def _assignments(state: dict, place_ids: list[str]) -> list[dict]:
    start = date.fromisoformat(state["startDate"])
    days = [(start + timedelta(days=index)).isoformat() for index in range(state["days"])]
    windows = day_windows(state)
    result = []
    for day in days:
        required = next((stay for stay in state["requiredStays"] if stay["from"] <= day <= stay["to"]), None)
        result.append({"date": day, "city": required["city"] if required else state["destination"], "placeIds": []})
    catalog = {item["id"]: item for item in state["places"]}
    for place_id in place_ids:
        city = catalog[place_id]["city"]
        matches = [item for item in result if item["city"] == city and item["date"] in windows
                   and ("夜" not in catalog[place_id]["name"] or windows[item["date"]][1].hour >= 21)
                   and len(item["placeIds"]) < capacity(windows[item["date"]])]
        if matches:
            min(matches, key=lambda item: len(item["placeIds"]))["placeIds"].append(place_id)
    return result


async def complete_with_tools(state: dict, credentials: dict, request: dict, priorities: dict):
    """Yield executed tool calls; the caller records each one in the normal trace."""
    if not state.get("destination") or not state.get("originCity") or not state.get("startDate") or not isinstance(state.get("days"), int):
        return
    sequence = []
    if not state.get("originDone"):
        sequence.append(("resolve_origin", {}))
    cities = {state["destination"], *(stay["city"] for stay in state.get("requiredStays") or [])}
    known_cities = {item.get("city") for item in state.get("places") or []}
    sequence.extend(("discover_places", {"city": city}) for city in cities if city not in known_cities)
    if not state.get("transportDone"):
        sequence.append(("search_transport", {}))
    if not state.get("staysDone"):
        sequence.append(("search_stays", {}))
    for name, args in sequence:
        for attempt in range(2):
            yield "start", name, args, None
            try:
                result = await execute(name, args, state, credentials, request, priorities)
            except Exception as exc:
                result = {"ok": False, "code": "tool_failed", "message": str(exc)[:200]}
            yield "end", name, args, result
            if result.get("ok"):
                break
        if not result.get("ok"):
            return
    cities = {state["destination"], *(stay["city"] for stay in state.get("requiredStays") or [])}
    windows = day_windows(state)
    maximum = min(8, max(2, state["days"] * 2), sum(capacity(window) for window in windows.values()))
    city_slots = {}
    for day, window in windows.items():
        required = next((stay for stay in state.get("requiredStays") or [] if stay["from"] <= day <= stay["to"]), None)
        city = required["city"] if required else state["destination"]
        city_slots[city] = city_slots.get(city, 0) + capacity(window)
    selected = []
    for item in state["places"]:
        city = item.get("city")
        if len(selected) >= maximum or city not in cities or city_slots.get(city, 0) <= 0:
            continue
        if "夜" in item.get("name", "") and not any(window[1].hour >= 21 for window in windows.values()):
            continue
        selected.append(item["id"])
        city_slots[city] -= 1
    args = {"placeIds": selected, "dayAssignments": _assignments(state, selected)}
    yield "start", "draft_plan", args, None
    result = await execute("draft_plan", args, state, credentials, request, priorities)
    yield "end", "draft_plan", args, result
    if result.get("code") == "infeasible_trip":
        question = {"question": "按真实去返程时刻，这几天没有足够的游玩时间。您希望怎样调整？",
                    "options": [{"id": "longer", "label": "延长旅行天数"},
                                {"id": "flight", "label": "改用更快的交通"},
                                {"id": "dates", "label": "更改出发日期"}]}
        yield "start", "ask_question", question, None
        response = await execute("ask_question", question, state, credentials, request, priorities)
        yield "end", "ask_question", question, response
