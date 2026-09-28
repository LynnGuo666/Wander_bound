"""Authenticated draft/edit/confirm interfaces. No video submission side effects."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from .auth import require_media_auth
from .contracts import ContractError
from .job_routes import _fields, _require_trip


def public(job):
    return {key: job.get(key) for key in (
        "id", "tripId", "productKind", "resultKind", "status", "version", "draft", "draftDigest",
        "selectionSnapshot", "materialCardsSnapshot", "confirmedSnapshot", "error", "errorCode",
        "createdAt", "startedAt", "completedAt", "attempt", "stepAttempts", "backend", "promptVersion")}


def router_for(trips, boards):
    router = APIRouter()

    def call(fn, *args):
        try:
            return public(fn(*args))
        except ContractError as exc:
            raise HTTPException(exc.status_code, exc.body()) from exc

    @router.post("/api/media/storyboards")
    async def create(request: Request, payload: dict):
        require_media_auth(request)
        _fields(payload, {"tripId", "photoIds"})
        _require_trip(trips, payload.get("tripId"))
        return JSONResponse(call(boards.create, payload["tripId"], payload.get("photoIds")), status_code=202)

    @router.get("/api/media/storyboards/{job_id}")
    async def get(job_id: str, request: Request):
        require_media_auth(request)
        return call(boards.get, job_id)

    @router.put("/api/media/storyboards/{job_id}")
    async def edit(job_id: str, request: Request, payload: dict):
        require_media_auth(request)
        _fields(payload, {"expectedVersion", "draft"})
        return call(boards.edit, job_id, payload.get("expectedVersion"), payload.get("draft"))

    @router.post("/api/media/storyboards/{job_id}/confirm")
    async def confirm(job_id: str, request: Request, payload: dict):
        require_media_auth(request)
        _fields(payload, {"version", "draftDigest", "confirmed"})
        return call(boards.confirm, job_id, payload.get("version"), payload.get("draftDigest"), payload.get("confirmed"))

    @router.post("/api/media/storyboards/{job_id}/retry")
    async def retry(job_id: str, request: Request):
        require_media_auth(request)
        return JSONResponse(call(boards.retry, job_id), status_code=202)

    return router
