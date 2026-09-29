"""Private Spark media photo endpoints."""
from __future__ import annotations

import tempfile
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from ..trips import TripStore
from .store import MediaStore
from .comfy import ComfyClient
from ..inference.controller import ModelController
from .auth import require_media_auth
from . import images
from .develop import suggest as suggest_development, review as review_development
from .vision import vision_base_url, vision_model
from .mcp_images import MCPImagesClient
from .dynamic_sources import DynamicPhotoSources
from .contracts import ContractError

async def _render_development(media: MediaStore, photo_id: str, settings: dict) -> bytes:
    normalized = images.normalize_develop(settings)
    source = media.bytes(photo_id)
    photo = media.get(photo_id)
    if source is None or photo is None:
        raise FileNotFoundError("照片不存在")
    media.photos_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    source_path = media.photos_dir / f"{photo_id}.jpg"
    with tempfile.TemporaryDirectory(prefix="develop-", dir=media.photos_dir) as temporary:
        destination = Path(temporary) / "adjusted.jpg"
        width, height = photo["width"], photo["height"]
        result = await MCPImagesClient().develop(source_path, destination, normalized, (width, height))
    return images.finish_local_curves(result, normalized)

def router_for(trips: TripStore, media: MediaStore, image_client: ComfyClient | None,
               video_client: ComfyClient | None, controller: ModelController) -> APIRouter:
    router = APIRouter()
    dynamic_sources = DynamicPhotoSources(media)
    def selected_photo(photo_id: str) -> dict:
        photo = media.get(photo_id)
        if not photo or media.bytes(photo_id) is None:
            raise HTTPException(404, "照片不存在")
        if not media.is_selected(photo):
            raise HTTPException(409, "照片尚未由优选模块提交，不能精修")
        return photo

    @router.get("/api/media/trips/{trip_id}/selected-photos")
    async def get_selected_photos(trip_id: str, request: Request):
        require_media_auth(request)
        if not trips.get(trip_id):
            raise HTTPException(404, "行程不存在")
        selected = media.selected(trip_id)
        return {**selected, "photos": [media.public_photo(photo) for photo in selected["photos"]]}

    @router.put("/api/media/trips/{trip_id}/selected-photos")
    async def put_selected_photos(trip_id: str, request: Request, payload: dict):
        require_media_auth(request)
        if not trips.get(trip_id):
            raise HTTPException(404, "行程不存在")
        try:
            selected = media.set_selected(trip_id, payload)
            return {**selected, "photos": [media.public_photo(photo) for photo in selected["photos"]]}
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.get("/api/media/health")
    async def media_health(request: Request):
        require_media_auth(request)
        model_status = await controller.status()
        by_id = {item["id"]: item["state"] for item in model_status["models"]}
        return {"ok": True, "storage": "private-local", "imageProcessor": "Pillow",
                "photoDevelopBackend": "mcp_images" if MCPImagesClient().configured else "unconfigured",
                "visionModel": vision_model(),
                "visionEndpoint": vision_base_url(),
                "imageEditBackend": "dgx-spark-qwen-image-2.1" if image_client and (await image_client.probe() or by_id.get("image") == "stopped_on_demand") else "unconfigured",
                "videoBackend": "dgx-spark-minimax-h3" if video_client and (await video_client.probe() or by_id.get("video") == "stopped_on_demand") else "unconfigured"}

    @router.post("/api/media/photos")
    async def upload_photo(request: Request):
        require_media_auth(request)
        trip_id = request.headers.get("X-Trip-Id", "")
        if not trips.get(trip_id):
            raise HTTPException(404, "行程不存在；请先在规划会话中创建行程")
        if request.headers.get("content-type") != "image/jpeg":
            raise HTTPException(415, "仅接收 JPEG")
        try:
            photo = media.add(await request.body(), trip_id, request.headers.get("X-Captured-Day"),
                              request.headers.get("X-Client-Asset-Key"))
        except (ValueError, OSError) as exc:
            raise HTTPException(400, str(exc)) from exc
        return JSONResponse(media.public_photo(photo), status_code=201)

    @router.get("/api/media/photos")
    async def list_photos(request: Request, tripId: str):
        require_media_auth(request)
        if not trips.get(tripId):
            raise HTTPException(404, "行程不存在")
        return {"photos": [media.public_photo(photo) for photo in media.list(tripId)]}

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
        return media.public_photo(photo)

    @router.post("/api/media/photos/{photo_id}/develop/suggest")
    async def develop_suggest(photo_id: str, request: Request):
        require_media_auth(request)
        photo = selected_photo(photo_id)
        source = media.bytes(photo_id)
        try:
            result = await suggest_development(source)
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc
        return {**result, "events": [
            {"step": "DGX 视觉分析", "status": "completed", "detail": result["model"]},
            {"step": "参数范围校验", "status": "completed", "detail": "裁切与 7 项调整均通过边界检查"},
        ]}

    @router.post("/api/media/photos/{photo_id}/develop/preview")
    async def develop_preview(photo_id: str, request: Request, payload: dict):
        require_media_auth(request)
        selected_photo(photo_id)
        source = media.bytes(photo_id)
        try:
            rendered = await _render_development(media, photo_id, payload.get("params") or {})
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except (ValueError, OSError, RuntimeError) as exc:
            if isinstance(exc, RuntimeError):
                raise HTTPException(503, str(exc)) from exc
            raise HTTPException(400, str(exc)) from exc
        return Response(rendered, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})

    @router.post("/api/media/photos/{photo_id}/develop/save")
    async def develop_save(photo_id: str, request: Request, payload: dict):
        require_media_auth(request)
        photo = selected_photo(photo_id)
        try:
            marker_id, batch_id = dynamic_sources.mark_development_started(photo["tripId"], photo_id)
        except ContractError as exc:
            raise HTTPException(exc.status_code, exc.body()) from exc
        try:
            source = media.bytes(photo_id)
            params = images.normalize_develop(payload.get("params") or {})
            rendered = await _render_development(media, photo_id, params)
            result = media.save_develop(photo_id, rendered, params, payload.get("note", ""),
                                        expected_batch_id=batch_id)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except (ValueError, OSError, RuntimeError) as exc:
            if isinstance(exc, RuntimeError):
                raise HTTPException(503, str(exc)) from exc
            raise HTTPException(400, str(exc)) from exc
        finally:
            dynamic_sources.mark_development_finished(photo["tripId"], marker_id)
        if result is None:
            raise HTTPException(409, "照片不再属于当前精选清单")
        return result

    @router.post("/api/media/photos/{photo_id}/develop/review")
    async def develop_review(photo_id: str, request: Request, payload: dict):
        require_media_auth(request)
        selected_photo(photo_id)
        source = media.bytes(photo_id)
        try:
            params = images.normalize_develop(payload.get("params") or {})
            edited = await _render_development(media, photo_id, params)
            return await review_development(source, edited, params)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except (OSError, RuntimeError) as exc:
            raise HTTPException(503, str(exc)) from exc

    return router
