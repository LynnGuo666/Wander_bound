"""Separate administrator authorization for provider credentials."""
from __future__ import annotations

from fastapi import Request
from ..accounts import require_admin


def require_admin_auth(request: Request) -> None:
    require_admin(request)
