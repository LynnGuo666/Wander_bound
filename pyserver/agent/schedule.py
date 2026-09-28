"""Travel-day windows derived from supplier departure and arrival times."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta


def _timestamp(offer: dict, field: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(offer.get(field) or ""))
    except ValueError:
        return None


def _mode(state: dict) -> str:
    preference = str((state.get("preferences") or {}).get("transportPreference") or
                     (state.get("preferences") or {}).get("transport") or "").lower()
    if any(value in preference for value in ("高铁", "动车", "火车", "train", "rail")):
        return "train"
    if any(value in preference for value in ("飞机", "航班", "flight", "air")):
        return "flight"
    return "train" if state.get("trains") else "flight"


def select_outbound(state: dict) -> dict | None:
    mode = _mode(state)
    offers = state.get("trains" if mode == "train" else "flights") or []
    if not offers:
        offers = state.get("flights" if mode == "train" else "trains") or []
    valid = [item for item in offers if _timestamp(item, "departureAt") and _timestamp(item, "arrivalAt")]
    if not valid:
        return None
    preference = str((state.get("preferences") or {}).get("transportPreference") or "").lower()
    high_speed = mode == "train" and not any(value in preference for value in ("普速", "普通列车", "slow"))
    def score(item: dict):
        dep = _timestamp(item, "departureAt")
        arr = _timestamp(item, "arrivalAt")
        price = item.get("totalPrice")
        night = 10_000 if dep.hour < 6 or dep.hour >= 22 else 0
        late = 1_000 if arr.hour >= 21 else 0
        slow = 2_000 if high_speed and mode == "train" and not str(item.get("trainNumber") or "").startswith(("G", "D", "C")) else 0
        unknown = 2_000 if price is None else 0
        return night + late + slow + unknown + (float(price) if price is not None else 0) + arr.hour * 5 + arr.minute / 12
    return min(valid, key=score)


def select_return(state: dict) -> dict | None:
    mode = _mode(state)
    offers = state.get("returnTrains" if mode == "train" else "returnFlights") or []
    if not offers:
        offers = state.get("returnFlights" if mode == "train" else "returnTrains") or []
    valid = [item for item in offers if _timestamp(item, "departureAt")]
    if not valid:
        return None
    daytime = [item for item in valid if 8 <= _timestamp(item, "departureAt").hour < 22]
    priced = [item for item in daytime if item.get("totalPrice") is not None]
    choices = priced or daytime or valid
    return max(choices, key=lambda item: _timestamp(item, "departureAt"))


def day_windows(state: dict) -> dict[str, tuple[datetime, datetime]]:
    start = date.fromisoformat(state["startDate"])
    end = start + timedelta(days=state["days"] - 1)
    outbound_offer = select_outbound(state)
    return_offer = select_return(state)
    outbound = _timestamp(outbound_offer, "arrivalAt") if outbound_offer else None
    inbound = _timestamp(return_offer, "departureAt") if return_offer else None
    outbound_mode = "train" if outbound_offer in (state.get("trains") or []) else "flight"
    return_mode = "train" if return_offer in (state.get("returnTrains") or []) else "flight"
    windows = {}
    for index in range(state["days"]):
        day = start + timedelta(days=index)
        lower = datetime.combine(day, time(9))
        upper = datetime.combine(day, time(21))
        if outbound:
            lower = max(lower, outbound + timedelta(minutes=(20 if outbound_mode == "train" else 45) + 25))
        if inbound:
            upper = min(upper, inbound - timedelta(minutes=45 if return_mode == "train" else 120))
        if upper - lower >= timedelta(hours=2):
            windows[day.isoformat()] = (lower, upper)
    return windows


def capacity(window: tuple[datetime, datetime]) -> int:
    return int((window[1] - window[0]).total_seconds() // 7200)
