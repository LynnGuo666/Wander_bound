"""FastAPI entrypoint for the travel agent, trips, settings, and private photos."""
from __future__ import annotations

import hmac
import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

from .agent import run_agent
from .config import ConfigStore
from .media import MediaStore
from .providers import list_mcp_tools
from .trips import TripStore, public_trip


def create_app(*, config: ConfigStore | None = None, trips: TripStore | None = None, media: MediaStore | None = None) -> FastAPI:
    app = FastAPI(title="行驿 Travel Agent", version="2.0.0")
    config = config or ConfigStore()
    trips = trips or TripStore()
    media = media or MediaStore()

    def media_auth(request: Request):
        token = os.getenv("MEDIA_API_TOKEN", "")
        if not token:
            raise HTTPException(503, "媒体服务尚未配置访问令牌")
        if not hmac.compare_digest(request.headers.get("Authorization", ""), f"Bearer {token}"):
            raise HTTPException(401, "媒体服务需要有效令牌")

    @app.get("/api/health")
    async def health():
        keys = config.credentials()
        ota = bool(os.getenv("TRAVEL_OTA_MCP_URL"))
        return {"ok": True, "runtime": "python-fastapi", "model": {"id": "step-5-preview", "configured": bool(keys["stepfun"]), "channel": "step-plan"},
                "providers": {"amap": {"configured": bool(keys["amap"]), "label": "高德地点与路线"},
                              "dida": {"configured": bool(keys["dida"]), "label": "道旅酒店"},
                              "duffel": {"configured": bool(keys["duffel"]), "label": "Duffel 航班"},
                              "tuniu": {"configured": ota and bool(keys["tuniu"]), "label": "途牛 · OTA MCP"},
                              "flyai": {"configured": ota, "label": "飞猪 · OTA MCP"},
                              "rail12306": {"configured": bool(os.getenv("TRAVEL_12306_MCP_URL")), "label": "12306 MCP（社区）"}}}

    @app.get("/api/settings")
    async def get_settings():
        return config.public()

    @app.put("/api/settings")
    async def put_settings(patch: dict):
        try:
            return config.update(patch)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    @app.post("/api/capabilities")
    async def capabilities(payload: dict):
        keys = config.credentials(payload.get("credentials"))
        import asyncio
        ota, rail = await asyncio.gather(list_mcp_tools(os.getenv("TRAVEL_OTA_MCP_URL")),
                                         list_mcp_tools(os.getenv("TRAVEL_12306_MCP_URL")))
        dida = {"kind": "MCP", "discovery": "authentication_required" if not keys["dida"] else "unavailable", "tools": [], "metadataSource": "tools/list"}
        current = await health()
        from .trips import now
        return {"checkedAt": now(), "providers": current["providers"], "connections": {"ota": ota, "rail": rail, "dida": dida}}

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
        async def frames():
            async for item in run_agent(trip, request, keys, trips, answer=answer, revision=revision):
                yield f"event: {item['event']}\ndata: {json.dumps(item['data'], ensure_ascii=False)}\n\n"
        if stream:
            return StreamingResponse(frames(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
        result = None
        async for item in run_agent(trip, request, keys, trips, answer=answer, revision=revision):
            if item["event"] == "result":
                result = item["data"]
        return JSONResponse(result, status_code=result.get("status", 200))

    @app.post("/api/plan")
    async def plan(payload: dict):
        return await plan_request(payload, stream=False)

    @app.post("/api/plan/stream")
    async def plan_stream(payload: dict):
        return await plan_request(payload, stream=True)

    @app.get("/api/trips")
    async def list_trips():
        return {"trips": trips.list()}

    @app.get("/api/trips/{trip_id}")
    async def get_trip(trip_id: str):
        trip = trips.get(trip_id)
        if not trip:
            raise HTTPException(404, "行程不存在")
        return {**public_trip(trip, detail=True), "photos": media.list(trip_id)}

    @app.get("/api/trips/{trip_id}/photos/{photo_id}")
    async def trip_photo(trip_id: str, photo_id: str, variant: str = "original"):
        photo = media.get(photo_id)
        if not trips.get(trip_id) or not photo or photo["tripId"] != trip_id:
            raise HTTPException(404, "照片不存在")
        data = media.bytes(photo_id, variant)
        if not data:
            raise HTTPException(404, "照片版本不存在")
        return Response(data, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})

    @app.get("/api/media/health")
    async def media_health(request: Request):
        media_auth(request)
        return {"ok": True, "storage": "private-local", "imageProcessor": "Pillow",
                "imageEditBackend": "unconfigured", "videoBackend": "unconfigured"}

    @app.post("/api/media/photos")
    async def upload_photo(request: Request):
        media_auth(request)
        trip_id = request.headers.get("X-Trip-Id", "")
        if not trips.get(trip_id):
            raise HTTPException(404, "行程不存在；请先在规划会话中创建行程")
        if request.headers.get("content-type") != "image/jpeg":
            raise HTTPException(415, "仅接收 JPEG")
        try:
            photo = media.add(await request.body(), trip_id, request.headers.get("X-Captured-Day"))
        except (ValueError, OSError) as exc:
            raise HTTPException(400, str(exc)) from exc
        return JSONResponse(photo, status_code=201)

    @app.get("/api/media/photos")
    async def list_photos(request: Request, tripId: str):
        media_auth(request)
        if not trips.get(tripId):
            raise HTTPException(404, "行程不存在")
        return {"photos": media.list(tripId)}

    @app.get("/api/media/photos/{photo_id}")
    async def photo_bytes(photo_id: str, request: Request, variant: str = "original"):
        media_auth(request)
        data = media.bytes(photo_id, variant)
        if not data:
            raise HTTPException(404, "照片不存在")
        return Response(data, media_type="image/jpeg")

    @app.post("/api/media/photos/{photo_id}/enhance")
    async def enhance_photo(photo_id: str, request: Request, payload: dict):
        media_auth(request)
        try:
            photo = media.enhance(photo_id, payload.get("preset"))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if not photo:
            raise HTTPException(404, "照片不存在")
        return photo

    @app.post("/api/media/memories")
    async def memory_unavailable(request: Request):
        media_auth(request)
        return JSONResponse({"error": "本地未配置 MiniMax H3 工作流"}, status_code=503)

    @app.post("/api/media/photos/{photo_id}/redraw")
    async def redraw_unavailable(photo_id: str, request: Request):
        media_auth(request)
        return JSONResponse({"error": "本地未配置 Qwen Image 工作流"}, status_code=503)

    @app.get("/")
    async def index():
        file = Path("dist/index.html")
        if not file.exists():
            raise HTTPException(404, "前端尚未构建；运行 npm run build")
        return FileResponse(file)

    @app.get("/{asset_path:path}")
    async def assets(asset_path: str):
        root = Path("dist").resolve()
        file = (root / asset_path).resolve()
        if not file.is_relative_to(root) or not file.is_file():
            raise HTTPException(404, "文件不存在")
        return FileResponse(file)

    return app


app = create_app()
