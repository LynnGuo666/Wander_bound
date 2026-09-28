"""Read-only model telemetry and authenticated local model controls."""
from __future__ import annotations

import os

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from ..accounts import require_admin
from ..media.jobs import JobStore
from .controller import ModelController


def router_for(controller: ModelController, jobs: JobStore) -> APIRouter:
    router = APIRouter()

    @router.get("/api/inference/status")
    async def status(request: Request):
        require_admin(request)
        result = await controller.status()
        pending = jobs.pending()
        result["queue"] = {"total": len(pending), "image": sum(job["kind"] in {"edit", "scrapbook"} for job in pending),
                           "video": sum(job["kind"] == "memory" for job in pending),
                           "jobs": [{key: job.get(key) for key in ("id", "kind", "status", "progressLabel", "progressPercent", "completedClips")}
                                    for job in pending]}
        return result

    @router.post("/api/inference/models/{name}/warm")
    async def warm(name: str, request: Request):
        require_admin(request)
        if jobs.pending():
            raise HTTPException(409, "媒体任务排队中，请等待任务完成")
        try:
            controller.begin_warm(name)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from exc
        return JSONResponse(await controller.status(), status_code=202)

    @router.post("/api/inference/models/{name}/release")
    async def release(name: str, request: Request):
        require_admin(request)
        kinds = {"image": {"edit", "scrapbook"}, "video": {"memory"}}.get(name, set())
        if any(job["kind"] in kinds for job in jobs.pending()):
            raise HTTPException(409, "该模型仍有待处理任务")
        try:
            await controller.release(name)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from exc
        return await controller.status()

    @router.post("/api/inference/chat")
    async def chat(request: Request, payload: dict):
        require_admin(request)
        if jobs.pending():
            raise HTTPException(409, "媒体任务排队中，请等待任务完成")
        message = str(payload.get("message") or "").strip()
        if not message or len(message) > 4000:
            raise HTTPException(400, "请输入不超过 4000 字的测试消息")
        try:
            async with controller.use("chat") as spec:
                async with httpx.AsyncClient(timeout=300) as client:
                    response = await client.post(spec.url.rstrip("/") + "/v1/chat/completions", json={
                        "model": os.getenv("SPARK_QWEN38_MODEL", "qwen38-27b"),
                        "messages": [{"role": "user", "content": message}], "max_tokens": 512, "stream": False,
                        "chat_template_kwargs": {"enable_thinking": False}})
                response.raise_for_status()
                body = response.json()
                return {"model": body.get("model"), "message": (body.get("choices") or [{}])[0].get("message", {}).get("content", ""),
                        "usage": body.get("usage")}
        except (RuntimeError, httpx.HTTPError, ValueError) as exc:
            raise HTTPException(503, str(exc)[:200]) from exc

    return router
