import asyncio

import httpx

from pyserver.api import core
from pyserver.app import create_app
from pyserver.media import MediaStore
from pyserver.settings import ConfigStore
from pyserver.trips import TripStore


def test_capabilities_use_live_docker_tools(tmp_path, monkeypatch):
    async def tools(endpoint):
        return {"kind": "MCP", "discovery": "runtime", "tools": [
            {"name": "dida_search_hotels", "description": "verified", "inputSchema": {"type": "object"}}]}

    monkeypatch.setattr(core, "list_mcp_tools", tools)
    monkeypatch.setenv("TRAVEL_DATA_MCP_URL", "http://127.0.0.1:14179/mcp")
    app = create_app(config=ConfigStore(tmp_path / "config.yml"), trips=TripStore(tmp_path / "trips"),
                     media=MediaStore(tmp_path / "media"))

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            data = (await client.post("/api/capabilities", json={})).json()
            assert data["connections"]["dida"]["tools"][0]["name"] == "dida_search_hotels"
            assert data["connections"]["travelData"]["discovery"] == "runtime"

    asyncio.run(scenario())
