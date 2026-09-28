"""Durable local queue for remote Spark image and video jobs."""
from __future__ import annotations

import asyncio
import copy
import json
import os
import secrets
import uuid
from pathlib import Path

import httpx

from .comfy import ComfyClient
from . import workflow_versions
from .store import MediaStore
from .contracts import (ContractError, original_from_snapshot, product_contract,
                        selected_original_snapshot, validate_snapshot)
from ..inference import ModelController
from ..trips import now

MAX_RESOURCE_RETRIES = 3
RESOURCE_RETRY_DELAY_SECONDS = 30
MAX_JOB_ATTEMPTS = 3
MAX_MISSING_POLLS = 3
POLL_DELAY_SECONDS = 5
SEED_MASK = (1 << 64) - 1


class JobStore:
    def __init__(self, media: MediaStore, image: ComfyClient | None, video: ComfyClient | None,
                 controller: ModelController):
        self.media = media
        self.image = image
        self.video = video
        self.root = media.root / "jobs"
        self.controller = controller
        self.worker: asyncio.Task | None = None

    def get(self, job_id: str) -> dict | None:
        try:
            uuid.UUID(job_id)
            return json.loads((self.root / f"{job_id}.json").read_text())
        except (ValueError, FileNotFoundError, json.JSONDecodeError):
            return None

    def save(self, job: dict):
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        filename = self.root / f"{job['id']}.json"
        temporary = self.root / f"{job['id']}.{uuid.uuid4()}.tmp"
        temporary.write_text(json.dumps(job, ensure_ascii=False))
        os.chmod(temporary, 0o600)
        os.replace(temporary, filename)

    def submit(self, kind: str, payload: dict) -> dict:
        if kind not in {"edit", "memory"}:
            raise ValueError("不支持的生成任务类型")
        if kind == "edit":
            photo = self.media.get(payload["photoId"])
            if photo is None:
                raise ContractError("PHOTO_NOT_FOUND", "照片不存在", 404)
            snapshot = selected_original_snapshot(self.media, photo.get("tripId"), [payload["photoId"]], maximum=1)
        else:
            snapshot = selected_original_snapshot(self.media, payload.get("tripId"), payload.get("photoIds"), maximum=8)
        adapter = self.image if kind == "edit" else self.video
        if not adapter or not adapter.configured:
            raise ValueError("Spark 工作流未配置")
        try:
            workflow_snapshot = adapter.freeze_workflow()
        except (OSError, RuntimeError, ValueError) as exc:
            raise ValueError(f"Spark 工作流快照不可用：{exc}") from exc
        seed_input = payload["seed"] if "seed" in payload else secrets.randbits(64)
        try:
            parameters, seed = workflow_versions.validate_parameters(
                workflow_snapshot, payload.get("parameters"), seed_input)
        except ValueError as exc:
            raise ContractError("WORKFLOW_PARAMETERS_INVALID", str(exc), 400) from exc
        if kind == "memory":
            clips = [{"photoId": photo_id, "seed": (seed + index) & SEED_MASK}
                     for index, photo_id in enumerate(payload["photoIds"])]
        else:
            clips = None
        job = {"id": str(uuid.uuid4()), "kind": kind, "status": "queued", "backend": "dgx-spark-qwen-image-2.1" if kind == "edit" else "dgx-spark-minimax-h3",
               "createdAt": now(), "attempt": 1, "progressPercent": 0, "progressLabel": "等待调度",
               **payload, "selectionSnapshot": copy.deepcopy(snapshot),
               "workflowSnapshot": copy.deepcopy(workflow_snapshot),
               "parameters": copy.deepcopy(parameters), "seed": seed}
        if clips is not None:
            job["clips"] = clips
        self.save(job)
        self._schedule()
        return job

    def prepare_product(self, payload: dict) -> dict:
        """Persist a validated product DTO; later feature tasks provide actual runners."""
        contract = product_contract(self.media, payload)
        job = {"id": str(uuid.uuid4()), "kind": contract["productKind"],
               "productKind": contract["productKind"], "resultKind": contract["resultKind"],
               "status": "prepared", "executionReady": False, "backend": None,
               "createdAt": now(), "tripId": contract["snapshot"]["tripId"],
               "selectionSnapshot": copy.deepcopy(contract["snapshot"]),
               "prompt": contract["prompt"], "result": None, "error": None}
        self.save(job)
        return job

    def _schedule(self):
        if self.worker is None or self.worker.done():
            self.worker = asyncio.create_task(self._drain())

    def pending(self) -> list[dict]:
        jobs = (self.get(path.stem) for path in self.root.glob("*.json")) if self.root.exists() else ()
        return sorted((job for job in jobs if job and job.get("status") in {"queued", "running", "loading_model"}),
                      key=lambda job: (job.get("createdAt", ""), job["id"]))

    def _validate_job_inputs(self, job: dict) -> None:
        snapshot = job.get("selectionSnapshot")
        expected = [job.get("photoId")] if job.get("kind") == "edit" else job.get("photoIds")
        if (job.get("kind") not in {"edit", "memory"} or not isinstance(snapshot, dict)
                or not isinstance(expected, list) or not expected
                or any(not isinstance(photo_id, str) for photo_id in expected)
                or snapshot.get("inputPhotoIds") != expected
                or (job.get("kind") == "memory" and snapshot.get("tripId") != job.get("tripId"))):
            raise ContractError("SNAPSHOT_INVALID", "任务缺少有效的输入快照", 409)
        validate_snapshot(snapshot)
        for photo_id in expected:
            original_from_snapshot(self.media, snapshot, photo_id)
        adapter_kind = "image" if job["kind"] == "edit" else "video"
        try:
            workflow = workflow_versions.validate_snapshot(job.get("workflowSnapshot"), adapter_kind)
            parameters, seed = workflow_versions.validate_parameters(
                workflow, job.get("parameters"), job.get("seed"))
        except (KeyError, TypeError, ValueError) as exc:
            raise ContractError("WORKFLOW_SNAPSHOT_INVALID", f"任务工作流快照无效：{exc}", 409) from exc
        if parameters != job.get("parameters") or seed != job.get("seed"):
            raise ContractError("WORKFLOW_SNAPSHOT_INVALID", "任务工作流参数与快照不一致", 409)
        if job["kind"] == "memory":
            clips = job.get("clips")
            if (not isinstance(clips, list) or len(clips) != len(expected)
                    or any(not isinstance(clip, dict) or clip.get("photoId") != photo_id
                           or clip.get("seed") != (seed + index) & SEED_MASK
                           for index, (clip, photo_id) in enumerate(zip(clips, expected)))):
                raise ContractError("WORKFLOW_SNAPSHOT_INVALID", "视频镜头与固定 seed 不一致", 409)

    def _fail(self, job: dict, exc: Exception) -> None:
        job["status"] = "failed"
        job["error"] = str(exc)[:300]
        job["errorCode"] = exc.code if isinstance(exc, ContractError) else "JOB_FAILED"
        job["progressLabel"] = "任务失败"
        self.save(job)

    async def _drain(self):
        while pending := self.pending():
            job = pending[0]
            try:
                self._validate_job_inputs(job)
                job["status"] = "loading_model"
                job["progressLabel"] = "加载模型服务"
                job["progressPercent"] = 5
                self.save(job)
                async with self.controller.use("image" if job["kind"] == "edit" else "video"):
                    await self._run(job["id"])
            except asyncio.CancelledError:
                raise
            except ContractError as exc:
                self._fail(self.get(job["id"]) or job, exc)
            except Exception as exc:
                job = self.get(job["id"]) or job
                if job["status"] == "succeeded":
                    continue
                retries = job.get("resourceRetries", 0) + 1
                job["resourceRetries"] = retries
                if retries >= MAX_RESOURCE_RETRIES:
                    self._fail(job, exc)
                    job["errorCode"] = "RESOURCE_RETRY_EXHAUSTED"
                    self.save(job)
                    continue
                job["status"] = "queued"
                job["error"] = str(exc)[:300]
                job["progressLabel"] = "等待资源后重试"
                job["progressPercent"] = 0
                self.save(job)
                await asyncio.sleep(RESOURCE_RETRY_DELAY_SECONDS)
        if getattr(self.controller, "primary_chat", False) and not self.controller.primary_paused:
            self.controller.begin_warm("chat")

    async def resume(self):
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.pending():
            self._schedule()

    async def close(self):
        if self.worker and not self.worker.done():
            self.worker.cancel()
            try:
                await self.worker
            except asyncio.CancelledError:
                pass

    async def _wait(self, adapter: ComfyClient, prompt_id: str) -> bytes:
        missing_polls = 0
        transient_polls = 0
        download_polls = 0
        for _ in range(360):
            try:
                status, file = await adapter.result(prompt_id)
            except (httpx.HTTPError, OSError) as exc:
                transient_polls += 1
                if transient_polls >= MAX_MISSING_POLLS:
                    raise RuntimeError("Spark 队列/历史持续不可达") from exc
                await asyncio.sleep(POLL_DELAY_SECONDS)
                continue
            transient_polls = 0
            if status == "completed" and file:
                try:
                    return await adapter.download(file)
                except (httpx.HTTPError, OSError) as exc:
                    download_polls += 1
                    if download_polls >= MAX_MISSING_POLLS:
                        raise RuntimeError("Spark 已完成产物持续无法下载") from exc
                    await asyncio.sleep(POLL_DELAY_SECONDS)
                    continue
            if status == "failed":
                raise RuntimeError("Spark 工作流失败；旧 prompt 不会自动重提交")
            if status == "missing":
                missing_polls += 1
                if missing_polls >= MAX_MISSING_POLLS:
                    raise RuntimeError("Spark 队列/历史中持续找不到 prompt")
            else:
                missing_polls = 0
            await asyncio.sleep(POLL_DELAY_SECONDS)
        raise TimeoutError("Spark 工作流执行超时")

    async def _run(self, job_id: str):
        job = self.get(job_id)
        if not job:
            return
        try:
            self._validate_job_inputs(job)
            # A previous resource wait is historical; it is no longer the
            # current outcome once this run has acquired the controller.
            job["error"] = None
            job.pop("errorCode", None)
            if job["kind"] == "edit":
                variant = f"ai-{job['id']}"
                photo = self.media.get(job["photoId"]) or {}
                if variant in photo.get("variants", []) and self.media.bytes(job["photoId"], variant):
                    job["variant"] = variant
                    job["status"] = "succeeded"
                    job["progressLabel"] = "已恢复已有图片产物"
                    job["progressPercent"] = 100
                    job["completedAt"] = now()
                    self.save(job)
                    return
            job["status"] = "running"
            job.setdefault("startedAt", now())
            job["progressLabel"] = "上传输入并提交工作流"
            job["progressPercent"] = 10
            self.save(job)
            if job["kind"] == "edit":
                if not job.get("promptId"):
                    source = original_from_snapshot(self.media, job.get("selectionSnapshot"), job["photoId"])
                    job["promptId"] = str(uuid.uuid4())
                    job["submissionState"] = "intent_recorded"
                    self.save(job)
                    try:
                        accepted = await self.image.queue(
                            source, job["prompt"], job["seed"], prompt_id=job["promptId"],
                            workflow_snapshot=job["workflowSnapshot"], parameters=job["parameters"])
                    except (httpx.HTTPError, OSError, RuntimeError):
                        # The server may have queued this UUID before its HTTP response was lost.
                        job["submissionState"] = "unknown"
                    else:
                        if accepted != job["promptId"]:
                            raise RuntimeError("Spark 返回的 promptId 与已冻结提交 ID 不一致")
                        job["submissionState"] = "accepted"
                    self.save(job)
                job["progressLabel"] = "图片生成中"
                job["progressPercent"] = None
                self.save(job)
                image = await self._wait(self.image, job["promptId"])
                job["submissionState"] = "completed"
                self.save(job)
                job["progressLabel"] = "保存图片"
                job["progressPercent"] = 95
                self.save(job)
                job["variant"] = f"ai-{job['id']}"
                self.media.save_variant(job["photoId"], job["variant"], image)
            else:
                job_dir = self.root / job_id
                job_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
                clips = job["clips"]
                final_video = job_dir / "memory.mp4"
                if final_video.exists() and all(clip.get("done") for clip in clips):
                    job["status"] = "succeeded"
                    job["progressLabel"] = "已恢复已有视频产物"
                    job["progressPercent"] = 100
                    job["completedAt"] = now()
                    self.save(job)
                    return
                for index, clip in enumerate(clips):
                    output = job_dir / f"{index}.mp4"
                    if output.exists():
                        if not clip.get("done"):
                            clip["done"] = True
                            job["completedClips"] = max(job.get("completedClips", 0), index + 1)
                            self.save(job)
                        continue
                    job["progressLabel"] = f"生成镜头 {index + 1}/{len(clips)}"
                    job["progressPercent"] = None
                    self.save(job)
                    if not clip.get("promptId"):
                        prompt = f"旅行回忆短片第 {index + 1} 个镜头。保留输入照片的主体与真实场景，缓慢平稳的电影感运镜，自然光影。画面里不要出现文字、字幕或标志，不要虚构人物。"
                        source = original_from_snapshot(self.media, job.get("selectionSnapshot"), clip["photoId"])
                        clip["promptId"] = str(uuid.uuid4())
                        clip["submissionState"] = "intent_recorded"
                        self.save(job)
                        try:
                            accepted = await self.video.queue(
                                source, prompt, clip["seed"], prompt_id=clip["promptId"],
                                workflow_snapshot=job["workflowSnapshot"], parameters=job["parameters"])
                        except (httpx.HTTPError, OSError, RuntimeError):
                            clip["submissionState"] = "unknown"
                        else:
                            if accepted != clip["promptId"]:
                                raise RuntimeError("Spark 返回的镜头 promptId 与已冻结提交 ID 不一致")
                            clip["submissionState"] = "accepted"
                        self.save(job)
                    temporary_clip = job_dir / f"{index}.pending.mp4"
                    temporary_clip.write_bytes(await self._wait(self.video, clip["promptId"]))
                    clip["submissionState"] = "completed"
                    self.save(job)
                    os.replace(temporary_clip, output)
                    clip["done"] = True
                    job["completedClips"] = index + 1
                    job["progressPercent"] = round((index + 1) / (len(clips) + 1) * 95)
                    self.save(job)
                job["progressLabel"] = "合成回忆短片"
                job["progressPercent"] = 95
                self.save(job)
                concat = job_dir / "clips.txt"
                concat.write_text("\n".join(f"file '{(job_dir / f'{index}.mp4').as_posix()}'" for index in range(len(clips))))
                temporary_video = job_dir / "memory.pending.mp4"
                process = await asyncio.create_subprocess_exec("ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat",
                                "-safe", "0", "-i", str(concat), "-c:v", "libx264", "-c:a", "aac", "-movflags", "+faststart",
                                str(temporary_video), stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
                _, stderr = await process.communicate()
                if process.returncode:
                    raise RuntimeError(f"视频合成失败：{stderr.decode(errors='replace')[:200]}")
                os.replace(temporary_video, final_video)
            job["status"] = "succeeded"
            job["progressLabel"] = "已完成"
            job["progressPercent"] = 100
            job["completedAt"] = now()
        except Exception as exc:
            self._fail(job, exc)
            return
        self.save(job)

    def retry(self, job_id: str, *, expected_kind: str | None = None) -> dict | None:
        job = self.get(job_id)
        if (not job or job["status"] != "failed" or job.get("attempt", 1) >= MAX_JOB_ATTEMPTS
                or (expected_kind is not None and job["kind"] != expected_kind)):
            return None
        job["status"] = "queued"
        job["error"] = None
        job.pop("errorCode", None)
        job["progressLabel"] = "等待调度"
        job["progressPercent"] = 0
        job["attempt"] += 1
        job["resourceRetries"] = 0
        if job.get("submissionState") != "completed":
            job.pop("promptId", None)
            job.pop("submissionState", None)
        for clip in job.get("clips", []):
            if not clip.get("done") and clip.get("submissionState") != "completed":
                clip.pop("promptId", None)
                clip.pop("submissionState", None)
        self.save(job)
        self._schedule()
        return job
