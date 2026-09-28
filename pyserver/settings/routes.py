"""Read and update local YAML settings."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from .store import ConfigStore
from .auth import require_admin_auth

def router_for(config: ConfigStore) -> APIRouter:
    router = APIRouter()
    @router.get("/api/settings")
    async def get_settings(request: Request):
        require_admin_auth(request)
        return config.public()

    @router.put("/api/settings")
    async def put_settings(patch: dict, request: Request):
        require_admin_auth(request)
        try:
            return config.update(patch)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    return router
