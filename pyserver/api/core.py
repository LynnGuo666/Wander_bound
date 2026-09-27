"""Health, settings, and live MCP capability discovery."""
from __future__ import annotations

import os
import asyncio
from fastapi import APIRouter
from ..settings import ConfigStore
from ..providers import list_mcp_tools
from ..trips import now

def router_for(config: ConfigStore) -> APIRouter:
    router = APIRouter()
    @router.get("/api/health")
    async def health():
        keys = config.credentials()
        ota = bool(os.getenv("TRAVEL_OTA_MCP_URL"))
        return {"ok": True, "runtime": "python-fastapi", "model": {"id": "step-5-preview", "configured": bool(keys["stepfun"]), "channel": "step-plan"},
                "providers": {"amap": {"configured": bool(keys["amap"]), "label": "高德地点与路线"},
                              "dida": {"configured": bool(keys["dida"]), "label": "道旅酒店"},
                              "duffel": {"configured": bool(keys["duffel"]), "label": "Duffel 航班"},
                              "tuniu": {"configured": ota and bool(keys["tuniu"]), "label": "途牛 · OTA MCP"},
                              "flyai": {"configured": ota, "label": "飞猪 · OTA MCP"},
                              "rail12306": {"configured": bool(os.getenv("TRAVEL_12306_MCP_URL")), "label": "12306 MCP（社区）"}}}

    @router.post("/api/capabilities")
    async def capabilities(payload: dict):
        keys = config.credentials(payload.get("credentials"))
        ota, rail, dida = await asyncio.gather(list_mcp_tools(os.getenv("TRAVEL_OTA_MCP_URL")),
                                               list_mcp_tools(os.getenv("TRAVEL_12306_MCP_URL")),
                                               list_mcp_tools(os.getenv("TRAVEL_DIDA_MCP_URL")))
        current = await health()
        return {"checkedAt": now(), "providers": current["providers"], "connections": {"ota": ota, "rail": rail, "dida": dida}}

    return router
