"""Private Spark media job endpoints."""
from __future__ import annotations

import secrets
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from ..trips import TripStore
from .store import MediaStore
from .jobs import JobStore
from .auth import require_media_auth

def router_for(trips: TripStore, media: MediaStore, jobs: JobStore) -> APIRouter:
    router = APIRouter()
    @router.post("/api/media/memories")
    async def create_memory(request: Request, payload: dict):
        require_media_auth(request)
        trip_id = payload.get("tripId")
        photo_ids = payload.get("photoIds")
        if not trips.get(trip_id) or not isinstance(photo_ids, list) or not 1 <= len(photo_ids) <= 8 or len(set(photo_ids)) != len(photo_ids) or any((media.get(item) or {}).get("tripId") != trip_id for item in photo_ids):
            raise HTTPException(400, "请选择该行程的 1–8 张不重复照片")
        try:
            job = jobs.submit("memory", {"tripId": trip_id, "photoIds": photo_ids,
                                         "title": str(payload.get("title") or "旅行回忆")[:80]})
        except ValueError as exc:
            raise HTTPException(503, str(exc)) from exc
        return JSONResponse({key: job[key] for key in ("id", "status", "backend")}, status_code=202)

    @router.post("/api/media/photos/{photo_id}/redraw")
    async def redraw(photo_id: str, request: Request, payload: dict):
        require_media_auth(request)
        if not media.get(photo_id):
            raise HTTPException(404, "照片不存在")
        prompt = str(payload.get("prompt") or "").strip()[:500]
        if not prompt:
            raise HTTPException(400, "请描述重绘效果")
        import secrets
        try:
            job = jobs.submit("edit", {"photoId": photo_id, "prompt": prompt,
                                       "seed": int(payload.get("seed")) if payload.get("seed") is not None else secrets.randbits(32)})
        except ValueError as exc:
            raise HTTPException(503, str(exc)) from exc
        return JSONResponse({key: job[key] for key in ("id", "status", "backend", "seed")}, status_code=202)

    @router.get("/api/media/edits/{job_id}")
    async def edit_status(job_id: str, request: Request):
        require_media_auth(request)
        job = jobs.get(job_id)
        if not job or job["kind"] != "edit":
            raise HTTPException(404, "任务不存在")
        return {key: job.get(key) for key in ("id", "photoId", "status", "backend", "variant", "error", "createdAt", "startedAt", "completedAt", "attempt", "progressLabel", "progressPercent")}

    @router.post("/api/media/edits/{job_id}/retry")
    async def retry_edit(job_id: str, request: Request):
        require_media_auth(request)
        job = jobs.retry(job_id)
        if not job or job["kind"] != "edit":
            raise HTTPException(404, "无法重试")
        return JSONResponse({"id": job_id, "status": job["status"], "attempt": job["attempt"]}, status_code=202)

    @router.get("/api/media/memories/{job_id}")
    async def memory_status(job_id: str, request: Request):
        require_media_auth(request)
        job = jobs.get(job_id)
        if not job or job["kind"] != "memory":
            raise HTTPException(404, "任务不存在")
        return {key: job.get(key) for key in ("id", "status", "backend", "error", "createdAt", "startedAt", "completedAt", "attempt", "completedClips", "progressLabel", "progressPercent")}

    @router.post("/api/media/memories/{job_id}/retry")
    async def retry_memory(job_id: str, request: Request):
        require_media_auth(request)
        job = jobs.retry(job_id)
        if not job or job["kind"] != "memory":
            raise HTTPException(404, "无法重试")
        return JSONResponse({"id": job_id, "status": job["status"], "attempt": job["attempt"]}, status_code=202)

    @router.get("/api/media/memories/{job_id}/video")
    async def memory_video(job_id: str, request: Request):
        require_media_auth(request)
        job = jobs.get(job_id)
        file = jobs.root / job_id / "memory.mp4"
        if not job or job["kind"] != "memory" or job["status"] != "succeeded" or not file.is_file():
            raise HTTPException(404, "视频尚未生成")
        return FileResponse(file, media_type="video/mp4")

    return router
