"""Conversation state initialization and tool errors."""
from __future__ import annotations

def initial_state(request: dict) -> dict:
    memory = request.get("memory") or {}
    days = request.get("days")
    return {"destination": str(request.get("destination") or "").strip(), "originCity": str(request.get("originCity") or memory.get("homeCity") or "").strip(),
            "days": int(days) if days not in (None, "") else None, "startDate": str(request.get("startDate") or ""),
            "totalBudgetCny": None, "requiredStays": [], "request": {"location": request.get("location")}, "interests": memory.get("interests") or [],
            "preferences": memory.get("preferences") or {},
            "places": [], "discoveredCities": [], "trains": [], "returnTrains": [], "flights": [], "returnFlights": [],
            "providerStatus": {}, "hotels": [], "plan": None, "pendingQuestion": None,
            "originDone": bool(request.get("originCity") or memory.get("homeCity")), "placesDone": False, "transportDone": False, "staysDone": False,
            "enrichmentDone": False, "answerNeedsCommit": False}


def _error(code: str, message: str) -> dict:
    return {"ok": False, "code": code, "message": message}
