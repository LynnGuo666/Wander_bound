"""Dispatch server-owned agent tools by feature."""
from __future__ import annotations

from . import spec, discovery, planning
from .state import _error

async def execute(name: str, args: dict, state: dict, credentials: dict, request: dict, priorities: dict | None = None) -> dict:
    match name:
        case "set_trip_spec": return await spec.set_trip_spec(args, state, request)
        case "ask_question": return await spec.ask_question(args, state)
        case "resolve_origin": return await spec.resolve_origin(state)
        case "discover_places": return await discovery.discover_places(args, state, credentials)
        case "search_transport": return await discovery.search_transport(state, credentials, priorities or {})
        case "search_stays": return await discovery.search_stays(state)
        case "draft_plan": return await planning.draft_plan(args, state)
        case _: return _error("unknown_tool", "未知工具")
