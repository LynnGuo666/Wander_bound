"""Transport through Spark's travel-data MCP tool."""
from __future__ import annotations

from .mcp import data_endpoint, mcp_call


async def search_transport(origin: str, destination: str, start_date: str, days: int,
                           credentials: dict, priorities: dict) -> dict:
    data = await mcp_call(data_endpoint(), "travel_search_transport", {"originCity": origin, "destination": destination,
                          "startDate": start_date, "days": days, "priorities": priorities}, credentials=credentials)
    if not data.get("ok"):
        raise RuntimeError(data.get("error") or data.get("message") or "交通数据服务未完成")
    for field in ("outboundFlights", "returnFlights", "outboundTrains", "returnTrains"):
        if not isinstance(data.get(field), list):
            raise RuntimeError(f"交通数据服务缺少 {field}")
    return data
