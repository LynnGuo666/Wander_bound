"""Durable local queue for remote Spark image and video jobs."""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path

from .comfy import ComfyClient
from .media import MediaStore
from .trips import now


class JobStore:
    def __init__(self, media: MediaStore, image: ComfyClient | None, video: ComfyClient | None):
        self.media = media
        self.image = image
        self.video = video
        self.root = media.root / "jobs"
        self.tasks: dict[str, asyncio.Task] = {}

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
               "createdAt": now(), "attempt": 1, **payload}
        self.save(job)
        self._schedule(job["id"])
        return job

    def _schedule(self, job_id: str):
        if job_id not in self.tasks or self.tasks[job_id].done():
            self.tasks[job_id] = asyncio.create_task(self._run(job_id))

    async def resume(self):
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        for path in self.root.glob("*.json"):
            job = self.get(path.stem)
            if job and job.get("status") in {"queued", "running"}:
                self._schedule(job["id"])

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
            self.save(job)
            if job["kind"] == "edit":
                if not job.get("promptId"):
                    source = self.media.bytes(job["photoId"])
                    job["promptId"] = await self.image.queue(source, job["prompt"], job["seed"])
                    self.save(job)
                image = await self._wait(self.image, job["promptId"])
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
                    if not clip.get("promptId"):
                        prompt = f"旅行回忆短片第 {index + 1} 个镜头。保留输入照片的主体与真实场景，缓慢平稳的电影感运镜，自然光影。画面里不要出现文字、字幕或标志，不要虚构人物。"
                        clip["promptId"] = await self.video.queue(self.media.bytes(clip["photoId"]), prompt)
                        self.save(job)
                    output.write_bytes(await self._wait(self.video, clip["promptId"]))
                    clip["done"] = True
                    job["completedClips"] = index + 1
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
            job["completedAt"] = now()
        except Exception as exc:
            job["status"] = "failed"
            job["error"] = str(exc)[:300]
        self.save(job)

    def retry(self, job_id: str) -> dict | None:
        job = self.get(job_id)
        if not job or job["status"] != "failed":
            return None
        job["status"] = "queued"
        job["error"] = None
        job["attempt"] += 1
        self.save(job)
        self._schedule(job_id)
        return job
