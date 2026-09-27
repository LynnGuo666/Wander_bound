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
