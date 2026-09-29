"""Private, durable Qwen text-to-image sticker jobs for journal pages."""
from __future__ import annotations

import asyncio
import io
import json
import os
import secrets
import uuid
from collections import deque
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter

from ..trips import now
from ..inference import ModelController
from .comfy import ComfyClient


def isolate_sticker(image: Image.Image) -> Image.Image:
    """Discard distant transparent-background artifacts before cropping the main motif."""
    if image.mode != "RGBA":
        raise RuntimeError("Qwen 未返回透明 PNG 贴纸")
    width, height = image.size
    alpha = image.getchannel("A")
    raw = alpha.tobytes()
    if min(raw) > 16 or max(raw) < 200:
        raise RuntimeError("Qwen 输出没有可用的透明区域")
    visited = bytearray(width * height)
    components: list[tuple[list[int], tuple[int, int, int, int]]] = []
    for start, value in enumerate(raw):
        if value <= 16 or visited[start]:
            continue
        queue = deque([start])
        visited[start] = 1
        points = []
        left = right = start % width
        top = bottom = start // width
        while queue:
            index = queue.popleft()
            points.append(index)
            x, y = index % width, index // width
            left, right = min(left, x), max(right, x)
            top, bottom = min(top, y), max(bottom, y)
            for yy in range(max(0, y - 1), min(height, y + 2)):
                for xx in range(max(0, x - 1), min(width, x + 2)):
                    neighbor = yy * width + xx
                    if raw[neighbor] > 16 and not visited[neighbor]:
                        visited[neighbor] = 1
                        queue.append(neighbor)
        components.append((points, (left, top, right + 1, bottom + 1)))
    if not components:
        raise RuntimeError("Qwen 输出没有贴纸主体")
    components.sort(key=lambda item: len(item[0]), reverse=True)
    main_points, main_box = components[0]
    if len(main_points) > width * height * .85:
        raise RuntimeError("Qwen 输出接近整张不透明背景")
    if main_box[2] - main_box[0] < 80 or main_box[3] - main_box[1] < 80:
        raise RuntimeError("Qwen 输出的贴纸主体过小")
    keep = bytearray(width * height)
    for point in main_points:
        keep[point] = 255
    # Nearby, substantial fragments can belong to the same motif; remote specks do not.
    for points, box in components[1:]:
        gap = max(main_box[0] - box[2], box[0] - main_box[2],
                  main_box[1] - box[3], box[1] - main_box[3], 0)
        if len(points) >= max(30, len(main_points) * .008) and gap < max(width, height) * .04:
            for point in points:
                keep[point] = 255
    nearby = Image.frombytes("L", (width, height), bytes(keep)).filter(ImageFilter.MaxFilter(5))
    clean = image.copy()
    clean.putalpha(ImageChops.multiply(alpha, nearby))
    bounds = clean.getchannel("A").getbbox()
    if not bounds:
        raise RuntimeError("Qwen 输出没有可用的贴纸")
    padding = round(max(bounds[2] - bounds[0], bounds[3] - bounds[1]) * .045)
    return clean.crop((max(0, bounds[0] - padding), max(0, bounds[1] - padding),
                       min(width, bounds[2] + padding), min(height, bounds[3] + padding)))


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
        except (ValueError, TypeError, AttributeError, FileNotFoundError, json.JSONDecodeError):
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
        if kind not in {"sticker", "stamp", "postcard", "illustration"}:
            raise ValueError("素材类型必须为 sticker、stamp、postcard 或 illustration")
        if (not isinstance(motif, str) or not 2 <= len(motif.strip()) <= 80
                or any(ord(char) < 32 for char in motif)):
            raise ValueError("贴纸主题须为 2–80 个字符")
        spec_file = self.prompt_dir / f"journal-{kind}.qwen-image-2.1.json"
        spec = json.loads(spec_file.read_text())
        existing_items = self.list_for_trip(trip_id)
        for item in existing_items:
            if (item["kind"] == kind and item["motif"] == motif.strip()
                    and item["status"] in {"queued", "running", "succeeded"}):
                stored = self.get(item["id"])
                if stored and stored.get("promptVersion") == spec["id"]:
                    return item
        if len(existing_items) >= 60:
            raise ValueError("每趟旅程最多保存 60 枚 AI 素材")
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
                if image.format != "PNG" or max(image.size) > 2048:
                    raise RuntimeError("Qwen 未返回可用的 PNG 素材")
                if job["kind"] in {"sticker", "stamp"}:
                    image = isolate_sticker(image)
                rendered = io.BytesIO()
                image.save(rendered, format="PNG", optimize=True)
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
