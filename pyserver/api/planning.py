"""Planning and event stream endpoints."""
from __future__ import annotations

import json
from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse
from ..agent import run_agent
from ..settings import ConfigStore
from ..trips import TripStore

def router_for(config: ConfigStore, trips: TripStore) -> APIRouter:
    router = APIRouter()
    async def plan_request(payload: dict, *, stream: bool):
        if not isinstance(payload, dict):
            return JSONResponse({"error": "请求必须是 JSON 对象"}, status_code=400)
        answer = payload.get("answer") if payload.get("sessionId") else None
        revision = str(payload.get("query") or "").strip() if payload.get("tripId") and not answer else None
        if payload.get("sessionId"):
            trip = trips.get(str(payload["sessionId"]))
            if not trip or not trip.get("continuation", {}).get("state", {}).get("pendingQuestion"):
                return JSONResponse({"error": "问答会话不存在或已结束"}, status_code=410)
            if not isinstance(answer, dict):
                return JSONResponse({"error": "缺少问题回答"}, status_code=400)
        elif payload.get("tripId"):
            trip = trips.get(str(payload["tripId"]))
            if not trip:
                return JSONResponse({"error": "行程不存在"}, status_code=404)
            if not revision:
                return JSONResponse({"error": "请填写修改要求"}, status_code=400)
            if trip.get("continuation", {}).get("state", {}).get("pendingQuestion"):
                return JSONResponse({"error": "请先回答当前问题"}, status_code=409)
        else:
            clean = {key: value for key, value in payload.items() if key not in {"credentials", "sessionId", "tripId", "answer"}}
            trip = trips.create(clean)
        keys = config.credentials(payload.get("credentials"))
        if not keys["stepfun"]:
            return JSONResponse({"error": "请先在设置页配置 Step Plan 密钥", "tripId": trip["id"]}, status_code=503)
        request = trip["request"]
        priorities = config.read()["priorities"]
        async def frames():
            async for item in run_agent(trip, request, keys, trips, answer=answer, revision=revision, priorities=priorities):
                yield f"event: {item['event']}\ndata: {json.dumps(item['data'], ensure_ascii=False)}\n\n"
        if stream:
            return StreamingResponse(frames(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
        result = None
        async for item in run_agent(trip, request, keys, trips, answer=answer, revision=revision, priorities=priorities):
            if item["event"] == "result":
                result = item["data"]
        return JSONResponse(result, status_code=result.get("status", 200))

    @router.post("/api/plan")
    async def plan(payload: dict):
        return await plan_request(payload, stream=False)

    @router.post("/api/plan/stream")
    async def plan_stream(payload: dict):
        return await plan_request(payload, stream=True)

    return router
