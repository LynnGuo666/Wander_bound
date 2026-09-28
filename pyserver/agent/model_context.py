"""Compact tool facts sent back to Step; the event trace retains the full response."""
from __future__ import annotations


def _rows(rows: list[dict], fields: tuple[str, ...], limit: int) -> list[dict]:
    return [{field: row[field] for field in fields if field in row} for row in rows[:limit]]


def result_for_model(name: str, result: dict) -> dict:
    if not result.get("ok"):
        return result
    if name == "search_transport":
        fields = ("id", "provider", "trainNumber", "flightNumber", "departureAt", "arrivalAt", "origin",
                  "destination", "totalPrice", "priceBasis", "seatAvailability", "stops")
        names = ("outboundFlights", "returnFlights", "outboundTrains", "returnTrains")
        return {"ok": True, "counts": {key: len(result.get(key) or []) for key in names},
                **{key: _rows(result.get(key) or [], fields, 8) for key in names},
                "warnings": result.get("warnings") or []}
    if name == "search_stays":
        return {"ok": True, "count": len(result.get("hotels") or []), "source": result.get("source"),
                "hotels": _rows(result.get("hotels") or [], ("id", "name", "totalPrice", "priceBasis", "currency"), 8)}
    if name == "discover_places":
        return {"ok": True, "city": result.get("city"), "count": len(result.get("places") or []),
                "places": _rows(result.get("places") or [], ("id", "name", "city", "area", "category", "duration"), 30)}
    return result
