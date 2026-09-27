"""Server-side bridge to the Spark JavaScript transport data service."""
from __future__ import annotations

import os

import httpx


async def search_transport(origin: str, destination: str, start_date: str, days: int,
                           credentials: dict, priorities: dict) -> dict:
    endpoint = os.getenv("TRAVEL_DATA_API_URL", "").rstrip("/")
    if not endpoint:
        raise RuntimeError("DGX Spark 交通数据 API 未配置")
    if not (endpoint.startswith("http://127.0.0.1:") or endpoint.startswith("http://localhost:")
            or endpoint.startswith("https://") or endpoint.endswith(".ts.net")):
        raise ValueError("交通数据 API 必须使用本机隧道、HTTPS 或 Tailscale 私网")
    async with httpx.AsyncClient(timeout=httpx.Timeout(95, connect=8)) as client:
        response = await client.post(endpoint, json={"originCity": origin, "destination": destination,
                                                     "startDate": start_date, "days": days,
                                                     "credentials": {key: credentials[key] for key in ("tuniu", "flyai", "duffel") if credentials.get(key)},
                                                     "priorities": priorities})
        response.raise_for_status()
        data = response.json()
    if not data.get("ok"):
        raise RuntimeError(data.get("error") or data.get("message") or "交通数据服务未完成")
    for field in ("outboundFlights", "returnFlights", "outboundTrains", "returnTrains"):
        if not isinstance(data.get(field), list):
            raise RuntimeError(f"交通数据服务缺少 {field}")
    return data
