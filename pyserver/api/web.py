"""Built React frontend static files."""
from __future__ import annotations

from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

def router_for() -> APIRouter:
    router = APIRouter()
    @router.get("/")
    async def index():
        file = Path("dist/index.html")
        if not file.exists():
            raise HTTPException(404, "前端尚未构建；运行 npm run build")
        return FileResponse(file)

    @router.get("/{asset_path:path}")
    async def assets(asset_path: str):
        root = Path("dist").resolve()
        file = (root / asset_path).resolve()
        if not file.is_relative_to(root) or not file.is_file():
            raise HTTPException(404, "文件不存在")
        return FileResponse(file)

    return router
