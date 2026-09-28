import asyncio

from pyserver.providers import attractions, mcp, stays, transport


def test_python_data_providers_call_only_mcp_tools(monkeypatch):
    calls = []

    async def fake_call(endpoint, name, args, **kwargs):
        calls.append((endpoint, name, args, kwargs))
        if name == "travel_search_transport":
            return {"ok": True, "outboundFlights": [], "returnFlights": [], "outboundTrains": [], "returnTrains": []}
        if name == "travel_search_stays":
            return {"ok": True, "hotels": []}
        return {"ok": True, "offers": []}

    monkeypatch.setenv("TRAVEL_DATA_MCP_URL", "http://127.0.0.1:14179/mcp")
    for module in (transport, stays, attractions):
        monkeypatch.setattr(module, "mcp_call", fake_call)

    async def scenario():
        await transport.search_transport("深圳", "上海", "2026-10-10", 2, {"tuniu": "test-key"}, {})
        await stays.search_stays("深圳", "南山", "2026-10-10", 1, 600, {"dida": "test-token"})
        await attractions.search_attractions("深圳", [], {"tuniu": "test-key"}, {})

    asyncio.run(scenario())
    assert [call[1] for call in calls] == ["travel_search_transport", "travel_search_stays", "travel_search_attractions"]
    assert calls[0][3]["credentials"]["tuniu"] == "test-key"
    assert calls[1][3]["credentials"]["dida"] == "test-token"


def test_data_endpoint_rejects_untrusted_plain_http(monkeypatch):
    monkeypatch.setenv("TRAVEL_DATA_MCP_URL", "http://example.com/mcp")
    try:
        mcp.data_endpoint()
        assert False, "untrusted endpoint should fail"
    except ValueError:
        pass
