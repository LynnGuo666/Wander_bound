"""Bearer authentication for private media operations."""
from __future__ import annotations

import hmac
import os
from fastapi import HTTPException, Request

def require_media_auth(request: Request) -> None:
    token = os.getenv("MEDIA_API_TOKEN", "")
    if not token:
        raise HTTPException(503, "媒体服务尚未配置访问令牌")
    if not hmac.compare_digest(request.headers.get("Authorization", ""), f"Bearer {token}"):
        raise HTTPException(401, "媒体服务需要有效令牌")
