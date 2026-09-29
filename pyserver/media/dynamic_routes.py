"""Authenticated source settlement for dynamic-photo jobs."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from ..trips import TripStore
from .auth import require_media_auth
from .contracts import ContractError
from .dynamic_sources import DynamicPhotoSources


def router_for(trips: TripStore, sources: DynamicPhotoSources) -> APIRouter:
    router = APIRouter()

    @router.get("/api/media/trips/{trip_id}/dynamic-photo/developments")
    async def development_attempts(trip_id: str, request: Request):
        require_media_auth(request)
        if not trips.get(trip_id):
            raise HTTPException(404, {"code": "TRIP_NOT_FOUND", "message": "行程不存在"})
        return {"attempts": sources.list_developments(trip_id)}

    @router.post("/api/media/trips/{trip_id}/dynamic-photo/developments/{marker_id}/resolve")
    async def resolve_development(trip_id: str, marker_id: str, request: Request, payload: dict):
        require_media_auth(request)
        if not trips.get(trip_id):
            raise HTTPException(404, {"code": "TRIP_NOT_FOUND", "message": "行程不存在"})
        if not isinstance(payload, dict) or set(payload) != {"batchId", "reason"}:
            raise HTTPException(400, {"code": "REQUEST_INVALID", "message": "恢复请求字段无效"})
        try:
            return sources.resolve_interrupted(trip_id, marker_id, payload["batchId"], payload["reason"])
        except ContractError as exc:
            raise HTTPException(exc.status_code, exc.body()) from exc

    @router.post("/api/media/trips/{trip_id}/dynamic-photo/settle")
    async def settle(trip_id: str, request: Request, payload: dict):
        require_media_auth(request)
        if not trips.get(trip_id):
            raise HTTPException(404, {"code": "TRIP_NOT_FOUND", "message": "行程不存在"})
        try:
            job = sources.settle(trip_id, payload)
        except ContractError as exc:
            raise HTTPException(exc.status_code, exc.body()) from exc
        return JSONResponse({key: value for key, value in job.items() if key != "ownerId"}, status_code=202)

    @router.get("/api/media/dynamic-photo/jobs/{job_id}")
    async def status(job_id: str, request: Request):
        require_media_auth(request)
        job = sources.get(job_id)
        if not job or not trips.get(job["tripId"]):
            raise HTTPException(404, {"code": "JOB_NOT_FOUND", "message": "动态照片任务不存在"})
        return {key: value for key, value in job.items() if key != "ownerId"}

    return router
