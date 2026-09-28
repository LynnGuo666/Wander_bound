"""Planning and event stream endpoints."""
from __future__ import annotations

import json
import copy
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from ..agent import run_agent
from ..settings import ConfigStore
from ..trips import TripStore, now

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

    @router.post("/api/trips/{trip_id}/recalculate")
    async def recalculate(trip_id: str, payload: dict):
        from ..providers import amap
        from ..providers.coordinates import add_map_coordinates
        from ..agent.timeline import build_timeline
        trip = trips.get(trip_id)
        if not trip or not trip.get("plan"):
            raise HTTPException(404, "行程不存在")
        plan = copy.deepcopy(trip["plan"])
        for field, collection in (("outboundFlightId", "flights"), ("outboundTrainId", "trains"),
                                  ("returnFlightId", "returnFlights"), ("returnTrainId", "returnTrains")):
            if field not in payload:
                continue
            if payload[field] not in {item.get("id") for item in plan.get(collection) or []}:
                raise HTTPException(400, f"{field} 必须来自现有已核实班次")
            target = "recommended" + field[0].upper() + field[1:]
            plan[target] = payload[field]
            opposite_field = "recommended" + ("Outbound" if "outbound" in field else "Return") + ("TrainId" if "Flight" in field else "FlightId")
            plan[opposite_field] = None
            if field.startswith("outbound"):
                plan["selectedTransportMode"] = "flight" if "Flight" in field else "train"
        if "hotelId" in payload:
            hotel = next((item for item in plan.get("hotels") or [] if item.get("id") == payload["hotelId"]), None)
            if not hotel:
                raise HTTPException(400, "酒店必须来自已核实候选")
            key = config.credentials(None).get("amap")
            point = await amap.hotel_point(hotel["name"], plan["destination"], key) if key else None
            plan["stayArea"] = point or {**(plan.get("stayArea") or {}), "name": f"{hotel['name']}（具体位置待核）", "approximate": True}
            plan["selectedHotelId"] = hotel["id"]
        if "dayOrders" in payload:
            orders = payload["dayOrders"]
            if not isinstance(orders, dict):
                raise HTTPException(400, "dayOrders 必须按日期指定地点 ID")
            for day in plan["itinerary"]:
                if day["date"] in orders:
                    ids = orders[day["date"]]
                    if not isinstance(ids, list) or set(ids) != {stop["id"] for stop in day["stops"]} or len(ids) != len(day["stops"]):
                        raise HTTPException(400, "地点顺序必须恰好包含该天全部地点")
                    by_id = {stop["id"]: stop for stop in day["stops"]}
                    day["stops"] = [by_id[item] for item in ids]
        if "durations" in payload:
            durations = payload["durations"]
            if not isinstance(durations, dict):
                raise HTTPException(400, "durations 必须是地点 ID 到分钟数的映射")
            for day in plan["itinerary"]:
                for stop in day["stops"]:
                    if stop["id"] in durations:
                        value = durations[stop["id"]]
                        if type(value) is not int or not 30 <= value <= 360:
                            raise HTTPException(400, "游玩时长须为 30–360 分钟")
                        stop["duration"] = value
        if "timeBuffers" in payload:
            if not isinstance(payload["timeBuffers"], dict):
                raise HTTPException(400, "timeBuffers 必须是对象")
            plan["timeBuffers"] = payload["timeBuffers"]
        for day in plan["itinerary"]:
            for stop in day["stops"]:
                stop["travelMinutes"] = None
                stop["travelSource"] = None
        key = config.credentials(None).get("amap")
        plan["groundJourneys"] = []
        if key:
            plan.update(await amap.enrich_routes(plan, key))
        build_timeline(plan)
        add_map_coordinates(plan)
        trip["plan"] = plan
        trip.setdefault("revisions", []).append({"at": now(),
                                                    "instruction": "调整时间与路线", "plan": copy.deepcopy(plan)})
        trips.save(trip)
        return {**plan, "tripId": trip_id}

    return router
