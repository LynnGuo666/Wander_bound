"""Private, durable Qwen text-to-image sticker jobs for journal pages."""
from __future__ import annotations

import asyncio
import io
import json
import os
import secrets
import uuid
from pathlib import Path

from PIL import Image

from ..trips import now
from ..inference import ModelController
from .comfy import ComfyClient


def public(job: dict) -> dict:
    return {key: job.get(key) for key in ("id", "tripId", "kind", "motif", "status", "createdAt", "error")}


class StickerStore:
    def __init__(self, root: Path, client: ComfyClient | None, controller: ModelController):
        self.root = root
        self.client = client
        self.controller = controller
        self.worker: asyncio.Task | None = None
        self.prompt_dir = Path(__file__).resolve().parents[2] / "prompts"

    def get(self, sticker_id: str) -> dict | None:
        try:
            if str(uuid.UUID(sticker_id)) != sticker_id:
                return None
            return json.loads((self.root / f"{sticker_id}.json").read_text())
        except (ValueError, FileNotFoundError, json.JSONDecodeError):
            return None

    def list_for_trip(self, trip_id: str) -> list[dict]:
        if not self.root.exists():
            return []
        items = (self.get(path.stem) for path in self.root.glob("*.json"))
        return sorted((public(item) for item in items if item and item.get("tripId") == trip_id),
                      key=lambda item: item["createdAt"], reverse=True)

    def save(self, job: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        target = self.root / f"{job['id']}.json"
        temporary = self.root / f"{job['id']}.{uuid.uuid4().hex}.tmp"
        try:
            temporary.write_text(json.dumps(job, ensure_ascii=False))
            os.chmod(temporary, 0o600)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    def submit(self, trip_id: str, city: str, motif: str, kind: str = "sticker") -> dict:
        if not self.client or not self.client.configured:
            raise ValueError("Qwen 贴纸工作流尚未配置")
        if kind not in {"sticker", "stamp"}:
            raise ValueError("素材类型必须为 sticker 或 stamp")
        if (not isinstance(motif, str) or not 2 <= len(motif.strip()) <= 80
                or any(ord(char) < 32 for char in motif)):
            raise ValueError("贴纸主题须为 2–80 个字符")
        existing = next((item for item in self.list_for_trip(trip_id)
                         if item["kind"] == kind and item["motif"] == motif.strip()
                         and item["status"] in {"queued", "running", "succeeded"}), None)
        if existing:
            return existing
        if len(self.list_for_trip(trip_id)) >= 40:
            raise ValueError("每趟旅程最多保存 40 枚 AI 素材")
        spec_file = self.prompt_dir / f"journal-{kind}.qwen-image-2.1.json"
        spec = json.loads(spec_file.read_text())
        graph = json.loads(self.client.workflow_file.read_text())
        if (graph.get("6", {}).get("class_type") != "EmptyLatentImage"
                or graph.get("6", {}).get("inputs", {}).get("width") != 1024
                or graph.get("6", {}).get("inputs", {}).get("height") != 1024):
            raise ValueError("贴纸文生图工作流无效")
        prompt = spec["promptTemplate"].replace("{{city}}", city[:80]).replace("{{motif}}", motif.strip())
        job = {"id": str(uuid.uuid4()), "tripId": trip_id, "kind": kind, "motif": motif.strip(),
               "status": "queued", "createdAt": now(), "seed": secrets.randbits(64),
               "prompt": prompt, "promptVersion": spec["id"], "workflow": graph,
               "promptId": str(uuid.uuid4()), "error": None}
        self.save(job)
        self.schedule()
        return public(job)

    def schedule(self) -> None:
        if self.worker is None or self.worker.done():
            self.worker = asyncio.create_task(self._drain())

    async def resume(self) -> None:
        if self.root.exists() and any((item := self.get(path.stem)) and item.get("status") in {"queued", "running"}
                                      for path in self.root.glob("*.json")):
            self.schedule()

    async def close(self) -> None:
        if self.worker and not self.worker.done():
            self.worker.cancel()
            try:
                await self.worker
            except asyncio.CancelledError:
                pass

    async def _drain(self) -> None:
        while True:
            pending = sorted((item for path in self.root.glob("*.json")
                              if (item := self.get(path.stem)) and item.get("status") in {"queued", "running"}),
                             key=lambda item: (item["createdAt"], item["id"]))
            if not pending:
                return
            job = pending[0]
            try:
                await self._run(job)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                job.update(status="failed", error=str(exc)[:200])
                self.save(job)

    async def _run(self, job: dict) -> None:
        if not self.client:
            raise RuntimeError("Qwen 贴纸工作流尚未配置")
        job["status"] = "running"
        self.save(job)
        async with self.controller.use("image"):
            state, file = await self.client.result(job["promptId"])
            if state == "missing":
                await self.client.queue_text(job["prompt"], job["seed"],
                                             graph=job["workflow"], prompt_id=job["promptId"])
            elif state == "failed":
                raise RuntimeError("Qwen 贴纸生成失败")
            for _ in range(120):
                state, file = await self.client.result(job["promptId"])
                if state == "completed":
                    break
                if state in {"failed", "missing"}:
                    raise RuntimeError("Qwen 贴纸任务中断")
                await asyncio.sleep(5)
            else:
                raise TimeoutError("Qwen 贴纸生成超时")
            data = await self.client.download(file)
            with Image.open(io.BytesIO(data)) as image:
                if image.format != "PNG" or image.mode != "RGBA" or max(image.size) > 2048:
                    raise RuntimeError("Qwen 未返回透明 PNG 贴纸")
                minimum, maximum = image.getchannel("A").getextrema()
                if minimum > 16 or maximum < 200:
                    raise RuntimeError("Qwen 输出没有可用的透明区域")
                visible = image.getchannel("A").point(lambda value: 255 if value > 16 else 0)
                bounds = visible.getbbox()
                if not bounds or (bounds[2] - bounds[0]) < 80 or (bounds[3] - bounds[1]) < 80:
                    raise RuntimeError("Qwen 输出的贴纸主体过小")
                padding = round(max(bounds[2] - bounds[0], bounds[3] - bounds[1]) * 0.045)
                bounds = (max(0, bounds[0] - padding), max(0, bounds[1] - padding),
                          min(image.width, bounds[2] + padding), min(image.height, bounds[3] + padding))
                rendered = io.BytesIO()
                image.crop(bounds).save(rendered, format="PNG", optimize=True)
            output = self.root / f"{job['id']}.png"
            temporary = self.root / f"{job['id']}.{uuid.uuid4().hex}.tmp"
            try:
                temporary.write_bytes(rendered.getvalue())
                os.chmod(temporary, 0o600)
                os.replace(temporary, output)
            finally:
                temporary.unlink(missing_ok=True)
            job.update(status="succeeded", error=None)
            self.save(job)
