import asyncio
import io
from pathlib import Path

import httpx
from PIL import Image

from pyserver import agent
from pyserver.app import create_app
from pyserver.settings import ConfigStore
from pyserver.media import MediaStore
from pyserver.trips import TripStore
from pyserver.agent.spec import set_trip_spec
from pyserver import providers
from pyserver.providers import amap


def call(name, args, call_id):
    import json
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}}


def test_question_answer_updates_memory_and_preserves_history(tmp_path, monkeypatch):
    config = ConfigStore(tmp_path / "config.yml")
    config.update({"credentials": {"stepfun": "test-secret"}})
    trips = TripStore(tmp_path / "trips")
    app = create_app(config=config, trips=trips, media=MediaStore(tmp_path / "media"))
    script = [
        [call("ask_question", {"question": "从哪里出发？", "options": [{"id": "cc", "label": "长春"}, {"id": "sh", "label": "上海"}]}, "q1")],
        [call("set_trip_spec", {"originCity": "长春"}, "spec1")],
        [call("ask_question", {"question": "哪天出发？", "options": [{"id": "d1", "label": "2026-10-01"}, {"id": "d2", "label": "2026-10-02"}]}, "q2")],
    ]
    seen = []
    async def fake_complete(messages, tools, key, **kwargs):
        seen.append({"messages": list(messages), "tools": [item["function"]["name"] for item in tools]})
        calls = script[len(seen) - 1]
        yield {"type": "completion", "message": {"role": "assistant", "content": None, "tool_calls": calls},
               "finishReason": "tool_calls", "usage": {"prompt_tokens": 20, "completion_tokens": 10}, "publicNote": ""}
    monkeypatch.setattr(agent.step, "complete", fake_complete)

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            first = (await client.post("/api/plan", json={"query": "安排旅行"})).json()
            assert first["needsInput"] and first["agentRun"]["modelTurns"] == 1
            second = (await client.post("/api/plan", json={"sessionId": first["sessionId"],
                      "answer": {"questionId": first["question"]["id"], "optionId": "cc"}})).json()
            assert second["question"]["question"] == "哪天出发？"
            assert second["agentRun"]["modelTurns"] == 3
            assert seen[1]["tools"] == ["set_trip_spec"]
            assert any("长春" in message.get("content", "") for message in seen[2]["messages"] if message["role"] == "tool")
            saved = (await client.get(f"/api/trips/{first['tripId']}")).json()
            assert saved["events"][-1]["sequence"] == len(saved["events"])
            assert saved["status"] == "not_started"
            assert saved["plan"] is None
            assert any(event["type"] == "trip_memory_updated" for event in saved["events"])
            assert (await client.get("/api/trips")).json()["trips"][0]["id"] == first["tripId"]
    asyncio.run(scenario())


def test_photo_belongs_to_trip_and_exif_is_removed(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_API_TOKEN", "test-media-token")
    config = ConfigStore(tmp_path / "config.yml")
    trips = TripStore(tmp_path / "trips")
    trip = trips.create({"query": "深圳旅行"})
    app = create_app(config=config, trips=trips, media=MediaStore(tmp_path / "media"))
    raw = io.BytesIO()
    Image.new("RGB", (40, 30), "blue").save(raw, format="JPEG", exif=b"Exif\x00\x00test")

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            headers = {"Authorization": "Bearer test-media-token", "Content-Type": "image/jpeg",
                       "X-Trip-Id": trip["id"], "X-Captured-Day": "2026-10-02"}
            response = await client.post("/api/media/photos", content=raw.getvalue(), headers=headers)
            assert response.status_code == 201
            photo = response.json()
            assert photo["tripId"] == trip["id"]
            detail = (await client.get(f"/api/trips/{trip['id']}")).json()
            assert detail["photos"][0]["id"] == photo["id"]
            result = await client.get(f"/api/trips/{trip['id']}/photos/{photo['id']}")
            assert result.status_code == 200
            assert b"Exif" not in result.content
            assert (await client.get(f"/api/trips/{trip['id']}/photos/{photo['id']}", params={"variant": "missing"})).status_code == 404
    asyncio.run(scenario())


def test_text_only_model_turn_continues_to_tool_call(tmp_path, monkeypatch):
    config = ConfigStore(tmp_path / "config.yml")
    config.update({"credentials": {"stepfun": "test-secret"}})
    trips = TripStore(tmp_path / "trips")
    app = create_app(config=config, trips=trips, media=MediaStore(tmp_path / "media"))
    seen = []

    async def fake_complete(messages, tools, key, **kwargs):
        seen.append(list(messages))
        calls = [] if len(seen) == 1 else [call("ask_question", {"question": "何时出发？", "options": [
            {"id": "d1", "label": "10月1日"}, {"id": "d2", "label": "10月2日"}]}, "q1")]
        yield {"type": "completion", "message": {"role": "assistant", "content": "我先想一下", "tool_calls": calls},
               "finishReason": "stop" if not calls else "tool_calls", "usage": {}, "publicNote": ""}

    monkeypatch.setattr(agent.step, "complete", fake_complete)

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            result = (await client.post("/api/plan", json={"query": "安排旅行"})).json()
            assert result["needsInput"] is True
            assert result["agentRun"]["modelTurns"] == 2
            assert any(event["type"] == "model_continuation" for event in result["agentRun"]["events"])
            assert "继续调用当前可用工具" in seen[1][-1]["content"]

    asyncio.run(scenario())


def test_preferences_are_merged_into_trip_memory():
    state = {"destination": "柳州", "originCity": "长春", "days": 3, "startDate": "2026-10-02",
             "totalBudgetCny": None, "requiredStays": [], "interests": [], "preferences": {"pace": "轻松"},
             "answerNeedsCommit": True}
    result = asyncio.run(set_trip_spec({"preferences": {"transport": "高铁"}}, state, {}))
    assert result["ok"] is True
    assert state["preferences"] == {"pace": "轻松", "transport": "高铁"}
    assert state["answerNeedsCommit"] is False


def test_server_fallback_saves_verified_plan_after_text_only_turns(tmp_path, monkeypatch):
    config = ConfigStore(tmp_path / "config.yml")
    config.update({"credentials": {"stepfun": "test-secret", "amap": "amap-test-key"}})
    trips = TripStore(tmp_path / "trips")
    app = create_app(config=config, trips=trips, media=MediaStore(tmp_path / "media"))

    async def fake_complete(messages, tools, key, **kwargs):
        yield {"type": "completion", "message": {"role": "assistant", "content": "继续分析"},
               "finishReason": "stop", "usage": {}, "publicNote": ""}

    async def fake_places(city, key):
        return [{"id": "verified-1", "name": "柳州博物馆", "city": city, "source": "test-provider"}]

    async def fake_transport(origin, destination, departure, days, credentials, priorities):
        assert priorities["trains"][0] == "rail12306"
        return {"ok": True, "outboundFlights": [], "returnFlights": [],
                "outboundTrains": [{"id": "verified-train", "origin": origin, "destination": destination, "totalPrice": 100}],
                "returnTrains": [], "providerStatus": {"rail12306": {"configured": True, "offers": 1}}}

    async def fake_dining(city, anchors, key):
        assert key == "amap-test-key"
        return [{"id": "verified-meal", "name": "柳州螺蛳粉", "day": 1, "rating": 4.6, "averageCost": 28, "source": "高德餐饮 POI"}]

    async def fake_stays(city, area, check_in, nights, budget, credentials):
        assert city == "柳州" and check_in == "2026-10-02" and nights == 2
        return {"ok": True, "hotels": [{"id": "verified-hotel", "name": "柳州酒店", "totalPrice": 450}],
                "source": "道旅 Docker MCP", "configured": True}

    async def fake_attractions(city, places, credentials, priorities):
        assert city == "柳州" and places[0]["id"] == "verified-1"
        return [{"placeId": "verified-1", "name": "柳州博物馆", "provider": "飞猪 FlyAI",
                 "productName": "门票", "price": 40, "currency": "CNY"}]

    async def fake_routes(plan, key):
        return {**plan, "groundJourneys": [{"day": 1, "from": "车站", "to": "柳州博物馆", "minutes": 15, "mode": "walk", "source": "高德步行路线"}]}

    monkeypatch.setattr(agent.step, "complete", fake_complete)
    monkeypatch.setattr(providers, "search_places", fake_places)
    monkeypatch.setattr(providers, "search_transport", fake_transport)
    monkeypatch.setattr(providers, "search_stays", fake_stays)
    monkeypatch.setattr(providers, "search_attractions", fake_attractions)
    monkeypatch.setattr(amap, "search_dining", fake_dining)
    monkeypatch.setattr(amap, "enrich_routes", fake_routes)

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/plan", json={"query": "长春到柳州三日游", "originCity": "长春",
                                                    "destination": "柳州", "startDate": "2026-10-02", "days": 3})
            result = response.json()
            assert response.status_code == 200
            assert result["days"] == 3
            assert result["itinerary"][0]["stops"][0]["id"] == "verified-1"
            assert result["agentRun"]["status"] == "degraded"
            assert result["dining"][0]["id"] == "verified-meal"
            assert result["groundJourneys"][0]["minutes"] == 15
            assert result["hotels"][0]["id"] == "verified-hotel"
            assert result["attractionOffers"][0]["placeId"] == "verified-1"
            fallback_events = [item for item in result["agentRun"]["events"] if item.get("source") == "server_fallback"]
            assert [item["type"] for item in fallback_events[:2]] == ["tool_start", "tool_end"]
            assert trips.get(result["tripId"])["plan"]["days"] == 3

    asyncio.run(scenario())
