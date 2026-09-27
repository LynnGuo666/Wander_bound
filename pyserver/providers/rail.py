"""12306 ticket lookup and normalized rail offers."""
from __future__ import annotations

import os
import asyncio
from datetime import date
from .mcp import mcp_call

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
    args = {"date": departure, "fromStation": origin, "toStation": destination, "format": "json"}
    direct, transfer = await asyncio.gather(
        mcp_call(endpoint, "get-tickets", {**args, "limitedNum": 30}),
        mcp_call(endpoint, "get-interline-tickets", {**args, "limitedNum": 10}), return_exceptions=True)
    if isinstance(direct, Exception) and isinstance(transfer, Exception):
        raise direct
    trains = []
    for index, row in enumerate(direct if isinstance(direct, list) else []):
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
    for index, row in enumerate(transfer if isinstance(transfer, list) else []):
        raw_legs = row.get("ticketList") or []
        if len(raw_legs) < 2:
            continue
        legs = [_rail_leg(item) for item in raw_legs]
        if any("None" in leg["departureAt"] or "None" in leg["arrivalAt"] for leg in legs):
            continue
        selected = [leg["selectedSeat"] for leg in legs]
        priced = all(selected)
        trains.append({"id": f"rail12306-transfer-{departure}-{index}", "provider": "12306 MCP（社区）",
                       "trainNumber": " → ".join(str(leg["trainNumber"]) for leg in legs),
                       "origin": legs[0]["origin"], "destination": legs[-1]["destination"],
                       "departureAt": legs[0]["departureAt"], "arrivalAt": legs[-1]["arrivalAt"],
                       "stops": len(legs) - 1, "totalPrice": sum(item["price"] for item in selected) if priced else None,
                       "currency": "CNY" if priced else None, "trainSegments": legs,
                       "seatClass": " / ".join(item["name"] for item in selected) if priced else None,
                       "seatsAvailable": min(item["count"] for item in selected) if priced and all(item["count"] is not None for item in selected) else None,
                       "seatAvailability": " / ".join(item["availability"] for item in selected) if priced else "部分航段无可售席别",
                       "transfer": {"station": row.get("middle_station_name"), "sameStation": row.get("same_station") is True,
                                    "waitTime": row.get("wait_time")}, "priceBasis": "各段可售席别之和 · 以 12306 为准" if priced else "部分航段无可售席别"})
    return trains
