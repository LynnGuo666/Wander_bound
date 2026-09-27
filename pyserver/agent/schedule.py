"""Travel-day windows derived from supplier departure and arrival times."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta


def _timestamp(offer: dict, field: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(offer.get(field) or ""))
    except ValueError:
        return None


def _choice(offers: list[dict], field: str, earliest: bool) -> datetime | None:
    priced = [item for item in offers if item.get("totalPrice") is not None]
    items = priced or offers
    times = [value for item in items if (value := _timestamp(item, field)) is not None]
    return (min(times) if earliest else max(times)) if times else None


def day_windows(state: dict) -> dict[str, tuple[datetime, datetime]]:
    start = date.fromisoformat(state["startDate"])
    end = start + timedelta(days=state["days"] - 1)
    outbound = _choice([*(state.get("flights") or []), *(state.get("trains") or [])], "arrivalAt", True)
    inbound = _choice([*(state.get("returnFlights") or []), *(state.get("returnTrains") or [])], "departureAt", False)
    windows = {}
    for index in range(state["days"]):
        day = start + timedelta(days=index)
        lower = datetime.combine(day, time(9))
        upper = datetime.combine(day, time(21))
        if outbound:
            lower = max(lower, outbound + timedelta(hours=1))
        if inbound:
            upper = min(upper, inbound - timedelta(hours=1))
        if upper - lower >= timedelta(hours=2):
            windows[day.isoformat()] = (lower, upper)
    return windows


def capacity(window: tuple[datetime, datetime]) -> int:
    return int((window[1] - window[0]).total_seconds() // 7200)
