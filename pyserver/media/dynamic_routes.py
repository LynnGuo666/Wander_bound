"""Authenticated source settlement for dynamic-photo jobs."""
from __future__ import annotations

import asyncio
import fcntl
import hashlib
import uuid
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from ..trips import TripStore
from .auth import require_media_auth
from .contracts import ContractError
from .dynamic_sources import DynamicPhotoSources
from .jobs import JobStore
from .photo_routes import _render_development
from . import images


def router_for(trips: TripStore, sources: DynamicPhotoSources, jobs: JobStore) -> APIRouter:
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
            job = jobs.enqueue_dynamic(sources.settle(trip_id, payload)["id"])
        except ContractError as exc:
            raise HTTPException(exc.status_code, exc.body()) from exc
        return JSONResponse({key: value for key, value in job.items() if key != "ownerId"}, status_code=202)

    @router.post("/api/media/trips/{trip_id}/dynamic-photo/develop-batch-and-settle")
    async def develop_batch_and_settle(trip_id: str, request: Request, payload: dict):
        """The real backend batch caller: save requested develops, then settle and queue."""
        require_media_auth(request)
        if not trips.get(trip_id):
            raise HTTPException(404, {"code": "TRIP_NOT_FOUND", "message": "行程不存在"})
        if (not isinstance(payload, dict) or set(payload) != {"operationId", "batchId", "selectionUpdatedAt", "photos"}
                or not isinstance(payload.get("photos"), list) or not payload["photos"]):
            raise HTTPException(400, {"code": "BATCH_INVALID", "message": "批次请求字段无效"})
        try:
            operation_id = str(uuid.UUID(payload["operationId"]))
        except (TypeError, ValueError):
            raise HTTPException(400, {"code": "OPERATION_ID_INVALID", "message": "批次操作编号无效"}) from None
        if operation_id != payload["operationId"]:
            raise HTTPException(400, {"code": "OPERATION_ID_INVALID", "message": "批次操作编号无效"})
        batch_id, updated_at = payload["batchId"], payload["selectionUpdatedAt"]
        entries = payload["photos"]
        ids = []
        for entry in entries:
            if (not isinstance(entry, dict) or set(entry) not in
                    ({"photoId", "action"}, {"photoId", "action", "params", "note"})
                    or not isinstance(entry.get("photoId"), str)
                    or entry.get("action") not in {"develop", "none"}
                    or entry["action"] == "none" and set(entry) != {"photoId", "action"}
                    or entry["action"] == "develop" and set(entry) != {"photoId", "action", "params", "note"}):
                raise HTTPException(400, {"code": "BATCH_INVALID", "message": "精修操作清单无效"})
            ids.append(entry["photoId"])
        sources.batches.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (sources.batches / f"{operation_id}.lock").open("a+b") as lock:
            await asyncio.to_thread(fcntl.flock, lock, fcntl.LOCK_EX)
            try:
                try:
                    receipt = sources.begin_batch_operation(trip_id, payload)
                except ContractError as exc:
                    raise HTTPException(exc.status_code, exc.body()) from exc
                if receipt["status"] == "settled":
                    job = sources.get(receipt["jobId"])
                    if not job:
                        raise HTTPException(409, {"code": "SETTLED_JOB_MISSING", "message": "结算任务记录丢失"})
                    return JSONResponse({"jobId": job["id"], "status": job["status"],
                        "completedPhotoIds": receipt["completedPhotoIds"], "settled": True}, status_code=202)
                completed = list(receipt["completedPhotoIds"])
                for entry in entries:
                    if entry["action"] != "develop":
                        continue
                    pid = entry["photoId"]
                    try:
                        prior = sources.media.development_for_operation(pid, operation_id)
                        if prior:
                            if not sources.media.bytes(pid, prior["variant"]):
                                raise ContractError("DEVELOPMENT_UNREADABLE", "已保存精修版本丢失", 409)
                        else:
                            marker_id, marker_batch = sources.mark_development_started(trip_id, pid, updated_at)
                            try:
                                params = images.normalize_develop(entry["params"])
                                artifact = sources.media.development_artifact_for_operation(pid, operation_id)
                                rendered = b"" if artifact.is_file() else await _render_development(sources.media, pid, params)
                                saved = sources.media.save_develop(pid, rendered, params, entry["note"],
                                    expected_batch_id=marker_batch, expected_selection_updated_at=updated_at,
                                    operation_id=operation_id)
                                if saved is None:
                                    raise ContractError("SELECTION_CHANGED", "精修保存前精选版本已改变", 409)
                            finally:
                                sources.mark_development_finished(trip_id, marker_id)
                        receipt = sources.update_batch_operation(receipt, completed_photo_id=pid)
                        if pid not in completed:
                            completed.append(pid)
                    except ContractError as exc:
                        raise HTTPException(exc.status_code, {**exc.body(), "completedPhotoIds": completed,
                                                             "settled": False}) from exc
                    except (ValueError, OSError, RuntimeError) as exc:
                        raise HTTPException(503, {"code": "DEVELOPMENT_FAILED", "photoId": pid,
                                                  "completedPhotoIds": completed, "settled": False,
                                                  "message": type(exc).__name__}) from exc
                outcomes = [{"photoId": pid, "status": "developed" if
                             (sources.media.get(pid) or {}).get("developments") else "none"} for pid in ids]
                try:
                    job = jobs.enqueue_dynamic(sources.settle(trip_id, {"batchId": batch_id,
                        "selectionUpdatedAt": updated_at, "photos": outcomes})["id"])
                    receipt = sources.update_batch_operation(receipt, job_id=job["id"])
                except ContractError as exc:
                    raise HTTPException(exc.status_code, {**exc.body(), "completedPhotoIds": completed,
                                                         "settled": False}) from exc
                return JSONResponse({"jobId": job["id"], "status": job["status"],
                                     "completedPhotoIds": completed, "settled": True}, status_code=202)
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    @router.get("/api/media/dynamic-photo/jobs/{job_id}")
    async def status(job_id: str, request: Request):
        require_media_auth(request)
        job = sources.get(job_id)
        if not job or not trips.get(job["tripId"]):
            raise HTTPException(404, {"code": "JOB_NOT_FOUND", "message": "动态照片任务不存在"})
        return {key: value for key, value in job.items() if key != "ownerId"}

    @router.post("/api/media/dynamic-photo/jobs/{job_id}/retry")
    async def retry(job_id: str, request: Request):
        require_media_auth(request)
        job = sources.get(job_id)
        if not job or not trips.get(job["tripId"]):
            raise HTTPException(404, {"code": "JOB_NOT_FOUND", "message": "动态照片任务不存在"})
        try:
            updated = await jobs.retry_dynamic(job_id)
        except ContractError as exc:
            raise HTTPException(exc.status_code, exc.body()) from exc
        return JSONResponse({key: value for key, value in updated.items() if key != "ownerId"}, status_code=202)

    @router.get("/api/media/photos/{photo_id}/dynamic-photo")
    async def photo_versions(photo_id: str, request: Request):
        require_media_auth(request)
        photo = sources.media.get(photo_id)
        if not photo or not trips.get(photo["tripId"]):
            raise HTTPException(404, {"code": "PHOTO_NOT_FOUND", "message": "照片不存在"})
        versions = []
        for path in sources.root.glob("*.json"):
            job = sources.get(path.stem)
            if not job or job.get("tripId") != photo["tripId"]:
                continue
            association = next((item for item in job.get("associations", [])
                                if item.get("photoId") == photo_id), None)
            if association:
                versions.append({"jobId": job["id"], "status": job["status"],
                                 "photoId": photo_id, "sourceVariant": association["sourceVariant"],
                                 "createdAt": job["createdAt"],
                                 "staticUrl": f"/api/media/photos/{photo_id}?variant={association['sourceVariant']}",
                                 "dynamicVersionId": association["dynamicVersionId"],
                                 "result": job.get("result") if
                                 (job.get("result") or {}).get("photoId") == photo_id else None,
                                 "error": job.get("error") if
                                 (job.get("selection") or {}).get("selectedPhotoId") == photo_id else None})
        return {"photoId": photo_id, "staticUrl": f"/api/media/photos/{photo_id}",
                "versions": sorted(versions, key=lambda item: item["createdAt"], reverse=True)}

    def media_file(job_id: str, request: Request, filename: str, digest_field: str, media_type: str):
        require_media_auth(request)
        job = sources.get(job_id)
        if not job or not trips.get(job["tripId"]):
            raise HTTPException(404, {"code": "JOB_NOT_FOUND", "message": "动态照片任务不存在"})
        if job["status"] != "succeeded" or not job.get("result"):
            raise HTTPException(409, {"code": "RESULT_NOT_READY", "message": "动态版本尚未生成"})
        path = sources.root / job_id / filename
        try:
            content = path.read_bytes()
        except OSError:
            raise HTTPException(404, {"code": "RESULT_MISSING", "message": "动态版本文件不存在"}) from None
        if hashlib.sha256(content).hexdigest() != job["result"]["media"].get(digest_field):
            raise HTTPException(409, {"code": "RESULT_CHANGED", "message": "动态版本文件校验失败"})
        return FileResponse(path, media_type=media_type, headers={"Cache-Control": "private, no-store"})

    @router.get("/api/media/dynamic-photo/jobs/{job_id}/video")
    async def video(job_id: str, request: Request):
        return media_file(job_id, request, "dynamic.mp4", "sha256", "video/mp4")

    @router.get("/api/media/dynamic-photo/jobs/{job_id}/cover")
    async def cover(job_id: str, request: Request):
        return media_file(job_id, request, "cover.jpg", "coverSha256", "image/jpeg")

    return router
