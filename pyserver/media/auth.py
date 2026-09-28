"""Bearer authentication for private media operations."""
from __future__ import annotations

from fastapi import Request
from ..accounts import require_user

def require_media_auth(request: Request) -> None:
    require_user(request)
