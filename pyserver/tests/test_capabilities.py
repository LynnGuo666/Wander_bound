import asyncio

import httpx

from pyserver.api import core
from pyserver.app import create_app
from pyserver.media import MediaStore
from pyserver.settings import ConfigStore
from pyserver.trips import TripStore


def test_capabilities_use_live_docker_tools_and_remote_credential_status(tmp_path, monkeypatch):
    async def tools(endpoint):
        return {"kind": "MCP", "discovery": "runtime", "tools": [
            {"name": "dida_search_hotels", "description": "verified", "inputSchema": {"type": "object"}}]}

    async def remote(env_name):
        assert env_name == "TRAVEL_SPARK_HEALTH_URL"
        return {"ok": True, "providers": {"dida": {"configured": True}, "tuniu": {"configured": True}}}

    monkeypatch.setattr(core, "list_mcp_tools", tools)
    monkeypatch.setattr(core, "get_configured", remote)
    app = create_app(config=ConfigStore(tmp_path / "config.yml"), trips=TripStore(tmp_path / "trips"),
                     media=MediaStore(tmp_path / "media"))

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            data = (await client.post("/api/capabilities", json={})).json()
            assert data["providers"]["dida"]["configured"] is True
            assert data["providers"]["tuniu"]["configured"] is True
            assert data["connections"]["dida"]["tools"][0]["name"] == "dida_search_hotels"

    asyncio.run(scenario())
