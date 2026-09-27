"""Lazily loaded external data tools. No provider is called until its tool runs."""
from __future__ import annotations

import os
from datetime import date

import httpx


async def mcp_request(endpoint: str, method: str, params: dict | None = None) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(endpoint, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
                                     headers={"Accept": "application/json, text/event-stream"})
        response.raise_for_status()
        data = response.json()
    if data.get("error"):
        raise RuntimeError(str(data["error"].get("message") or "MCP error"))
    return data.get("result") or {}


async def list_mcp_tools(endpoint: str | None) -> dict:
    if not endpoint:
        return {"kind": "MCP", "discovery": "unavailable", "tools": [], "metadataSource": "tools/list"}
    try:
        result = await mcp_request(endpoint, "tools/list")
        return {"kind": "MCP", "discovery": "runtime", "tools": [{"name": t.get("name"), "description": t.get("description", ""),
                "inputSchema": t.get("inputSchema")} for t in result.get("tools", [])], "metadataSource": "tools/list"}
    except Exception:
        return {"kind": "MCP", "discovery": "failed", "tools": [], "metadataSource": "tools/list"}


async def mcp_call(endpoint: str, name: str, args: dict) -> object:
    result = await mcp_request(endpoint, "tools/call", {"name": name, "arguments": args})
    if result.get("isError"):
        raise RuntimeError("MCP 工具执行失败")
    import json
    text = next((item.get("text", "") for item in result.get("content", []) if item.get("type") == "text"), "")
    return json.loads(text)


async def search_places(city: str, key: str | None) -> list[dict]:
    if not city or not key:
        return []
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
                       "duration": 90, "description": str(row.get("address") or ""), "source": "高德"})
    return places


def _rail_leg(row: dict) -> dict:
    choices = []
    for item in row.get("prices") or []:
        try:
            price = float(item["price"])
        except (KeyError, TypeError, ValueError):
            continue
        amount = str(item.get("num") or "未知")
        choices.append({"name": item.get("seat_name"), "price": price, "availability": amount,
                        "available": amount == "有" or (amount.isdigit() and int(amount) > 0),
                        "count": int(amount) if amount.isdigit() else None})
    selected = min((item for item in choices if item["available"]), key=lambda item: item["price"], default=None)
    return {"trainNumber": row.get("start_train_code"), "origin": row.get("from_station"), "destination": row.get("to_station"),
            "departureAt": f"{row.get('start_date')}T{row.get('start_time')}:00",
            "arrivalAt": f"{row.get('arrive_date')}T{row.get('arrive_time')}:00", "seatOptions": choices, "selectedSeat": selected}


async def search_trains(origin: str, destination: str, departure: str) -> list[dict]:
    endpoint = os.getenv("TRAVEL_12306_MCP_URL")
    if not endpoint or not origin or not destination:
        return []
    date.fromisoformat(departure)
    rows = await mcp_call(endpoint, "get-tickets", {"date": departure, "fromStation": origin, "toStation": destination,
                                                    "format": "json", "limitedNum": 30})
    trains = []
    for index, row in enumerate(rows if isinstance(rows, list) else []):
        if not all(row.get(key) for key in ("start_train_code", "start_date", "arrive_date", "start_time", "arrive_time")):
            continue
        leg = _rail_leg(row)
        selected = leg["selectedSeat"]
        trains.append({"id": f"rail12306-{departure}-{index}", "provider": "12306 MCP（社区）", "trainNumber": leg["trainNumber"],
                       "origin": leg["origin"], "destination": leg["destination"], "departureAt": leg["departureAt"],
                       "arrivalAt": leg["arrivalAt"], "stops": 0, "totalPrice": selected["price"] if selected else None,
                       "currency": "CNY" if selected else None, "seatClass": selected["name"] if selected else None,
                       "seatsAvailable": selected["count"] if selected else None,
                       "seatAvailability": selected["availability"] if selected else "无可售席别", "trainSegments": [leg],
                       "priceBasis": "可售席别票价 · 以 12306 为准" if selected else "无可售席别"})
    return trains
