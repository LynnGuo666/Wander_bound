"""Single-image MiniMax H3 path for dynamic photos; old memory jobs stay unchanged."""
from __future__ import annotations

import asyncio
import fcntl
import hashlib
import json
import math
import os
import secrets
import subprocess
import uuid
from pathlib import Path
from fractions import Fraction

from ..trips import now
from .contracts import ContractError
from .dynamic_sources import DynamicPhotoSources
from . import workflow_versions


RUNNER_VERSION = "dynamic-photo-h3@1"
MAX_PIXELS = 768 * 1344
FRAMES = 124
FPS = 24


def choose_canvas(source_width: int, source_height: int) -> dict:
    """Favor exact source aspect, then area, on the installed node's 32px grid."""
    if (type(source_width) is not int or type(source_height) is not int
            or source_width <= 0 or source_height <= 0):
        raise ContractError("SOURCE_DIMENSIONS_INVALID", "来源尺寸无效", 409)
    ratio = source_width / source_height
    choices = [(width, height) for width in range(256, 1345, 32)
               for height in range(256, 1345, 32) if width * height <= MAX_PIXELS]
    width, height = min(choices, key=lambda pair: (abs(math.log((pair[0] / pair[1]) / ratio)),
                                                    -(pair[0] * pair[1])))
    relative_error = abs((width / height) / ratio - 1)
    if relative_error > 0.02:
        raise ContractError("ASPECT_UNSUPPORTED", "来源比例无法在 H3 画布上保真", 409)
    scale = min(width / source_width, height / source_height)
    fitted_width = min(width, round(source_width * scale))
    fitted_height = min(height, round(source_height * scale))
    return {"sourceWidth": source_width, "sourceHeight": source_height,
            "width": width, "height": height, "fittedWidth": fitted_width,
            "fittedHeight": fitted_height, "paddingX": width - fitted_width,
            "paddingY": height - fitted_height,
            "relativeAspectError": round(relative_error, 6),
            "policy": "source-contain-canvas-v1", "grid": 32, "maxPixels": MAX_PIXELS}


def inspect_video(path: Path, width: int, height: int) -> dict:
    """Probe H.264/no-audio metadata and force a complete decode."""
    try:
        probe = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-show_streams",
                                "-show_format", "-of", "json", str(path)],
                               capture_output=True, text=True, timeout=30, check=True)
        body = json.loads(probe.stdout)
        streams = body.get("streams") or []
        videos = [stream for stream in streams if stream.get("codec_type") == "video"]
        if (len(videos) != 1 or len(streams) != 1 or videos[0].get("codec_name") != "h264"
                or videos[0].get("pix_fmt") != "yuv420p"
                or videos[0].get("width") != width or videos[0].get("height") != height):
            raise ValueError("编码、尺寸或无音轨契约不符")
        frames = int(videos[0].get("nb_read_frames") or 0)
        duration = float((body.get("format") or {}).get("duration") or 0)
        actual_fps = float(Fraction(videos[0].get("avg_frame_rate") or "0"))
        if not 120 <= frames <= 128 or not 4.8 <= duration <= 5.5 or abs(actual_fps - FPS) > 0.1:
            raise ValueError("H3 帧数或时长不在约 5 秒范围")
        subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(path),
                        "-map", "0:v:0", "-f", "null", "-"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                       timeout=120, check=True)
        return {"width": width, "height": height, "frames": frames,
                "durationSeconds": duration, "fps": round(actual_fps, 3), "codec": "h264",
                "pixelFormat": "yuv420p", "hasAudio": False, "fullDecode": True,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    except (OSError, ValueError, ZeroDivisionError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        raise ContractError("VIDEO_INVALID", f"动态照片视频校验失败：{type(exc).__name__}", 409) from exc


def finish_video(raw_path: Path, output_path: Path, cover_path: Path,
                 width: int, height: int) -> dict:
    output_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(raw_path),
                        "-map", "0:v:0", "-an", "-c:v", "libx264", "-preset", "medium",
                        "-crf", "18", "-pix_fmt", "yuv420p", "-fps_mode", "passthrough",
                        "-movflags", "+faststart",
                        str(output_path)], capture_output=True, timeout=180, check=True)
        metadata = inspect_video(output_path, width, height)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(output_path),
                        "-frames:v", "1", str(cover_path)],
                       capture_output=True, timeout=30, check=True)
        if not cover_path.is_file() or not cover_path.stat().st_size:
            raise ValueError("封面提取失败")
        metadata["coverSha256"] = hashlib.sha256(cover_path.read_bytes()).hexdigest()
        return metadata
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        output_path.unlink(missing_ok=True)
        cover_path.unlink(missing_ok=True)
        raise ContractError("VIDEO_POSTPROCESS_FAILED", f"动态照片后处理失败：{type(exc).__name__}", 409) from exc


class DynamicPhotoH3:
    def __init__(self, sources: DynamicPhotoSources, client, controller):
        if client.kind != "dynamic_video":
            raise ValueError("动态照片需要独立 dynamic_video Comfy 客户端")
        self.sources = sources
        self.client = client
        self.controller = controller

    def _save(self, job: dict) -> None:
        path = self.sources.root / f"{job['id']}.json"
        temporary = path.with_name(f"{job['id']}.{uuid.uuid4().hex}.tmp")
        job["updatedAt"] = now()
        try:
            temporary.write_text(json.dumps(job, ensure_ascii=False))
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    async def _wait(self, prompt_id: str) -> bytes:
        missing = 0
        for _ in range(360):
            status, file = await self.client.result(prompt_id)
            if status == "completed" and file:
                return await self.client.download(file)
            if status == "failed":
                raise ContractError("H3_PROMPT_FAILED", "H3 工作流执行失败", 409)
            missing = missing + 1 if status == "missing" else 0
            if missing >= 4:
                raise ContractError("H3_PROMPT_MISSING", "已提交的 H3 prompt 不在队列或历史中", 409)
            await asyncio.sleep(5)
        raise ContractError("H3_TIMEOUT", "H3 工作流执行超时", 409)

    async def run(self, job_id: str) -> dict:
        """Called by the existing single worker in integration; never creates a scheduler."""
        job = self.sources.get(job_id)
        if not job:
            raise ContractError("JOB_NOT_FOUND", "动态照片任务不存在", 404)
        lock_path = self.sources.root / f"{job_id}.h3.lock"
        with lock_path.open("a+b") as lock:
            await asyncio.to_thread(fcntl.flock, lock, fcntl.LOCK_EX)
            try:
                job = self.sources.get(job_id)
                if job["status"] in {"succeeded", "failed", "skipped"}:
                    return job
                if job["status"] not in {"selected", "generating"}:
                    raise ContractError("JOB_STATE_INVALID", "任务尚未完成选图", 409)
                selection = job.get("selection") or {}
                photo_id = selection.get("selectedPhotoId")
                prompt = selection.get("motionPrompt")
                if (not isinstance(photo_id, str) or not isinstance(prompt, str)
                        or not 1 <= len(prompt.strip()) <= 500):
                    raise ContractError("SELECTION_INVALID", "选图结果缺少目标或运动描述", 409)
                source = next((item for item in job["sourceSnapshot"]["inputs"]
                               if item["photoId"] == photo_id), None)
                if source is None:
                    raise ContractError("SELECTION_INVALID", "所选照片不在冻结输入中", 409)
                image = self.sources.read_input(job, photo_id)
                intent = job.get("h3")
                if intent is None:
                    canvas = choose_canvas(source["width"], source["height"])
                    snapshot = self.client.freeze_workflow()
                    parameters = {"width": canvas["width"], "height": canvas["height"],
                                  "frames": FRAMES, "fps": FPS}
                    workflow_versions.validate_parameters(snapshot, parameters, 0)
                    intent = {"runnerVersion": RUNNER_VERSION, "photoId": photo_id,
                              "sourceSha256": source["sha256"], "canvas": canvas,
                              "workflowSnapshot": snapshot, "parameters": parameters,
                              "seed": secrets.randbits(64), "prompt": prompt,
                              "promptVersion": selection.get("promptVersion"),
                              "promptId": str(uuid.uuid4()), "submissionState": "prepared",
                              "createdAt": now()}
                    job["h3"] = intent
                    job["status"] = "generating"
                    self._save(job)  # Persist immutable graph, seed and prompt ID before submission.
                if (intent.get("runnerVersion") != RUNNER_VERSION or intent.get("photoId") != photo_id
                        or intent.get("sourceSha256") != source["sha256"] or intent.get("prompt") != prompt):
                    raise ContractError("H3_INTENT_CHANGED", "H3 冻结执行意图不匹配", 409)
                workflow_versions.validate_snapshot(intent["workflowSnapshot"], "dynamic_video")
                workflow_versions.validate_parameters(intent["workflowSnapshot"], intent["parameters"], intent["seed"])
                job_dir = self.sources.root / job_id
                final = job_dir / "dynamic.mp4"
                cover = job_dir / "cover.jpg"
                if final.is_file() and cover.is_file():
                    metadata = inspect_video(final, intent["canvas"]["width"], intent["canvas"]["height"])
                    metadata["coverSha256"] = hashlib.sha256(cover.read_bytes()).hexdigest()
                    return self._complete(job, intent, metadata)
                async with self.controller.use("video"):
                    submission_state = intent.get("submissionState")
                    if submission_state not in {"prepared", "submitting", "submitted"}:
                        raise ContractError("H3_INTENT_INVALID", "H3 提交状态无效", 409)
                    if submission_state == "prepared":
                        # This durable state means no outbound call has started yet.
                        intent["submissionState"] = "submitting"
                        intent["submissionStartedAt"] = now()
                        self._save(job)
                        accepted = await self.client.queue(image, prompt, intent["seed"],
                                                           workflow_snapshot=intent["workflowSnapshot"],
                                                           parameters=intent["parameters"],
                                                           prompt_id=intent["promptId"])
                        if accepted != intent["promptId"]:
                            raise ContractError("H3_PROMPT_ID_MISMATCH", "H3 prompt ID 不匹配", 409)
                        intent["submissionState"] = "submitted"
                        intent["submittedAt"] = now()
                        self._save(job)
                    else:
                        status, _ = await self.client.result(intent["promptId"])
                        if status == "missing":
                            raise ContractError("H3_SUBMISSION_UNKNOWN", "H3 提交状态不明，禁止自动重投", 409)
                        if status == "failed":
                            raise ContractError("H3_PROMPT_FAILED", "H3 工作流执行失败", 409)
                        if submission_state == "submitting":
                            intent["submissionState"] = "submitted"
                            intent["submittedAt"] = now()
                            self._save(job)
                    raw = await self._wait(intent["promptId"])
                raw_path = job_dir / "dynamic.raw.mp4"
                raw_path.write_bytes(raw)
                os.chmod(raw_path, 0o600)
                metadata = finish_video(raw_path, final, cover,
                                        intent["canvas"]["width"], intent["canvas"]["height"])
                raw_path.unlink(missing_ok=True)
                return self._complete(job, intent, metadata)
            except Exception as exc:
                job = self.sources.get(job_id) or job
                if job["status"] != "succeeded":
                    job["status"] = "failed"
                    job["error"] = {"code": exc.code if isinstance(exc, ContractError) else "H3_UNEXPECTED",
                                    "message": str(exc)[:200] if isinstance(exc, ContractError) else type(exc).__name__}
                    self._save(job)
                return job
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _complete(self, job: dict, intent: dict, metadata: dict) -> dict:
        job["status"] = "succeeded"
        job["error"] = None
        job["result"] = {"photoId": intent["photoId"], "sourceVariant": next(
            item["sourceVariant"] for item in job["sourceSnapshot"]["inputs"]
            if item["photoId"] == intent["photoId"]),
            "videoPath": f"{job['id']}/dynamic.mp4", "coverPath": f"{job['id']}/cover.jpg",
            "canvas": intent["canvas"], "media": metadata, "workflowId": intent["workflowSnapshot"]["workflow_id"],
            "workflowVersion": intent["workflowSnapshot"]["workflow_version"],
            "workflowHash": intent["workflowSnapshot"]["workflow_hash"],
            "seed": intent["seed"], "promptId": intent["promptId"],
            "promptVersion": intent["promptVersion"], "completedAt": now()}
        self._save(job)
        return job
