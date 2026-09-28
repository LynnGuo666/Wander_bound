"""Journal composition keeps private media private and Qwen jobs text-only."""
import asyncio
import json

import httpx
from fastapi import FastAPI

from pyserver.inference import ModelController
from pyserver.media import ComfyClient, MediaStore
from pyserver.media import journal_routes
from pyserver.media.stickers import StickerStore
from pyserver.trips import TripStore


class Config:
    def credentials(self):
        return {"stepfun": "test-step-key"}


class Jobs:
    def list_for_trip(self, _trip_id):
        return []


def test_step_composition_and_qwen_sticker_are_authenticated_and_private(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_API_TOKEN", "journal-test-token")
    trips = TripStore(tmp_path / "trips")
    trip = trips.create({"query": "上海旅行"})
    trip["plan"] = {"destination": "上海", "itinerary": [{"stops": [{"name": "外滩"}]}]}
    trips.save(trip)
    media = MediaStore(tmp_path / "media")
    client = ComfyClient("http://127.0.0.1:8191", "workflows/qwen-image-2.1-sticker-api.json", "image")
    stickers = StickerStore(media.root / "stickers", client, ModelController())
    monkeypatch.setattr(stickers, "schedule", lambda: None)
    captured = []

    async def complete(messages, tools, key):
        captured.append(messages)
        assert tools == [] and key == "test-step-key"
        yield {"type": "completion", "message": {"content": json.dumps({
            "templates": ["photo-wall", "book-and-clip"],
            "stickerMotifs": ["绿色电车和银杏", "黄浦江上的小船", "外滩建筑", "旅途美食"],
            "stampMotif": "外滩江景"})}}

    monkeypatch.setattr(journal_routes.step, "complete", complete)
    app = FastAPI()
    app.include_router(journal_routes.router_for(Config(), trips, media, Jobs(), stickers))

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
            base = f"/api/media/trips/{trip['id']}"
            assert (await http.post(base + "/journal/compose")).status_code == 401
            assert (await http.post(base + "/stickers", json={"motif": "电车"})).status_code == 401
            http.headers["Authorization"] = "Bearer journal-test-token"
            response = await http.post(base + "/journal/compose")
            assert response.status_code == 200, response.text
            assert response.json()["source"] == journal_routes.step.MODEL
            assert "photoCount" in captured[0][1]["content"]
            assert "base64" not in json.dumps(captured)
            created = await http.post(base + "/stickers", json={"motif": "绿色电车和银杏"})
            assert created.status_code == 202, created.text
            body = created.json()
            assert "prompt" not in body and "workflow" not in body
            saved = stickers.get(body["id"])
            assert saved["kind"] == "sticker"
            assert saved["promptVersion"] == "journal-sticker-qwen21-t2i-v1"
            assert saved["workflow"]["6"]["class_type"] == "EmptyLatentImage"
            assert all(node["class_type"] != "LoadImage" for node in saved["workflow"].values())
            assert (await http.get(base + "/stickers")).json()["stickers"][0]["id"] == body["id"]
            assert (await http.get(f"/api/media/stickers/{body['id']}/image")).status_code == 409
            stamp = await http.post(base + "/stickers", json={"motif": "外滩江景", "kind": "stamp"})
            assert stamp.status_code == 202 and stamp.json()["kind"] == "stamp"
            assert stickers.get(stamp.json()["id"])["promptVersion"] == "journal-stamp-qwen21-t2i-v1"
            assert (await http.post(base + "/stickers", json={"motif": "x"})).status_code == 400
    asyncio.run(scenario())
