"""Server-side bridge to the Spark JavaScript transport data service."""
from __future__ import annotations

from .js_api import post_configured


async def search_transport(origin: str, destination: str, start_date: str, days: int,
                           credentials: dict, priorities: dict) -> dict:
    data = await post_configured("TRAVEL_DATA_API_URL", {"originCity": origin, "destination": destination,
                                                        "startDate": start_date, "days": days,
                                                        "credentials": {key: credentials[key] for key in ("tuniu", "flyai", "duffel") if credentials.get(key)},
                                                        "priorities": priorities})
    if not data.get("ok"):
        raise RuntimeError(data.get("error") or data.get("message") or "交通数据服务未完成")
    for field in ("outboundFlights", "returnFlights", "outboundTrains", "returnTrains"):
        if not isinstance(data.get(field), list):
            raise RuntimeError(f"交通数据服务缺少 {field}")
    return data
