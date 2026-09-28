"""Private HTTP calls to Spark's existing Node.js data service."""
from __future__ import annotations

import os

import httpx


def _endpoint(env_name: str) -> str:
    endpoint = os.getenv(env_name, "").rstrip("/")
    if not endpoint:
        raise RuntimeError(f"{env_name} 未配置")
    if not (endpoint.startswith("http://127.0.0.1:") or endpoint.startswith("http://localhost:")
            or endpoint.startswith("https://") or ".ts.net:" in endpoint):
        raise ValueError("Spark 数据 API 必须使用本机隧道、HTTPS 或 Tailscale 私网")
    return endpoint


async def get_configured(env_name: str, timeout: float = 5) -> dict:
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=3)) as client:
        response = await client.get(_endpoint(env_name))
        response.raise_for_status()
        data = response.json()
    if not isinstance(data, dict) or not data.get("ok"):
        raise RuntimeError("Spark 状态响应无效")
    return data


async def post_configured(env_name: str, payload: dict, timeout: float = 95) -> dict:
    endpoint = _endpoint(env_name)
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=8)) as client:
        response = await client.post(endpoint, json=payload)
        response.raise_for_status()
        data = response.json()
    if not isinstance(data, dict) or data.get("error"):
        raise RuntimeError(str(data.get("error") if isinstance(data, dict) else "Spark 数据响应无效"))
    return data
