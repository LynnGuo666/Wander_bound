"""On-demand verified places, transport, and stays."""
from __future__ import annotations

from .. import providers
from .state import _error

async def discover_places(args: dict, state: dict, credentials: dict) -> dict:
    city = str(args.get("city") or state["destination"] or "").strip()
    if not city:
        return _error("missing_destination", "请先确定目的地")
    found = await providers.search_places(city, credentials.get("amap"))
    existing = {item["id"]: item for item in state["places"]}
    existing.update({item["id"]: {**item, "city": city} for item in found})
    state["places"] = list(existing.values())
    state["placesDone"] = True
    return {"ok": True, "city": city, "places": [{key: item.get(key) for key in ("id", "name", "area", "category", "duration", "city")} for item in found]}

async def search_transport(state: dict, credentials: dict, priorities: dict) -> dict:
    if not state["originDone"] or not state["startDate"]:
        return _error("missing_transport_spec", "缺少出发城市或日期")
    data = await providers.search_transport(state["originCity"], state["destination"], state["startDate"], state["days"],
                                            credentials, priorities)
    state["trains"] = data["outboundTrains"]
    state["returnTrains"] = data["returnTrains"]
    state["flights"] = data["outboundFlights"]
    state["returnFlights"] = data["returnFlights"]
    state["providerStatus"] = data.get("providerStatus") or {}
    state["transportDone"] = True
    return {"ok": True, **{key: data[key] for key in ("outboundFlights", "returnFlights", "outboundTrains", "returnTrains")},
            "providerStatus": state["providerStatus"], "warnings": data.get("warnings") or []}

async def search_stays(state: dict, credentials: dict, request: dict) -> dict:
    if not state.get("destination") or not state.get("startDate") or not state.get("days"):
        return _error("missing_stay_spec", "缺少住宿城市、日期或天数")
    area = next((item.get("area") for item in state.get("places") or [] if item.get("area")), "")
    preferences = state.get("preferences") or {}
    budget = preferences.get("hotelNightBudget") or (request.get("memory") or {}).get("hotelNightBudget")
    result = await providers.search_stays(state["destination"], area or "", state["startDate"],
                                           max(1, state["days"] - 1), budget, credentials)
    state["hotels"] = result["hotels"]
    state.setdefault("providerStatus", {})["dida"] = {"configured": bool(result.get("configured")),
                                                          "result": "ok" if state["hotels"] else "本次无酒店报价", "label": "道旅 Docker MCP"}
    state["staysDone"] = True
    return {"ok": True, "hotels": state["hotels"], "source": result["source"]}
