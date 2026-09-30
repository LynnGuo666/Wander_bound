"""Private Spark media job endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from ..trips import TripStore
from .store import MediaStore
from .jobs import JobStore
from .auth import require_media_auth
from .contracts import ContractError, MAX_PROMPT_LENGTH, PRODUCT_KINDS
from .scrapbook import style_catalog
from .material_cards import MaterialCards
from .contracts import selected_original_snapshot


def _contract_error(exc: ContractError) -> HTTPException:
    return HTTPException(exc.status_code, exc.body())


def _fields(payload: dict, allowed: set[str]) -> None:
    if set(payload) - allowed:
        raise HTTPException(400, {"code": "REQUEST_INVALID", "message": "请求包含未支持字段"})


def _require_trip(trips: TripStore, trip_id: object) -> None:
    if not isinstance(trip_id, str):
        raise HTTPException(400, {"code": "TRIP_ID_INVALID", "message": "tripId 无效"})
    if not trips.get(trip_id):
        raise HTTPException(404, {"code": "TRIP_NOT_FOUND", "message": "行程不存在"})

def router_for(trips: TripStore, media: MediaStore, jobs: JobStore) -> APIRouter:
    router = APIRouter()
    cards = MaterialCards(media)

    @router.get("/api/media/trips/{trip_id}/works")
    async def list_works(trip_id: str, request: Request):
        require_media_auth(request)
        _require_trip(trips, trip_id)
        return {"works": jobs.list_for_trip(trip_id)}

    @router.get("/api/media/trips/{trip_id}/photos/{photo_id}/material-card")
    async def read_material_card(trip_id: str, photo_id: str, request: Request):
        require_media_auth(request)
        _require_trip(trips, trip_id)
        try:
            snapshot = selected_original_snapshot(media, trip_id, [photo_id], maximum=1)
            return cards.snapshot(snapshot)[0]
        except ContractError as exc:
            raise _contract_error(exc) from exc

    @router.put("/api/media/trips/{trip_id}/photos/{photo_id}/material-card")
    async def save_material_card(trip_id: str, photo_id: str, request: Request, payload: dict):
        require_media_auth(request)
        _require_trip(trips, trip_id)
        try:
            return cards.put(trip_id, photo_id, payload)
        except ContractError as exc:
            raise _contract_error(exc) from exc

    @router.get("/api/media/scrapbook-styles")
    async def scrapbook_styles(request: Request):
        require_media_auth(request)
        return {"styles": style_catalog()}

    @router.post("/api/media/scrapbooks")
    async def create_scrapbook(request: Request, payload: dict):
        require_media_auth(request)
        _fields(payload, {"tripId", "photoId", "styleId", "title", "seed"})
        _require_trip(trips, payload.get("tripId"))
        if not isinstance(payload.get("photoId"), str):
            raise HTTPException(400, {"code": "PHOTO_ID_INVALID", "message": "photoId 无效"})
        try:
            job = jobs.submit_scrapbook(payload)
        except ContractError as exc:
            raise _contract_error(exc) from exc
        except ValueError as exc:
            raise HTTPException(503, {"code": "WORKFLOW_UNAVAILABLE", "message": str(exc)}) from exc
        return JSONResponse({key: job[key] for key in
                             ("id", "productKind", "resultKind", "status", "executionReady", "seed", "selectionSnapshot")},
                            status_code=202)

    @router.post("/api/media/generation-jobs/{job_id}/retry")
    async def retry_scrapbook(job_id: str, request: Request):
        require_media_auth(request)
        current = jobs.get(job_id)
        if not current or current.get("kind") != "scrapbook" or current.get("status") != "failed":
            raise HTTPException(409, {"code": "JOB_NOT_RETRYABLE", "message": "此任务不能重试"})
        try:
            job = jobs.retry(job_id, expected_kind="scrapbook")
        except ContractError as exc:
            raise _contract_error(exc) from exc
        if not job:
            raise HTTPException(409, {"code": "RETRY_LIMIT_REACHED", "message": "已达到重试上限"})
        return JSONResponse({"id": job_id, "status": job["status"], "attempt": job["attempt"]}, status_code=202)

    @router.get("/api/media/generation-jobs/{job_id}/image")
    async def scrapbook_image(job_id: str, request: Request):
        return scrapbook_file(job_id, request, "scrapbook.jpg")

    @router.get("/api/media/generation-jobs/{job_id}/thumbnail")
    async def scrapbook_thumbnail(job_id: str, request: Request):
        return scrapbook_file(job_id, request, "thumbnail.jpg")

    def scrapbook_file(job_id: str, request: Request, name: str):
        require_media_auth(request)
        job = jobs.get(job_id)
        if not job or job.get("kind") != "scrapbook":
            raise HTTPException(404, {"code": "JOB_NOT_FOUND", "message": "手帐不存在"})
        path = jobs.root / job_id / name
        if job["status"] != "succeeded" or not path.is_file():
            raise HTTPException(409, {"code": "RESULT_NOT_READY", "message": "手帐尚未生成"})
        return FileResponse(path, media_type="image/jpeg", filename=name)
    @router.post("/api/media/memories")
    async def create_memory(request: Request, payload: dict):
        require_media_auth(request)
        _fields(payload, {"tripId", "photoIds", "title", "seed", "parameters"})
        trip_id = payload.get("tripId")
        photo_ids = payload.get("photoIds")
        _require_trip(trips, trip_id)
        title = payload.get("title", "旅行回忆")
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 80:
            raise HTTPException(400, {"code": "TITLE_INVALID", "message": "title 必须是 1–80 字符"})
        try:
            job = jobs.submit("memory", {"tripId": trip_id, "photoIds": photo_ids,
                                         "title": title.strip(),
                                         **{key: payload[key] for key in ("seed", "parameters") if key in payload}})
        except ContractError as exc:
            raise _contract_error(exc) from exc
        except ValueError as exc:
            raise HTTPException(503, str(exc)) from exc
        return JSONResponse({key: job[key] for key in ("id", "status", "backend", "seed", "parameters")}, status_code=202)

    @router.post("/api/media/photos/{photo_id}/redraw")
    async def redraw(photo_id: str, request: Request, payload: dict):
        require_media_auth(request)
        _fields(payload, {"prompt", "seed", "parameters"})
        photo = media.get(photo_id)
        if not photo:
            raise HTTPException(404, {"code": "PHOTO_NOT_FOUND", "message": "照片不存在"})
        _require_trip(trips, photo.get("tripId"))
        prompt = payload.get("prompt")
        if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= MAX_PROMPT_LENGTH:
            raise HTTPException(400, {"code": "PROMPT_INVALID", "message": f"prompt 必须是 1–{MAX_PROMPT_LENGTH} 字符"})
        seed = payload.get("seed")
        if seed is not None and (type(seed) is not int or not 0 <= seed <= (1 << 64) - 1):
            raise HTTPException(400, {"code": "SEED_INVALID", "message": "seed 必须是 0–18446744073709551615 的整数"})
        try:
            job = jobs.submit("edit", {"photoId": photo_id, "prompt": prompt.strip(),
                                       **{key: payload[key] for key in ("seed", "parameters") if key in payload}})
        except ContractError as exc:
            raise _contract_error(exc) from exc
        except ValueError as exc:
            raise HTTPException(503, str(exc)) from exc
        return JSONResponse({key: job[key] for key in ("id", "status", "backend", "seed", "parameters")}, status_code=202)

    @router.post("/api/media/generation-jobs")
    async def prepare_generation_job(request: Request, payload: dict):
        """Persist a validated input contract; product runners arrive in M02/M03."""
        require_media_auth(request)
        _require_trip(trips, payload.get("tripId"))
        try:
            job = jobs.prepare_product(payload)
        except ContractError as exc:
            raise _contract_error(exc) from exc
        return JSONResponse({key: job[key] for key in
                             ("id", "productKind", "resultKind", "status", "executionReady", "selectionSnapshot")},
                            status_code=201)

    @router.get("/api/media/generation-jobs/{job_id}")
    async def generation_job_status(job_id: str, request: Request):
        require_media_auth(request)
        job = jobs.get(job_id)
        if not job or job.get("productKind") not in PRODUCT_KINDS:
            raise HTTPException(404, {"code": "JOB_NOT_FOUND", "message": "任务不存在"})
        return {key: job.get(key) for key in
                ("id", "productKind", "resultKind", "status", "executionReady", "backend",
                 "createdAt", "startedAt", "completedAt", "selectionSnapshot", "result", "error", "errorCode",
                 "styleId", "seed", "parameters", "title", "attempt", "progressLabel", "progressPercent", "scheduledAt")} | {
                    "styleVersion": (job.get("styleSnapshot") or {}).get("version"),
                    "presetSha256": (job.get("styleSnapshot") or {}).get("sha256"),
                    "workflowVersion": (job.get("workflowSnapshot") or {}).get("workflow_version"),
                    "workflowSnapshotSha256": (job.get("workflowSnapshot") or {}).get("snapshot_hash")}

    @router.get("/api/media/generation-jobs/{job_id}/result")
    async def generation_job_result(job_id: str, request: Request):
        require_media_auth(request)
        job = jobs.get(job_id)
        if not job or job.get("productKind") not in PRODUCT_KINDS:
            raise HTTPException(404, {"code": "JOB_NOT_FOUND", "message": "任务不存在"})
        if job["status"] != "succeeded" or job.get("result") is None:
            raise HTTPException(409, {"code": "RESULT_NOT_READY", "message": "产物尚未生成"})
        return {"id": job_id, "productKind": job["productKind"], "resultKind": job["resultKind"],
                "result": job["result"]}

    @router.get("/api/media/edits/{job_id}")
    async def edit_status(job_id: str, request: Request):
        require_media_auth(request)
        job = jobs.get(job_id)
        if not job or job["kind"] != "edit":
            raise HTTPException(404, "任务不存在")
        return {key: job.get(key) for key in ("id", "photoId", "status", "backend", "variant", "error", "errorCode", "createdAt", "startedAt", "completedAt", "attempt", "progressLabel", "progressPercent")}

    @router.post("/api/media/edits/{job_id}/retry")
    async def retry_edit(job_id: str, request: Request):
        require_media_auth(request)
        current = jobs.get(job_id)
        if not current or current.get("kind") != "edit" or current.get("status") != "failed":
            raise HTTPException(404, "无法重试")
        try:
            job = jobs.retry(job_id, expected_kind="edit")
        except ContractError as exc:
            raise _contract_error(exc) from exc
        if not job:
            raise HTTPException(404, "无法重试")
        return JSONResponse({"id": job_id, "status": job["status"], "attempt": job["attempt"]}, status_code=202)

    @router.get("/api/media/memories/{job_id}")
    async def memory_status(job_id: str, request: Request):
        require_media_auth(request)
        job = jobs.get(job_id)
        if not job or job["kind"] != "memory":
            raise HTTPException(404, "任务不存在")
        return {key: job.get(key) for key in ("id", "status", "backend", "error", "errorCode", "createdAt", "startedAt", "completedAt", "attempt", "completedClips", "progressLabel", "progressPercent", "scheduledAt")}

    @router.post("/api/media/memories/{job_id}/retry")
    async def retry_memory(job_id: str, request: Request):
        require_media_auth(request)
        current = jobs.get(job_id)
        if not current or current.get("kind") != "memory" or current.get("status") != "failed":
            raise HTTPException(404, "无法重试")
        try:
            job = jobs.retry(job_id, expected_kind="memory")
        except ContractError as exc:
            raise _contract_error(exc) from exc
        if not job:
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
