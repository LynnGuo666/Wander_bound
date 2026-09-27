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

async def search_transport(state: dict) -> dict:
    if not state["originDone"] or not state["startDate"]:
        return _error("missing_transport_spec", "缺少出发城市或日期")
    state["trains"] = await providers.search_trains(state["originCity"], state["destination"], state["startDate"])
    state["transportDone"] = True
    return {"ok": True, "outboundFlights": [], "returnFlights": [], "outboundTrains": state["trains"], "returnTrains": []}

async def search_stays(state: dict) -> dict:
    state["staysDone"] = True
    return {"ok": True, "hotels": state["hotels"], "source": "unconfigured"}

