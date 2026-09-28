"""Trip timestamps and public read models."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

def now() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()


def public_trip(trip: dict, detail: bool = False) -> dict:
    result = {key: value for key, value in trip.items() if key not in {"continuation", "request", "ownerId"} and (detail or key not in {"events", "revisions"})}
    plan = trip.get("plan") or {}
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    result["status"] = "ended" if trip.get("kind") == "history" and (trip.get("history") or {}).get("status") == "confirmed" else "in_progress" if trip.get("kind") == "history" else "ended" if plan.get("endDate") and today > plan["endDate"] else "in_progress" if plan.get("startDate") and today >= plan["startDate"] else "not_started"
    if detail:
        result["pendingQuestion"] = (trip.get("continuation") or {}).get("state", {}).get("pendingQuestion")
    return result
