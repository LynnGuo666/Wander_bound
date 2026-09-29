"""Durable batch photo curation and private Spark vision analysis."""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path

from ..trips import now
from ..accounts import current_user
from .curate import curate_trip
from .vlm import VLMError, tag_image, tag_history_image


class AnalysisJobs:
    def __init__(self, media):
        self.media = media
        self.root = media.root / "analysis-jobs"
        self.worker: asyncio.Task | None = None

    def get(self, job_id: str) -> dict | None:
        try:
            uuid.UUID(job_id)
            job = json.loads((self.root / f"{job_id}.json").read_text())
            user = current_user.get()
            return job if user is None or job.get("ownerId") == user["id"] else None
        except (ValueError, FileNotFoundError, json.JSONDecodeError):
            return None

    def list(self, trip_id: str) -> list[dict]:
        return sorted((job for file in self.root.glob("*.json")
                       if (job := self.get(file.stem)) and job["tripId"] == trip_id),
                      key=lambda job: job["createdAt"], reverse=True)

    def save(self, job: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.root / f"{job['id']}.json"
        temporary = self.root / f"{job['id']}.{uuid.uuid4().hex}.tmp"
        try:
            temporary.write_text(json.dumps(job, ensure_ascii=False))
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def submit(self, trip_id: str, photo_ids: list[str], batch_id: str, purpose: str = "curation") -> dict:
        if (not isinstance(photo_ids, list) or not photo_ids or len(photo_ids) > 10000
                or any(not isinstance(pid, str) for pid in photo_ids)
                or len(photo_ids) != len(set(photo_ids))):
            raise ValueError("请选择 1 至 10000 张互不重复的照片")
        if any(not isinstance(pid, str) or not (photo := self.media.get(pid)) or
               photo["tripId"] != trip_id for pid in photo_ids):
            raise ValueError("照片不存在或不属于该行程")
        if not isinstance(batch_id, str) or not 1 <= len(batch_id) <= 128:
            raise ValueError("batchId 无效")
        if purpose not in {"curation", "history"}:
            raise ValueError("purpose 无效")
        for previous in self.list(trip_id):
            if previous["batchId"] == batch_id:
                if previous["photoIds"] != photo_ids or previous.get("purpose", "curation") != purpose:
                    raise ValueError("batchId 已用于另一批照片")
                return previous
        job = {"id": str(uuid.uuid4()), "tripId": trip_id, "photoIds": photo_ids,
               "ownerId": (current_user.get() or {}).get("id"),
               "batchId": batch_id, "purpose": purpose, "status": "queued", "stage": "等待分析",
               "completed": 0, "total": len(photo_ids), "results": {}, "recommended": [],
               "warnings": [], "error": None, "createdAt": now(), "updatedAt": now()}
        self.save(job)
        self.schedule()
        return job

    def retry(self, job_id: str) -> dict | None:
        job = self.get(job_id)
        if not job or (job["status"] != "failed" and not
                       (job["status"] == "succeeded" and job["warnings"])):
            return None
        job.update(status="queued", stage="等待重试", error=None, updatedAt=now())
        self.save(job)
        self.schedule()
        return job

    def schedule(self) -> None:
        if self.worker is None or self.worker.done():
            reset = current_user.set(None)
            try:
                self.worker = asyncio.create_task(self.run_pending())
            finally:
                current_user.reset(reset)

    async def resume(self) -> None:
        if any(job.get("ownerId") and job["status"] in {"queued", "running"} for file in self.root.glob("*.json")
               if (job := self.get(file.stem))):
            self.schedule()

    async def close(self) -> None:
        if self.worker:
            self.worker.cancel()
            try:
                await self.worker
            except asyncio.CancelledError:
                pass

    async def run_pending(self) -> None:
        while True:
            pending = [job for file in self.root.glob("*.json") if (job := self.get(file.stem))
                       and job.get("ownerId") and job["status"] in {"queued", "running"}]
            if not pending:
                return
            await self.run_one(sorted(pending, key=lambda item: item["createdAt"])[0])

    async def run_one(self, job: dict) -> None:
        try:
            if job.get("purpose") == "history":
                await self.run_history(job)
                return
            job.update(completed=0, results={}, recommended=[], warnings=[])
            job.update(status="running", stage="画质筛选与去重", updatedAt=now())
            self.save(job)
            curated = await asyncio.to_thread(curate_trip, self.media, job["tripId"], None, job["photoIds"])
            job["recommended"] = curated["keep"]
            for pid in job["photoIds"]:
                job["results"][pid] = {"verdict": curated["verdicts"].get(pid, "drop")}
            job.update(stage="视觉分析", updatedAt=now())
            self.save(job)
            for pid in job["photoIds"]:
                if job["results"][pid]["verdict"] == "keep":
                    try:
                        tags = (self.media.get(pid) or {}).get("tags")
                        if not tags:
                            tags = await asyncio.to_thread(tag_image, self.media.bytes(pid))
                            self.media.set_tags(pid, tags)
                        job["results"][pid]["tags"] = tags
                        visual = tags.get("quality") or {}
                        if visual.get("trash") is True or (
                            isinstance(visual.get("keep"), (int, float)) and visual["keep"] <= 1
                        ):
                            job["recommended"] = [item for item in job["recommended"] if item != pid]
                            job["results"][pid]["verdict"] = "visual_drop"
                    except VLMError:
                        job["warnings"].append({"photoId": pid, "message": "视觉打标未完成，已保留画质分析"})
                job["results"][pid]["quality"] = (self.media.get(pid) or {}).get("quality") or {}
                job["completed"] += 1
                job["updatedAt"] = now()
                self.save(job)
            job.update(status="succeeded", stage="分析完成", updatedAt=now())
        except asyncio.CancelledError:
            self.save(job)
            raise
        except Exception:
            job.update(status="failed", stage="分析失败", error="分析暂时失败，请重试", updatedAt=now())
        self.save(job)

    async def run_history(self, job: dict) -> None:
        """Examine every selected photo, including images curation would discard."""
        job.update(status="running", stage="逐张识别历史行程线索", completed=0,
                   results={}, recommended=[], warnings=[], updatedAt=now())
        self.save(job)

        async def analyze(pid: str) -> tuple[str, dict | None]:
            tags = (self.media.get(pid) or {}).get("tags")
            if tags:
                return pid, tags
            try:
                return pid, await asyncio.to_thread(tag_history_image, self.media.bytes(pid))
            except VLMError:
                return pid, None

        try:
            for start in range(0, len(job["photoIds"]), 3):
                batch = job["photoIds"][start:start + 3]
                for pid, tags in await asyncio.gather(*(analyze(pid) for pid in batch)):
                    if tags:
                        self.media.set_tags(pid, tags)
                    else:
                        job["warnings"].append({"photoId": pid, "message": "视觉打标未完成，已保留元数据"})
                    job["results"][pid] = {"verdict": "evidence", "tags": tags or {}}
                    job["completed"] += 1
                job["updatedAt"] = now()
                self.save(job)
            job.update(status="succeeded", stage="分析完成", updatedAt=now())
        except asyncio.CancelledError:
            self.save(job)
            raise
        except Exception:
            job.update(status="failed", stage="分析失败", error="分析暂时失败，请重试", updatedAt=now())
        self.save(job)
