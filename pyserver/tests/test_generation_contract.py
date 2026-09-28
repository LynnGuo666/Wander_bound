"""Selected-original contracts use only synthetic photos and an in-process HTTP app."""
import asyncio
import io
import uuid

import httpx
from fastapi import FastAPI
from PIL import Image

from pyserver.media import MediaStore
from pyserver.media.contracts import original_from_snapshot
from pyserver.media.job_routes import router_for
from pyserver.media.jobs import JobStore
from pyserver.trips import TripStore


def jpeg(color):
    output = io.BytesIO()
    Image.new("RGB", (32, 24), color).save(output, format="JPEG")
    return output.getvalue()


class Adapter:
    configured = True

    def __init__(self):
        self.queued = []
        self.result_calls = 0

    async def queue(self, *args):
        self.queued.append(args)
        return "prompt-id"

    async def result(self, _prompt_id):
        self.result_calls += 1
        return "completed", {"filename": "rendered.jpg"}

    async def download(self, _file):
        return jpeg("green")


def fixture(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_API_TOKEN", "contract-test-token")
    trips = TripStore(tmp_path / "trips")
    first = trips.create({"query": "甲行程"})
    second = trips.create({"query": "乙行程"})
    media = MediaStore(tmp_path / "media")
    chosen = media.add(jpeg("red"), first["id"], None)
    other = media.add(jpeg("blue"), first["id"], None)
    foreign = media.add(jpeg("yellow"), second["id"], None)
    image, video = Adapter(), Adapter()
    jobs = JobStore(media, image, video, object())
    jobs._schedule = lambda: None
    app = FastAPI()
    app.include_router(router_for(trips, media, jobs))
    return app, media, jobs, image, first, chosen, other, foreign


def test_http_contract_rejects_missing_empty_foreign_unselected_duplicate_and_forged(tmp_path, monkeypatch):
    app, media, jobs, _, trip, chosen, other, foreign = fixture(tmp_path, monkeypatch)

    async def scenario():
        headers = {"Authorization": "Bearer contract-test-token"}
        base = {"productKind": "scrapbook", "tripId": trip["id"], "photoIds": [chosen["id"]]}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.post("/api/media/generation-jobs", json=base)).status_code == 401

            async def reject(payload, code, status):
                response = await client.post("/api/media/generation-jobs", headers=headers, json=payload)
                assert response.status_code == status, response.text
                assert response.json()["detail"]["code"] == code

            await reject(base, "SELECTION_MISSING", 409)
            media.set_selected(trip["id"], {"batchId": "empty", "source": "test", "photoIds": []})
            await reject(base, "SELECTION_EMPTY", 409)
            media.set_selected(trip["id"], {"batchId": "batch-1", "source": "test", "photoIds": [chosen["id"]]})
            await reject({**base, "productKind": "video", "photoIds": [chosen["id"], chosen["id"]]}, "PHOTO_IDS_DUPLICATE", 400)
            await reject({**base, "photoIds": [chosen["id"], other["id"]]}, "PHOTO_IDS_INVALID", 400)
            await reject({**base, "productKind": "storyboard", "photoIds": [str(uuid.uuid4()) for _ in range(9)]},
                         "PHOTO_IDS_INVALID", 400)
            await reject({**base, "photoIds": [other["id"]]}, "PHOTO_NOT_SELECTED", 409)
            await reject({**base, "photoIds": [foreign["id"]]}, "PHOTO_WRONG_TRIP", 409)
            await reject({**base, "photoIds": ["00000000-0000-4000-8000-000000000000"]}, "PHOTO_NOT_FOUND", 404)
            await reject({**base, "selectionSnapshot": {"photoIds": [other["id"]]}}, "REQUEST_INVALID", 400)
            await reject({**base, "inputVariant": "develop"}, "REQUEST_INVALID", 400)
            await reject({**base, "tripId": []}, "TRIP_ID_INVALID", 400)
            await reject({**base, "prompt": "x" * 4001}, "PROMPT_INVALID", 400)
            original = media.bytes(chosen["id"], "original")
            media.photos_dir.joinpath(f"{chosen['id']}.jpg").unlink()
            await reject(base, "ORIGINAL_UNREADABLE", 409)
            media.photos_dir.joinpath(f"{chosen['id']}.jpg").write_bytes(b"not a JPEG")
            await reject(base, "ORIGINAL_UNREADABLE", 409)
            media.photos_dir.joinpath(f"{chosen['id']}.jpg").write_bytes(original)
            assert not jobs.root.exists() or not list(jobs.root.glob("*.json"))

    asyncio.run(scenario())


def test_prepared_product_dto_is_independent_and_selection_is_frozen(tmp_path, monkeypatch):
    app, media, jobs, _, trip, chosen, other, _ = fixture(tmp_path, monkeypatch)
    media.set_selected(trip["id"], {"batchId": "batch-1", "source": "test-selection", "photoIds": [chosen["id"], other["id"]]})
    original = media.bytes(chosen["id"], "original")
    media.save_variant(chosen["id"], "ai-test", jpeg("purple"))

    async def scenario():
        headers = {"Authorization": "Bearer contract-test-token"}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            ids = []
            for kind, result_kind in (("scrapbook", "image"), ("storyboard", "storyboard_json"), ("video", "video")):
                input_ids = [other["id"], chosen["id"]] if kind == "video" else [chosen["id"]]
                response = await client.post("/api/media/generation-jobs", headers=headers,
                    json={"productKind": kind, "tripId": trip["id"], "photoIds": input_ids, "prompt": "x" * 4000})
                assert response.status_code == 201, response.text
                body = response.json()
                assert body["productKind"] == kind and body["resultKind"] == result_kind
                assert body["status"] == "prepared" and body["executionReady"] is False
                snapshot = body["selectionSnapshot"]
                assert snapshot["selection"]["photoIds"] == [chosen["id"], other["id"]]
                assert snapshot["inputPhotoIds"] == input_ids
                assert snapshot["selection"]["batchId"] == "batch-1"
                assert snapshot["selection"]["source"] == "test-selection"
                assert snapshot["selection"]["updatedAt"]
                assert len(snapshot["selection"]["sha256"]) == 64
                assert original_from_snapshot(media, snapshot, chosen["id"]) == original
                ids.append((body["id"], input_ids))
            media.set_selected(trip["id"], {"batchId": "batch-2", "source": "test-selection", "photoIds": [other["id"]]})
            for job_id, input_ids in ids:
                saved = jobs.get(job_id)
                assert saved["selectionSnapshot"]["selection"]["batchId"] == "batch-1"
                assert saved["selectionSnapshot"]["inputPhotoIds"] == input_ids
                assert saved["prompt"] == "x" * 4000
                assert (await client.get(f"/api/media/generation-jobs/{job_id}", headers=headers)).json()["status"] == "prepared"
                result = await client.get(f"/api/media/generation-jobs/{job_id}/result", headers=headers)
                assert result.status_code == 409 and result.json()["detail"]["code"] == "RESULT_NOT_READY"

    asyncio.run(scenario())


def test_old_generation_routes_require_selection_and_worker_rechecks_original(tmp_path, monkeypatch):
    app, media, jobs, image, trip, chosen, other, _ = fixture(tmp_path, monkeypatch)
    media.set_selected(trip["id"], {"batchId": "batch-1", "source": "test", "photoIds": [chosen["id"]]})
    media.save_variant(chosen["id"], "ai-test", jpeg("purple"))

    async def scenario():
        headers = {"Authorization": "Bearer contract-test-token"}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            memory = {"tripId": trip["id"], "photoIds": [other["id"]]}
            rejected = await client.post("/api/media/memories", headers=headers, json=memory)
            assert rejected.status_code == 409 and rejected.json()["detail"]["code"] == "PHOTO_NOT_SELECTED"
            rejected = await client.post(f"/api/media/photos/{other['id']}/redraw", headers=headers, json={"prompt": "test"})
            assert rejected.status_code == 409 and rejected.json()["detail"]["code"] == "PHOTO_NOT_SELECTED"
            rejected = await client.post(f"/api/media/photos/{chosen['id']}/redraw", headers=headers,
                                         json={"prompt": "x" * 4001})
            assert rejected.status_code == 400 and rejected.json()["detail"]["code"] == "PROMPT_INVALID"
            accepted = await client.post(f"/api/media/photos/{chosen['id']}/redraw", headers=headers,
                                         json={"prompt": "真实重绘", "seed": 42})
            assert accepted.status_code == 202, accepted.text
            job = jobs.get(accepted.json()["id"])
            assert job["selectionSnapshot"]["inputVariant"] == "original"
            assert job["selectionSnapshot"]["selection"]["batchId"] == "batch-1"
            memory["photoIds"] = [chosen["id"]]
            accepted_memory = await client.post("/api/media/memories", headers=headers, json=memory)
            assert accepted_memory.status_code == 202
            assert jobs.get(accepted_memory.json()["id"])["selectionSnapshot"]["inputPhotoIds"] == [chosen["id"]]
            media.set_selected(trip["id"], {"batchId": "batch-2", "source": "test", "photoIds": [other["id"]]})
            await jobs._run(job["id"])
            assert jobs.get(job["id"])["status"] == "succeeded"
            assert image.queued[0][0] == media.bytes(chosen["id"], "original")
            assert image.queued[0][0] != media.bytes(chosen["id"], "ai-test")
            original_other = media.bytes(other["id"], "original")
            later = jobs.submit("edit", {"photoId": other["id"], "prompt": "test", "seed": 1})
            media.photos_dir.joinpath(f"{other['id']}.jpg").write_bytes(jpeg("black"))
            await jobs._run(later["id"])
            failed = jobs.get(later["id"])
            assert failed["status"] == "failed" and failed["errorCode"] == "ORIGINAL_CHANGED"
            assert len(image.queued) == 1
            media.photos_dir.joinpath(f"{other['id']}.jpg").write_bytes(original_other)
            deleted = jobs.submit("edit", {"photoId": other["id"], "prompt": "test", "seed": 1})
            media.photos_dir.joinpath(f"{other['id']}.jpg").unlink()
            await jobs._run(deleted["id"])
            assert jobs.get(deleted["id"])["errorCode"] == "ORIGINAL_UNREADABLE"
            assert len(image.queued) == 1

            media.photos_dir.joinpath(f"{other['id']}.jpg").write_bytes(original_other)
            corrupt = jobs.submit("edit", {"photoId": other["id"], "prompt": "test", "seed": 1})
            media.photos_dir.joinpath(f"{other['id']}.jpg").write_bytes(b"not a JPEG")
            await jobs._run(corrupt["id"])
            assert jobs.get(corrupt["id"])["errorCode"] == "ORIGINAL_UNREADABLE"
            assert len(image.queued) == 1

    asyncio.run(scenario())


def test_wrong_retry_route_never_mutates_or_schedules_another_job_kind(tmp_path, monkeypatch):
    app, media, jobs, _, trip, chosen, _, _ = fixture(tmp_path, monkeypatch)
    media.set_selected(trip["id"], {"batchId": "batch", "source": "test", "photoIds": [chosen["id"]]})
    edit = jobs.submit("edit", {"photoId": chosen["id"], "prompt": "test", "seed": 1})
    memory = jobs.submit("memory", {"tripId": trip["id"], "photoIds": [chosen["id"]], "title": "旅行"})
    for job in (edit, memory):
        job["status"] = "failed"
        jobs.save(job)
    schedules = []
    jobs._schedule = lambda: schedules.append("scheduled")

    async def scenario():
        headers = {"Authorization": "Bearer contract-test-token"}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            for path, job in ((f"/api/media/memories/{edit['id']}/retry", edit),
                              (f"/api/media/edits/{memory['id']}/retry", memory)):
                response = await client.post(path, headers=headers)
                assert response.status_code == 404
                current = jobs.get(job["id"])
                assert current["status"] == "failed" and current["attempt"] == 1
            assert schedules == []
            response = await client.post(f"/api/media/edits/{edit['id']}/retry", headers=headers)
            assert response.status_code == 202
            assert jobs.get(edit["id"])["attempt"] == 2
            assert schedules == ["scheduled"]

    asyncio.run(scenario())


def test_legacy_prompt_id_cannot_bypass_snapshot_before_controller(tmp_path, monkeypatch):
    _, media, jobs, image, trip, chosen, _, _ = fixture(tmp_path, monkeypatch)
    media.set_selected(trip["id"], {"batchId": "batch", "source": "test", "photoIds": [chosen["id"]]})
    legacy = {"id": str(uuid.uuid4()), "kind": "edit", "status": "queued", "backend": "test",
              "createdAt": "2026-09-28T00:00:00Z", "photoId": chosen["id"],
              "prompt": "old", "promptId": "already-queued", "seed": 1, "attempt": 1}
    jobs.save(legacy)
    asyncio.run(jobs._drain())
    failed = jobs.get(legacy["id"])
    assert failed["status"] == "failed" and failed["errorCode"] == "SNAPSHOT_INVALID"
    assert not image.queued and image.result_calls == 0
