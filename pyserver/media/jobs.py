"""Durable local queue for remote Spark image and video jobs."""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path

from .comfy import ComfyClient
from .store import MediaStore
from ..inference import ModelController
from ..trips import now


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
        adapter = self.image if kind == "edit" else self.video
        if not adapter or not adapter.configured:
            raise ValueError("Spark 工作流未配置")
        job = {"id": str(uuid.uuid4()), "kind": kind, "status": "queued", "backend": "dgx-spark-qwen-image-2.1" if kind == "edit" else "dgx-spark-minimax-h3",
               "createdAt": now(), "attempt": 1, "progressPercent": 0, "progressLabel": "等待调度", **payload}
        self.save(job)
        self._schedule()
        return job

    def _schedule(self):
        if self.worker is None or self.worker.done():
            self.worker = asyncio.create_task(self._drain())

    def pending(self) -> list[dict]:
        jobs = (self.get(path.stem) for path in self.root.glob("*.json")) if self.root.exists() else ()
        return sorted((job for job in jobs if job and job.get("status") in {"queued", "running", "loading_model"}),
                      key=lambda job: (job.get("createdAt", ""), job["id"]))

    async def _drain(self):
        while pending := self.pending():
            job = pending[0]
            try:
                job["status"] = "loading_model"
                job["progressLabel"] = "加载模型服务"
                job["progressPercent"] = 5
                self.save(job)
                async with self.controller.use("image" if job["kind"] == "edit" else "video"):
                    await self._run(job["id"])
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                job = self.get(job["id"]) or job
                job["status"] = "queued"
                job["error"] = str(exc)[:300]
                job["progressLabel"] = "等待资源后重试"
                job["progressPercent"] = 0
                self.save(job)
                await asyncio.sleep(30)
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
        for _ in range(360):
            status, file = await adapter.result(prompt_id)
            if status == "completed" and file:
                return await adapter.download(file)
            if status in {"failed", "missing"}:
                raise RuntimeError(f"Spark 工作流{status}")
            await asyncio.sleep(5)
        raise TimeoutError("Spark 工作流执行超时")

    async def _run(self, job_id: str):
        job = self.get(job_id)
        if not job:
            return
        try:
            job["status"] = "running"
            job.setdefault("startedAt", now())
            job["progressLabel"] = "上传输入并提交工作流"
            job["progressPercent"] = 10
            self.save(job)
            if job["kind"] == "edit":
                if not job.get("promptId"):
                    source = self.media.bytes(job["photoId"])
                    job["promptId"] = await self.image.queue(source, job["prompt"], job["seed"])
                    self.save(job)
                job["progressLabel"] = "图片生成中"
                job["progressPercent"] = None
                self.save(job)
                image = await self._wait(self.image, job["promptId"])
                job["progressLabel"] = "保存图片"
                job["progressPercent"] = 95
                self.save(job)
                job["variant"] = f"ai-{job['id']}"
                self.media.save_variant(job["photoId"], job["variant"], image)
            else:
                job_dir = self.root / job_id
                job_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
                clips = job.setdefault("clips", [{"photoId": photo_id} for photo_id in job["photoIds"]])
                for index, clip in enumerate(clips):
                    output = job_dir / f"{index}.mp4"
                    if clip.get("done") and output.exists():
                        continue
                    job["progressLabel"] = f"生成镜头 {index + 1}/{len(clips)}"
                    job["progressPercent"] = None
                    self.save(job)
                    if not clip.get("promptId"):
                        prompt = f"旅行回忆短片第 {index + 1} 个镜头。保留输入照片的主体与真实场景，缓慢平稳的电影感运镜，自然光影。画面里不要出现文字、字幕或标志，不要虚构人物。"
                        clip["promptId"] = await self.video.queue(self.media.bytes(clip["photoId"]), prompt)
                        self.save(job)
                    output.write_bytes(await self._wait(self.video, clip["promptId"]))
                    clip["done"] = True
                    job["completedClips"] = index + 1
                    job["progressPercent"] = round((index + 1) / (len(clips) + 1) * 95)
                    self.save(job)
                job["progressLabel"] = "合成回忆短片"
                job["progressPercent"] = 95
                self.save(job)
                concat = job_dir / "clips.txt"
                concat.write_text("\n".join(f"file '{(job_dir / f'{index}.mp4').as_posix()}'" for index in range(len(clips))))
                process = await asyncio.create_subprocess_exec("ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat",
                                "-safe", "0", "-i", str(concat), "-c:v", "libx264", "-c:a", "aac", "-movflags", "+faststart",
                                str(job_dir / "memory.mp4"), stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
                _, stderr = await process.communicate()
                if process.returncode:
                    raise RuntimeError(f"视频合成失败：{stderr.decode(errors='replace')[:200]}")
            job["status"] = "succeeded"
            job["progressLabel"] = "已完成"
            job["progressPercent"] = 100
            job["completedAt"] = now()
        except Exception as exc:
            job["status"] = "failed"
            job["error"] = str(exc)[:300]
            job["progressLabel"] = "任务失败"
        self.save(job)

    def retry(self, job_id: str) -> dict | None:
        job = self.get(job_id)
        if not job or job["status"] != "failed":
            return None
        job["status"] = "queued"
        job["error"] = None
        job["progressLabel"] = "等待调度"
        job["progressPercent"] = 0
        job["attempt"] += 1
        job.pop("promptId", None)
        for clip in job.get("clips", []):
            if not clip.get("done"):
                clip.pop("promptId", None)
        self.save(job)
        self._schedule()
        return job
