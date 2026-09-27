"""HTTP adapters for the existing DGX Spark ComfyUI services."""
from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from pathlib import Path
from urllib.parse import urlparse

import httpx

FILE = re.compile(r"^[\w. -]{1,180}$")


def _replace(value, mapping):
    if isinstance(value, str):
        return mapping.get(value, value)
    if isinstance(value, list):
        return [_replace(item, mapping) for item in value]
    if isinstance(value, dict):
        return {key: _replace(item, mapping) for key, item in value.items()}
    return value


class ComfyClient:
    def __init__(self, base_url: str, workflow_file: str | Path, kind: str):
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not (parsed.hostname in {"localhost", "127.0.0.1", "::1"} or (parsed.hostname or "").endswith(".ts.net")):
            raise ValueError("ComfyUI 地址只能是本机隧道或 Tailscale 私网")
        self.base_url = base_url.rstrip("/")
        self.workflow_file = Path(workflow_file)
        self.kind = kind

    @property
    def configured(self) -> bool:
        return self.workflow_file.is_file()

    async def probe(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.base_url}/system_stats")
            return response.status_code == 200 and bool(response.json().get("devices"))
        except (httpx.HTTPError, ValueError):
            return False

    async def queue(self, image: bytes, prompt: str, seed: int | None = None) -> str:
        if not self.configured:
            raise RuntimeError("工作流文件未配置")
        async with httpx.AsyncClient(timeout=35) as client:
            upload = await client.post(f"{self.base_url}/upload/image", files={"image": (f"travel-{uuid.uuid4()}.jpg", image, "image/jpeg")},
                                       data={"overwrite": "false"})
            upload.raise_for_status()
            name = upload.json().get("name", "")
            if not FILE.fullmatch(name):
                raise RuntimeError("ComfyUI 未返回有效图片名")
            workflow = json.loads(self.workflow_file.read_text())
            text = f"<image1> {prompt}" if self.kind == "image" and "<image1>" not in prompt else prompt
            workflow = _replace(workflow, {"__TRAVEL_IMAGE__": name, "__TRAVEL_PROMPT__": text,
                                           "__TRAVEL_SEED__": seed if seed is not None else 0})
            queued = await client.post(f"{self.base_url}/prompt", json={"prompt": workflow, "client_id": str(uuid.uuid4())})
            queued.raise_for_status()
            body = queued.json()
            if not body.get("prompt_id") or body.get("error"):
                raise RuntimeError(f"ComfyUI 拒绝工作流：{body.get('error')}")
            return body["prompt_id"]

    async def result(self, prompt_id: str) -> tuple[str, dict | None]:
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.get(f"{self.base_url}/history/{prompt_id}")
            response.raise_for_status()
            record = response.json().get(prompt_id)
            if not record:
                queue = (await client.get(f"{self.base_url}/queue")).json()
                waiting = any(item[1] == prompt_id for item in [*(queue.get("queue_running") or []), *(queue.get("queue_pending") or [])])
                return ("running" if waiting else "missing"), None
            if record.get("status", {}).get("status_str") == "error":
                return "failed", None
            files = [file for output in record.get("outputs", {}).values() for group in ("images", "videos", "gifs") for file in output.get(group, [])]
            extension = ".mp4" if self.kind == "video" else (".png", ".jpg", ".jpeg", ".webp")
            file = next((file for file in files if str(file.get("filename", "")).lower().endswith(extension)), None)
            return ("completed", file) if file else ("failed" if record.get("status", {}).get("completed") else "running", None)

    async def download(self, file: dict) -> bytes:
        name = file.get("filename", "")
        if not FILE.fullmatch(name):
            raise RuntimeError("ComfyUI 输出文件名无效")
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.get(f"{self.base_url}/view", params={"filename": name, "subfolder": file.get("subfolder", ""), "type": file.get("type", "output")})
            response.raise_for_status()
            return response.content


def configured_clients() -> tuple[ComfyClient | None, ComfyClient | None]:
    image_url = os.getenv("SPARK_QWEN_COMFY_URL", "")
    video_url = os.getenv("SPARK_COMFY_URL", "")
    image = ComfyClient(image_url, os.getenv("SPARK_QWEN_IMAGE_WORKFLOW_FILE", "workflows/qwen-image-2.1-edit-api.json"), "image") if image_url else None
    video = ComfyClient(video_url, os.getenv("SPARK_H3_WORKFLOW_FILE", "workflows/minimax-h3-i2v-api.json"), "video") if video_url else None
    return image, video
