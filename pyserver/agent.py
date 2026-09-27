"""Persistent Step Plan loop and server-owned tool execution."""
from __future__ import annotations

import json
import uuid
from datetime import date, timedelta
from typing import AsyncIterator

from . import providers, step
from .trips import TripStore, now

MAX_TURNS = 200
MAX_CALLS = 200
SYSTEM = ("你是旅行规划 Agent。直接理解用户原话，不能编造日期、地点、路线和价格。"
          "每次用户回答 ask_question 后必须先调用 set_trip_spec 增量保存答案，再问下一题。"
          "按需调用地点、交通、住宿工具。工具调用失败可根据错误重试。"
          "只使用工具返回的地点 ID 制作行程。最终用简短中文总结。")


def definition(name: str, description: str, properties: dict, required: list[str] | None = None) -> dict:
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": properties, **({"required": required} if required else {})}}}


TOOLS = {
    "set_trip_spec": definition("set_trip_spec", "增量保存已确认的行程字段，每次回答后先调用。只提交新增字段。", {
        "destination": {"type": "string"}, "originCity": {"type": "string"}, "days": {"type": "integer"},
        "startDate": {"type": "string"}, "totalBudgetCny": {"type": "number"},
        "requiredStays": {"type": "array", "items": {"type": "object", "properties": {"city": {"type": "string"},
                          "from": {"type": "string"}, "to": {"type": "string"}}}},
        "interests": {"type": "array", "items": {"type": "string"}}}),
    "ask_question": definition("ask_question", "向用户提出一个会改变行程决定的问题，提供 2–5 个选项，界面会补充其他。", {
        "question": {"type": "string"}, "options": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "label": {"type": "string"}, "description": {"type": "string"}}}}}, ["question", "options"]),
    "resolve_origin": definition("resolve_origin", "读取已确认的出发城市。", {}),
    "discover_places": definition("discover_places", "按目的地查询真实地点，返回可用于排程的 ID。", {}),
    "search_transport": definition("search_transport", "按起点、目的地和日期懒加载 12306 MCP 火车票数据。", {}),
    "search_stays": definition("search_stays", "取得住宿数据；无已认证供应商时返回空数组，不能编造酒店。", {}),
    "draft_plan": definition("draft_plan", "使用已发现的真实地点 ID 提交最终行程；不填价格。", {
        "placeIds": {"type": "array", "items": {"type": "string"}}}, ["placeIds"]),
}


def available(state: dict) -> list[dict]:
    if state.get("answerNeedsCommit"):
        return [TOOLS["set_trip_spec"]]
    if state.get("plan"):
        return []
    names = ["ask_question", "set_trip_spec"]
    if not state.get("originDone"):
        names.append("resolve_origin")
    if not state.get("placesDone"):
        names.append("discover_places")
    if state.get("placesDone") and state.get("originDone"):
        names += ["search_transport", "search_stays"]
    if state.get("placesDone") and state.get("transportDone") and state.get("staysDone"):
        names.append("draft_plan")
    return [TOOLS[name] for name in names]


def initial_state(request: dict) -> dict:
    memory = request.get("memory") or {}
    days = request.get("days")
    return {"destination": str(request.get("destination") or "").strip(), "originCity": str(request.get("originCity") or memory.get("homeCity") or "").strip(),
            "days": int(days) if days not in (None, "") else None, "startDate": str(request.get("startDate") or ""),
            "totalBudgetCny": None, "requiredStays": [], "interests": memory.get("interests") or [],
            "places": [], "trains": [], "hotels": [], "plan": None, "pendingQuestion": None,
            "originDone": False, "placesDone": False, "transportDone": False, "staysDone": False, "answerNeedsCommit": False}


def _error(code: str, message: str) -> dict:
    return {"ok": False, "code": code, "message": message}


async def execute(name: str, args: dict, state: dict, credentials: dict, request: dict) -> dict:
    if name == "set_trip_spec":
        keys = {"destination", "originCity", "days", "startDate", "totalBudgetCny", "requiredStays", "interests"}
        if not keys.intersection(args):
            return _error("empty_spec", "请提交已确认的字段")
        proposal = {key: args.get(key, state.get(key)) for key in keys}
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
            state.update({"originDone": False, "placesDone": False, "transportDone": False, "staysDone": False,
                          "places": [], "trains": [], "hotels": [], "plan": None})
        state.update(proposal)
        state["answerNeedsCommit"] = False
        return {"ok": True, **proposal}
    if name == "ask_question":
        question = str(args.get("question") or "").strip()[:240]
        options = [{"id": str(item.get("id") or "")[:40], "label": str(item.get("label") or "")[:80],
                    "description": str(item.get("description") or "")[:160]} for item in (args.get("options") or [])[:5] if isinstance(item, dict)]
        if not question or len(options) < 2 or len({item["id"] for item in options}) != len(options) or any(not item["id"] or not item["label"] for item in options):
            return _error("invalid_question", "问题需要 2–5 个互斥选项")
        state["pendingQuestion"] = {"id": str(uuid.uuid4()), "question": question, "options": options + [{"id": "other", "label": "其他", "description": "输入自己的答案"}]}
        return {"ok": True, "waitingForUser": True, "question": state["pendingQuestion"]}
    if name == "resolve_origin":
        state["originDone"] = bool(state["originCity"])
        return {"ok": state["originDone"], "originCity": state["originCity"]} if state["originDone"] else _error("missing_origin", "请先询问出发城市")
    if name == "discover_places":
        if not state["destination"]:
            return _error("missing_destination", "请先确定目的地")
        state["places"] = await providers.search_places(state["destination"], credentials.get("amap"))
        state["placesDone"] = True
        return {"ok": True, "places": [{key: item[key] for key in ("id", "name", "area", "category", "duration")} for item in state["places"]]}
    if name == "search_transport":
        if not state["originDone"] or not state["startDate"]:
            return _error("missing_transport_spec", "缺少出发城市或日期")
        state["trains"] = await providers.search_trains(state["originCity"], state["destination"], state["startDate"])
        state["transportDone"] = True
        return {"ok": True, "outboundFlights": [], "returnFlights": [], "outboundTrains": state["trains"], "returnTrains": []}
    if name == "search_stays":
        state["staysDone"] = True
        return {"ok": True, "hotels": state["hotels"], "source": "unconfigured"}
    if name == "draft_plan":
        if not state["destination"] or not state["startDate"] or not isinstance(state["days"], int):
            return _error("incomplete_spec", "先确定目的地、日期和总天数")
        ids = args.get("placeIds")
        catalog = {item["id"]: item for item in state["places"]}
        if not isinstance(ids, list) or any(item not in catalog for item in ids):
            return _error("unverified_place", "只能使用 discover_places 返回的地点 ID")
        start = date.fromisoformat(state["startDate"])
        itinerary = []
        for index in range(state["days"]):
            day = (start + timedelta(days=index)).isoformat()
            stops = [{**catalog[item], "start": f"{9 + slot * 2:02d}:00", "travelMinutes": None, "travelSource": None}
                     for slot, item in enumerate(ids[index * 3:(index + 1) * 3])]
            itinerary.append({"day": index + 1, "date": day, "title": f"{state['destination']} · 第 {index + 1} 天", "stops": stops})
        plan = {"destination": state["destination"], "originCity": state["originCity"], "startDate": state["startDate"],
                "endDate": (start + timedelta(days=state["days"] - 1)).isoformat(), "days": state["days"],
                "intro": "根据已确认的约束与已核实地点编排", "revisit": False, "skippedPlaces": [], "itinerary": itinerary,
                "stayArea": None, "flights": [], "returnFlights": [], "trains": state["trains"], "returnTrains": [], "hotels": state["hotels"],
                "attractionOffers": [], "dining": [], "groundJourneys": [], "providerStatus": {}, "transportPreference": "train",
                "hotelBrands": [], "generatedAt": now(), "locationDetected": False, "requiredStays": state["requiredStays"],
                "totalBudgetCny": state["totalBudgetCny"], "recommendedOutboundTrainId": next((item["id"] for item in state["trains"] if item["totalPrice"] is not None), None)}
        state["plan"] = plan
        return {"ok": True, "days": itinerary, "selectedPlaceIds": ids}
    return _error("unknown_tool", "未知工具")


async def run_agent(trip: dict, request: dict, credentials: dict, store: TripStore, *, answer: dict | None = None,
                    revision: str | None = None) -> AsyncIterator[dict]:
    state = trip.get("continuation", {}).get("state") if trip.get("continuation") else initial_state(request)
    if not state:
        state = initial_state(request)
    history = trip.get("continuation") or {}
    messages = history.get("messages") or [{"role": "system", "content": SYSTEM},
               {"role": "user", "content": json.dumps({"query": request.get("query"), "explicitFields": {key: request.get(key) for key in ("originCity", "destination", "days", "startDate")},
                                                   "preferences": request.get("memory") or {}}, ensure_ascii=False)}]
    turns = history.get("modelTurns", 0)
    calls = history.get("toolCalls", 0)
    usage = history.get("usage") or {"prompt_tokens": 0, "completion_tokens": 0, "reported": False}
    events = trip.get("events") or []
    def event(kind: str, **fields) -> dict:
        entry = {"sequence": len(events) + 1, "at": now(), "type": kind, **fields}
        events.append(entry)
        return {"event": "progress", "data": entry}
    if answer:
        pending = state.get("pendingQuestion") or {}
        option = next((item for item in pending.get("options", []) if item["id"] == answer.get("optionId")), None)
        if not option or pending.get("id") != answer.get("questionId"):
            yield {"event": "result", "data": {"status": 400, "error": "回答与当前问题不匹配"}}
            return
        value = str(answer.get("customText") or "").strip()[:500] if option["id"] == "other" else option["label"]
        if not value:
            yield {"event": "result", "data": {"status": 400, "error": "请填写其他答案"}}
            return
        state["pendingQuestion"] = None
        state["answerNeedsCommit"] = True
        messages.append({"role": "user", "content": json.dumps({"question": pending["question"], "answer": value,
                         "instruction": "先调用 set_trip_spec 增量写入行程记忆，成功后才可继续提问。"}, ensure_ascii=False)})
        yield event("user_answer", questionId=pending["id"], question=pending["question"], answer=value)
    elif revision:
        state["plan"] = None
        state["placesDone"] = False
        state["transportDone"] = False
        state["staysDone"] = False
        messages.append({"role": "user", "content": f"在之前的会话和行程基础上修改：{revision[:2000]}"})
        yield event("revision_requested", instruction=revision[:2000])
    else:
        yield event("run_start", model=step.MODEL, channel="step-plan", mode="model")
    error = None
    while turns < MAX_TURNS and calls < MAX_CALLS and not state.get("pendingQuestion") and not state.get("plan"):
        exposed = available(state)
        names = [item["function"]["name"] for item in exposed]
        yield event("model_turn_start", turn=turns + 1, availableTools=names,
                    input={"toolChoice": "required", "messageCount": len(messages), "latest": [{"role": item["role"], "preview": str(item.get("content") or "")[:1200]} for item in messages[-2:]]})
        completed = None
        for attempt in range(2):
            try:
                async for item in step.complete(messages, exposed, credentials["stepfun"], tool_choice="required"):
                    if item["type"] == "completion":
                        completed = item
                    else:
                        yield event(item["type"], turn=turns + 1, text=item["text"])
                break
            except Exception as exc:
                if attempt:
                    error = getattr(exc, "code", "model_error")
                    yield event("model_error", turn=turns + 1, code=error, message=str(exc), usage=getattr(exc, "usage", None))
                else:
                    yield event("model_retry", turn=turns + 1, code=getattr(exc, "code", "model_error"), attempt=2)
        if not completed:
            break
        turns += 1
        reported = completed.get("usage") or {}
        for key in ("prompt_tokens", "completion_tokens"):
            usage[key] += int(reported.get(key) or 0)
        usage["reported"] = usage["reported"] or bool(reported)
        requested = completed["message"].get("tool_calls") or []
        yield event("model_turn_end", turn=turns, requestedTools=[item["function"]["name"] for item in requested],
                    usage=reported, finishReason=completed["finishReason"], publicNote=completed["publicNote"])
        if not requested:
            error = "incomplete_plan"
            break
        messages.append(completed["message"])
        for call in requested:
            if calls >= MAX_CALLS:
                break
            calls += 1
            name = call["function"]["name"]
            try:
                args = json.loads(call["function"].get("arguments") or "{}")
                if not isinstance(args, dict):
                    raise ValueError("工具参数必须是对象")
            except (json.JSONDecodeError, ValueError):
                args = {}
                result = _error("invalid_arguments", "工具参数不是有效 JSON 对象")
            else:
                yield event("tool_start", turn=turns, source="model", tool=name, input=args)
                if name not in names:
                    result = _error("tool_not_loaded", "当前阶段未加载该工具")
                else:
                    try:
                        result = await execute(name, args, state, credentials, request)
                    except Exception as exc:
                        result = _error("tool_failed", str(exc)[:200])
            yield event("tool_end", turn=turns, source="model", tool=name, input=args, output=result, ok=result.get("ok", False), code=result.get("code", "ok"))
            if name == "set_trip_spec" and result.get("ok"):
                yield event("trip_memory_updated", turn=turns, fields=args, memory=result)
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result, ensure_ascii=False)[:20000]})
            if state.get("pendingQuestion"):
                break
    trip["events"] = events
    trip["continuation"] = {"state": state, "messages": messages, "modelTurns": turns, "toolCalls": calls, "usage": usage}
    agent_run = {"status": "waiting_for_user" if state.get("pendingQuestion") else "completed" if state.get("plan") else "degraded",
                 "model": step.MODEL, "channel": "step-plan", "modelTurns": turns, "toolCalls": calls, "usage": usage, "events": events,
                 "trace": [{"tool": item["tool"], "ok": item["ok"], "code": item["code"]} for item in events if item["type"] == "tool_end"], "warnings": []}
    if state.get("pendingQuestion"):
        result = {"status": 409, "needsInput": True, "question": state["pendingQuestion"], "sessionId": trip["id"], "tripId": trip["id"], "agentRun": agent_run}
    elif state.get("plan"):
        plan = state["plan"]
        plan["agentRun"] = agent_run
        trip["plan"] = plan
        trip["phase"] = "ready"
        trip["revisions"].append({"at": now(), "instruction": revision or request.get("query"), "plan": plan})
        result = {**plan, "tripId": trip["id"]}
    else:
        result = {"status": 502, "error": f"Step 未完成规划（{error or 'incomplete_plan'}）。请查看完整调试记录。",
                  "tripId": trip["id"], "agentRun": agent_run}
    store.save(trip)
    yield {"event": "result", "data": result}
