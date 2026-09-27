"""Persistent Step Plan loop. Tool definitions and handlers live in agent_tools."""
from __future__ import annotations

import json
from typing import AsyncIterator

from . import step
from .catalog import MAX_TURNS, MAX_CALLS, available, SYSTEM
from .handlers import execute
from .state import initial_state, _error
from .fallback import complete_with_tools
from ..trips import TripStore, now


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
    empty_turns = 0
    while turns < MAX_TURNS and calls < MAX_CALLS and not state.get("pendingQuestion") and not state.get("plan"):
        exposed = available(state)
        names = [item["function"]["name"] for item in exposed]
        yield event("model_turn_start", turn=turns + 1, availableTools=names,
                    input={"messageCount": len(messages), "latest": [{"role": item["role"], "preview": str(item.get("content") or "")[:1200]} for item in messages[-2:]]})
        completed = None
        for attempt in range(2):
            try:
                async for item in step.complete(messages, exposed, credentials["stepfun"]):
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
            empty_turns += 1
            if empty_turns >= 3:
                error = "incomplete_plan"
                break
            yield event("model_continuation", turn=turns, reason="tool_call_required", attempt=empty_turns)
            messages.append({"role": "user", "content": "规划尚未由工具完成。请继续调用当前可用工具；只有 draft_plan 成功后才能结束。若工具失败，请依据返回的错误重试。"})
            continue
        empty_turns = 0
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
    used_fallback = False
    if error and not state.get("plan") and not state.get("pendingQuestion"):
        yield event("fallback_start", reason=error)
        async for phase, name, args, result in complete_with_tools(state, credentials, request):
            used_fallback = True
            if phase == "start":
                yield event("tool_start", turn=turns, source="server_fallback", tool=name, input=args)
            else:
                yield event("tool_end", turn=turns, source="server_fallback", tool=name, input=args,
                            output=result, ok=result.get("ok", False), code=result.get("code", "ok"))
        if state.get("plan"):
            yield event("fallback_end", status="completed")
    trip["events"] = events
    trip["continuation"] = {"state": state, "messages": messages, "modelTurns": turns, "toolCalls": calls, "usage": usage}
    agent_run = {"status": "waiting_for_user" if state.get("pendingQuestion") else "degraded" if used_fallback else "completed" if state.get("plan") else "degraded",
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
