"""Health, settings, and live MCP capability discovery."""
from __future__ import annotations

import os
import asyncio
from fastapi import APIRouter
from ..settings import ConfigStore
from ..providers import list_mcp_tools
from ..providers.js_api import get_configured
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
        ota, rail, dida, remote = await asyncio.gather(list_mcp_tools(os.getenv("TRAVEL_OTA_MCP_URL")),
                                                       list_mcp_tools(os.getenv("TRAVEL_12306_MCP_URL")),
                                                       list_mcp_tools(os.getenv("TRAVEL_DIDA_MCP_URL")),
                                                       get_configured("TRAVEL_SPARK_HEALTH_URL"), return_exceptions=True)
        current = await health()
        if isinstance(remote, dict):
            for name, status in remote.get("providers", {}).items():
                if name in current["providers"] and isinstance(status, dict) and status.get("configured"):
                    current["providers"][name]["configured"] = True
        return {"checkedAt": now(), "providers": current["providers"], "connections": {"ota": ota, "rail": rail, "dida": dida}}

    return router
