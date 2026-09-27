"""Bounded server-side completion when Step ends without a tool call."""
from __future__ import annotations

from datetime import date, timedelta

from .handlers import execute


def _assignments(state: dict, place_ids: list[str]) -> list[dict]:
    start = date.fromisoformat(state["startDate"])
    days = [(start + timedelta(days=index)).isoformat() for index in range(state["days"])]
    result = []
    for day in days:
        required = next((stay for stay in state["requiredStays"] if stay["from"] <= day <= stay["to"]), None)
        result.append({"date": day, "city": required["city"] if required else state["destination"], "placeIds": []})
    catalog = {item["id"]: item for item in state["places"]}
    for place_id in place_ids:
        city = catalog[place_id]["city"]
        matches = [item for item in result if item["city"] == city]
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
    selected = [item["id"] for item in state["places"] if item.get("city") in cities][:min(8, max(2, state["days"] * 2))]
    args = {"placeIds": selected, "dayAssignments": _assignments(state, selected)}
    yield "start", "draft_plan", args, None
    result = await execute("draft_plan", args, state, credentials, request, priorities)
    yield "end", "draft_plan", args, result
