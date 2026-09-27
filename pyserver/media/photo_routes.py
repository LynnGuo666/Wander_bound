"""Private Spark media photo endpoints."""
from __future__ import annotations

import secrets
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from ..trips import TripStore
from .store import MediaStore
from .comfy import ComfyClient
from .auth import require_media_auth

def router_for(trips: TripStore, media: MediaStore, image_client: ComfyClient | None, video_client: ComfyClient | None) -> APIRouter:
    router = APIRouter()
    @router.get("/api/media/health")
    async def media_health(request: Request):
        require_media_auth(request)
        return {"ok": True, "storage": "private-local", "imageProcessor": "Pillow",
                "imageEditBackend": "dgx-spark-qwen-image-2.1" if image_client and await image_client.probe() else "unconfigured",
                "videoBackend": "dgx-spark-minimax-h3" if video_client and await video_client.probe() else "unconfigured"}

    @router.post("/api/media/photos")
    async def upload_photo(request: Request):
        require_media_auth(request)
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

    @router.get("/api/media/photos")
    async def list_photos(request: Request, tripId: str):
        require_media_auth(request)
        if not trips.get(tripId):
            raise HTTPException(404, "行程不存在")
        return {"photos": media.list(tripId)}

    @router.get("/api/media/photos/{photo_id}")
    async def photo_bytes(photo_id: str, request: Request, variant: str = "original"):
        require_media_auth(request)
        data = media.bytes(photo_id, variant)
        if not data:
            raise HTTPException(404, "照片不存在")
        return Response(data, media_type="image/jpeg")

    @router.post("/api/media/photos/{photo_id}/enhance")
    async def enhance_photo(photo_id: str, request: Request, payload: dict):
        require_media_auth(request)
        try:
            photo = media.enhance(photo_id, payload.get("preset"))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if not photo:
            raise HTTPException(404, "照片不存在")
        return photo

    return router
