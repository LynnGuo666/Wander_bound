"""Private HTTP calls to Spark's existing Node.js data service."""
from __future__ import annotations

import os

import httpx


async def post_configured(env_name: str, payload: dict, timeout: float = 95) -> dict:
    endpoint = os.getenv(env_name, "").rstrip("/")
    if not endpoint:
        raise RuntimeError(f"{env_name} 未配置")
    if not (endpoint.startswith("http://127.0.0.1:") or endpoint.startswith("http://localhost:")
            or endpoint.startswith("https://") or ".ts.net:" in endpoint):
        raise ValueError("Spark 数据 API 必须使用本机隧道、HTTPS 或 Tailscale 私网")
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=8)) as client:
        response = await client.post(endpoint, json=payload)
        response.raise_for_status()
        data = response.json()
    if not isinstance(data, dict) or data.get("error"):
        raise RuntimeError(str(data.get("error") if isinstance(data, dict) else "Spark 数据响应无效"))
    return data
