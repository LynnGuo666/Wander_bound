"""Journal composition keeps private media private and Qwen jobs text-only."""
import asyncio
import io
import json

import httpx
from fastapi import FastAPI
from PIL import Image

from pyserver.accounts import current_user
from pyserver.inference import ModelController
from pyserver.media import ComfyClient, MediaStore
from pyserver.media import journal_routes
from pyserver.media.stickers import StickerStore
from pyserver.trips import TripStore


class Config:
    def credentials(self):
        return {"stepfun": "test-step-key"}


class Jobs:
    def __init__(self):
        self.entries = {}

    def list_for_trip(self, _trip_id):
        return []

    def get(self, job_id):
        return self.entries.get(job_id)


def test_qwen_asset_reuses_only_the_current_prompt_version(tmp_path, monkeypatch):
    client = ComfyClient("http://127.0.0.1:8191", "workflows/qwen-image-2.1-sticker-api.json", "image")
    stickers = StickerStore(tmp_path / "stickers", client, ModelController())
    monkeypatch.setattr(stickers, "schedule", lambda: None)
    first = stickers.submit("trip-a", "上海", "外滩江景", "postcard")
    assert stickers.submit("trip-a", "上海", "外滩江景", "postcard")["id"] == first["id"]
    old = stickers.get(first["id"])
    old["promptVersion"] = "journal-postcard-scene-qwen21-t2i-v2"
    stickers.save(old)
    current = stickers.submit("trip-a", "上海", "外滩江景", "postcard")
    assert current["id"] != first["id"]
    assert stickers.get(current["id"])["promptVersion"] == "journal-postcard-scene-qwen21-t2i-v4"


def test_step_photo_context_ignores_malformed_recognition_fields():
    class SelectedPhotos:
        def selected(self, _trip_id):
            return {"photos": [{"id": "photo-a", "capturedDay": "2026-09-29",
                                "tags": {"scene": {"unexpected": "object"}, "objects": "外滩游船",
                                         "quality": "highlight", "activity": ["赏景"]}},
                               {"id": "photo-b", "tags": {"scene": "黄浦江", "objects": ["游船", 42],
                                                          "quality": {"highlight": True}}}]}

    context = journal_routes.photo_context(SelectedPhotos(), "trip-a")
    assert context[0] == {"photoId": "photo-a", "capturedDay": "2026-09-29",
                          "scene": "", "activity": "", "objects": [], "locationClue": "",
                          "mood": "", "highlight": False}
    assert context[1]["scene"] == "黄浦江"
    assert context[1]["objects"] == ["游船"]
    assert context[1]["highlight"] is True


def test_step_composition_and_qwen_sticker_are_authenticated_and_private(tmp_path, monkeypatch):
    user = {"id": "journal-test-user", "role": "member"}
    trips = TripStore(tmp_path / "trips")
    context = current_user.set(user)
    trip = trips.create({"query": "上海旅行"})
    current_user.reset(context)
    trip["plan"] = {"destination": "上海", "itinerary": [{"stops": [{"name": "外滩"}]}]}
    trips.save(trip)
    media = MediaStore(tmp_path / "media")
    image = io.BytesIO()
    Image.new("RGB", (64, 64), "#467a91").save(image, format="JPEG")
    context = current_user.set(user)
    photo = media.add(image.getvalue(), trip["id"], "2026-09-29")
    media.set_tags(photo["id"], {"scene": "外滩黄浦江夜景", "objects": ["江边建筑", "游船"],
                                  "activity": "赏景", "quality": {"highlight": True}})
    media.set_selected(trip["id"], {"photoIds": [photo["id"]], "batchId": "journal-selected", "source": "test"})
    current_user.reset(context)
    client = ComfyClient("http://127.0.0.1:8191", "workflows/qwen-image-2.1-sticker-api.json", "image")
    stickers = StickerStore(media.root / "stickers", client, ModelController())
    monkeypatch.setattr(stickers, "schedule", lambda: None)
    captured = []
    valid_plan = {
        "templates": ["photo-wall", "book-and-clip"],
        "photoOrder": [photo["id"]],
        "stickerMotifs": ["绿色电车和银杏", "黄浦江上的小船", "外滩建筑", "旅途美食",
                          "外滩夜色倒影", "黄浦江边的相机"],
        "stampMotif": "外滩江景", "postcardMotif": "黄浦江夜景明信片",
        "illustrationMotif": "江边建筑和游船", "diaryText": "黄浦江边看到了游船。",
        "postcardText": "寄一张黄浦江夜景给未来的我。",
    }

    async def complete(messages, tools, key):
        captured.append(messages)
        assert tools == [] and key == "test-step-key"
        yield {"type": "completion", "message": {"content": json.dumps(valid_plan)}}

    monkeypatch.setattr(journal_routes.step, "complete", complete)
    app = FastAPI()

    @app.middleware("http")
    async def test_account_session(request, call_next):
        bearer = request.headers.get("Authorization")
        request.state.user = (user if bearer == "Bearer journal-test-token" else
                              {"id": "another-user", "role": "member"} if bearer == "Bearer other-test-token" else None)
        context = current_user.set(request.state.user)
        try:
            return await call_next(request)
        finally:
            current_user.reset(context)

    jobs = Jobs()
    app.include_router(journal_routes.router_for(Config(), trips, media, jobs, stickers))

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
            assert "外滩黄浦江夜景" in captured[0][1]["content"]
            assert photo["id"] in response.json()["photoOrder"]
            assert len(response.json()["stickerMotifs"]) == 6
            assert response.json()["diaryText"] == "黄浦江边看到了游船。"
            assert response.json()["postcardText"] == valid_plan["postcardText"]
            assert "base64" not in json.dumps(captured)
            assert "sourceSha256" not in json.dumps(captured)
            async def incomplete(_messages, _tools, _key):
                yield {"type": "completion", "message": {"content": json.dumps({
                    **valid_plan, "postcardMotif": {"unexpected": "object"}})}}
            monkeypatch.setattr(journal_routes.step, "complete", incomplete)
            assert (await http.post(base + "/journal/compose")).status_code == 502
            async def unwritten(_messages, _tools, _key):
                yield {"type": "completion", "message": {"content": json.dumps({
                    **valid_plan, "postcardText": ""})}}
            monkeypatch.setattr(journal_routes.step, "complete", unwritten)
            assert (await http.post(base + "/journal/compose")).status_code == 502
            assert (await http.get(base + "/journal")).json()["version"] == 0
            created = await http.post(base + "/stickers", json={"motif": "绿色电车和银杏"})
            assert created.status_code == 202, created.text
            body = created.json()
            assert "prompt" not in body and "workflow" not in body
            saved = stickers.get(body["id"])
            assert saved["kind"] == "sticker"
            assert saved["promptVersion"] == "journal-sticker-qwen21-t2i-v1"
            assert saved["workflow"]["6"]["class_type"] == "EmptyLatentImage"
            assert all(node["class_type"] != "LoadImage" for node in saved["workflow"].values())
            inventory = (await http.get(base + "/stickers")).json()
            assert inventory["stickers"][0]["id"] == body["id"]
            assert inventory["stickers"][0]["promptVersion"] == inventory["promptVersions"]["sticker"]
            assert (await http.get(f"/api/media/stickers/{body['id']}/image")).status_code == 409
            http.headers["Authorization"] = "Bearer other-test-token"
            assert (await http.get(f"/api/media/stickers/{body['id']}/image")).status_code == 404
            http.headers["Authorization"] = "Bearer journal-test-token"
            stamp = await http.post(base + "/stickers", json={"motif": "外滩江景", "kind": "stamp"})
            assert stamp.status_code == 202 and stamp.json()["kind"] == "stamp"
            assert stickers.get(stamp.json()["id"])["promptVersion"] == "journal-stamp-qwen21-t2i-v1"
            postcard = await http.post(base + "/stickers", json={"motif": "黄浦江夜景明信片", "kind": "postcard"})
            illustration = await http.post(base + "/stickers", json={"motif": "江边建筑和游船", "kind": "illustration"})
            assert postcard.status_code == illustration.status_code == 202
            assert stickers.get(postcard.json()["id"])["promptVersion"] == "journal-postcard-scene-qwen21-t2i-v4"
            assert stickers.get(illustration.json()["id"])["promptVersion"] == "journal-illustration-qwen21-t2i-v3"
            journal = (await http.get(base + "/journal")).json()
            edited_page = journal["pages"][0]
            edited_page["items"] = [{**item, "text": "这页由用户写过"} if item["kind"] == "text" else item
                                    for item in edited_page["items"]]
            saved = await http.put(base + "/journal/pages/0", json={"expectedVersion": 0, "page": edited_page})
            assert saved.status_code == 200 and saved.json()["pages"][0]["protected"]
            video_id = "410a794a-aa66-4db4-a780-1eab7ed39eb5"
            jobs.entries[video_id] = {"id": video_id, "kind": "memory", "tripId": trip["id"]}
            video_page = saved.json()["pages"][0]
            video_page["items"].append({"id": "838b7399-d3b3-44b2-9349-a3038249fb3f", "kind": "video",
                                        "videoId": video_id, "x": 10, "y": 10, "w": 30, "h": 20, "r": 0, "z": 3})
            saved = await http.put(base + "/journal/pages/0", json={
                "expectedVersion": saved.json()["version"], "page": video_page})
            assert saved.status_code == 200 and saved.json()["pages"][0]["items"][-1]["videoId"] == video_id
            foreign = {**video_page, "items": [*video_page["items"][:-1],
                       {**video_page["items"][-1], "videoId": "c251060e-0152-4507-aee4-af63b68abb4b"}]}
            assert (await http.put(base + "/journal/pages/0", json={
                "expectedVersion": saved.json()["version"], "page": foreign})).status_code == 400
            proposed = [journal_routes.JournalStore(tmp_path / "scratch", journal_routes.catalog())._seed_page(
                "photo-wall", trip, 0), journal_routes.JournalStore(tmp_path / "scratch", journal_routes.catalog())._seed_page(
                "postcard-collage", trip, 1)]
            proposed[1]["items"][0]["assetId"] = postcard.json()["id"]
            applied = await http.post(base + "/journal/apply-ai", json={"pages": proposed})
            assert applied.status_code == 200, applied.text
            assert applied.json()["preservedPageIndices"] == [0]
            assert applied.json()["pages"][0] == saved.json()["pages"][0]
            proposed[1]["items"].append({"id": "904f3a31-374a-42bb-90f5-af48e9d21a62", "kind": "photo",
                                         "photoId": "75cac321-cd57-4a7e-9fa3-1509489f01bb",
                                         "x": 10, "y": 10, "w": 20, "h": 20, "r": 0, "z": 3})
            assert (await http.post(base + "/journal/apply-ai", json={"pages": proposed})).status_code == 400
            http.headers["Authorization"] = "Bearer other-test-token"
            assert (await http.get(base + "/journal")).status_code == 404
            http.headers["Authorization"] = "Bearer journal-test-token"
            assert (await http.post(base + "/stickers", json={"motif": "x"})).status_code == 400
    asyncio.run(scenario())
