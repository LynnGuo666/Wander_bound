"""Trip constraints, clarification, and origin confirmation."""
from __future__ import annotations

import uuid
from datetime import date
from .state import _error

async def set_trip_spec(args: dict, state: dict, request: dict) -> dict:
    keys = {"destination", "originCity", "days", "startDate", "totalBudgetCny", "requiredStays", "interests", "preferences"}
    if not keys.intersection(args):
        return _error("empty_spec", "请提交已确认的字段")
    proposal = {key: args.get(key, state.get(key)) for key in keys}
    if "preferences" in args:
        if not isinstance(args["preferences"], dict):
            return _error("invalid_preferences", "偏好必须是对象")
        proposal["preferences"] = {**(state.get("preferences") or {}), **args["preferences"]}
    if not state.get("answerNeedsCommit"):
        for field in ("destination", "originCity", "startDate"):
            if request.get(field):
                proposal[field] = request[field]
        if request.get("days") not in (None, ""):
            proposal["days"] = int(request["days"])
    try:
        if proposal["days"] is not None and not 1 <= int(proposal["days"]) <= 21:
            raise ValueError("天数须为 1–21")
        if proposal["startDate"]:
            date.fromisoformat(proposal["startDate"])
        if proposal["totalBudgetCny"] is not None and not 0 <= float(proposal["totalBudgetCny"]) <= 1_000_000:
            raise ValueError("总预算无效")
        for stay in proposal["requiredStays"] or []:
            date.fromisoformat(stay["from"]); date.fromisoformat(stay["to"])
    except (ValueError, TypeError, KeyError) as exc:
        return _error("invalid_spec", str(exc))
    changed = any(proposal[key] != state.get(key) for key in ("destination", "originCity", "startDate", "days"))
    if changed:
        state.update({"originDone": False, "placesDone": False, "transportDone": False, "staysDone": False, "enrichmentDone": False,
                      "places": [], "discoveredCities": [], "trains": [], "returnTrains": [], "flights": [], "returnFlights": [],
                      "providerStatus": {}, "hotels": [], "plan": None})
    state.update(proposal)
    state["originDone"] = bool(state["originCity"])
    state["answerNeedsCommit"] = False
    return {"ok": True, **proposal}

async def ask_question(args: dict, state: dict) -> dict:
    question = str(args.get("question") or "").strip()[:240]
    options = [{"id": str(item.get("id") or "")[:40], "label": str(item.get("label") or "")[:80],
                "description": str(item.get("description") or "")[:160]} for item in (args.get("options") or [])[:5] if isinstance(item, dict)]
    if not question or len(options) < 2 or len({item["id"] for item in options}) != len(options) or any(not item["id"] or not item["label"] for item in options):
        return _error("invalid_question", "问题需要 2–5 个互斥选项")
    state["pendingQuestion"] = {"id": str(uuid.uuid4()), "question": question, "options": options + [{"id": "other", "label": "其他", "description": "输入自己的答案"}]}
    return {"ok": True, "waitingForUser": True, "question": state["pendingQuestion"]}

async def resolve_origin(state: dict) -> dict:
    state["originDone"] = bool(state["originCity"])
    return {"ok": state["originDone"], "originCity": state["originCity"]} if state["originDone"] else _error("missing_origin", "请先询问出发城市")
