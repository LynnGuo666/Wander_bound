"""Private batch-analysis HTTP contract."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from ..trips import TripStore
from .analysis_jobs import AnalysisJobs
from .auth import require_media_auth


def router_for(trips: TripStore, jobs: AnalysisJobs) -> APIRouter:
    router = APIRouter()

    @router.post("/api/media/analysis-jobs")
    async def create(request: Request, payload: dict):
        require_media_auth(request)
        trip_id = payload.get("tripId")
        if not isinstance(trip_id, str) or not trips.get(trip_id):
            raise HTTPException(404, "行程不存在")
        try:
            purpose = payload.get("purpose", "curation")
            if purpose == "history" and trips.get(trip_id).get("kind") != "history":
                raise ValueError("历史分析只能用于过往旅行")
            job = jobs.submit(trip_id, payload.get("photoIds"), payload.get("batchId"), purpose)
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from exc
        return JSONResponse({key: value for key, value in job.items() if key != "ownerId"}, status_code=202)

    @router.get("/api/media/trips/{trip_id}/analysis-jobs")
    async def list_for_trip(trip_id: str, request: Request):
        require_media_auth(request)
        if not trips.get(trip_id):
            raise HTTPException(404, "行程不存在")
        return {"jobs": [{key: value for key, value in job.items() if key != "ownerId"} for job in jobs.list(trip_id)]}

    @router.get("/api/media/analysis-jobs/{job_id}")
    async def read(job_id: str, request: Request):
        require_media_auth(request)
        job = jobs.get(job_id)
        if not job:
            raise HTTPException(404, "分析任务不存在")
        return {key: value for key, value in job.items() if key != "ownerId"}

    @router.post("/api/media/analysis-jobs/{job_id}/retry")
    async def retry(job_id: str, request: Request):
        require_media_auth(request)
        job = jobs.retry(job_id)
        if not job:
            raise HTTPException(409, "分析任务不能重试")
        return JSONResponse({key: value for key, value in job.items() if key != "ownerId"}, status_code=202)

    return router
