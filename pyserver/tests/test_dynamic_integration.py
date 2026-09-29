"""Dynamic-photo batch, shared-worker and authenticated result integration tests."""
import asyncio
import hashlib
import json
import uuid
from contextlib import asynccontextmanager

import httpx
import pytest

from pyserver.accounts import AccountStore
from pyserver.app import create_app
from pyserver.media.jobs import JobStore
from pyserver.media.dynamic_sources import DynamicPhotoSources
from pyserver.media.contracts import ContractError
from pyserver.settings import ConfigStore
from pyserver.tests.test_dynamic_sources import fixture, jpeg


OWNER = {"id": "legacy-feature-test", "username": "test", "role": "admin"}
OTHER = {"id": "other-account", "username": "other", "role": "user"}


def setup(tmp_path, monkeypatch):
    trips, media, trip, other, first, second, foreign, payload = fixture(tmp_path)
    monkeypatch.setattr(AccountStore, "authenticate", lambda self, token: {
        "owner-token": OWNER, "other-token": OTHER}.get(token))
    monkeypatch.setattr(JobStore, "_schedule", lambda self: None)
    app = create_app(config=ConfigStore(tmp_path / "config.yml"), trips=trips, media=media)
    return app, trips, media, trip, other, first, second, payload


def headers(token="owner-token"):
    return {"Authorization": f"Bearer {token}"}


def batch_payload(media, trip, first, second):
    selection = media.selected(trip["id"])
    return {"operationId": str(uuid.uuid4()), "batchId": selection["batchId"],
            "selectionUpdatedAt": selection["updatedAt"],
            "photos": [{"photoId": first["id"], "action": "develop", "params": {}, "note": "first"},
                       {"photoId": second["id"], "action": "develop", "params": {}, "note": "second"}]}


def test_batch_partial_failure_resumes_same_variants_and_reuses_settlement(tmp_path, monkeypatch):
    app, _, media, trip, _, first, second, _ = setup(tmp_path, monkeypatch)
    data = batch_payload(media, trip, first, second)
    calls = []
    async def render(_media, pid, params):
        calls.append(pid)
        if pid == second["id"] and calls.count(pid) == 1:
            raise RuntimeError("test render interruption")
        return jpeg("purple" if pid == first["id"] else "orange")
    monkeypatch.setattr("pyserver.media.dynamic_routes._render_development", render)

    async def scenario():
        url = f"/api/media/trips/{trip['id']}/dynamic-photo/develop-batch-and-settle"
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            first_call = await client.post(url, json=data, headers=headers())
            assert first_call.status_code == 503
            assert first_call.json()["detail"]["completedPhotoIds"] == [first["id"]]
            assert first_call.json()["detail"]["settled"] is False
            assert not list(DynamicPhotoSources(media).root.glob("*.json"))
            saved_variant = media.development_for_operation(first["id"], data["operationId"])["variant"]
            resumed = await client.post(url, json=data, headers=headers())
            assert resumed.status_code == 202, resumed.text
            job_id = resumed.json()["jobId"]
            assert resumed.json()["completedPhotoIds"] == [first["id"], second["id"]]
            assert media.development_for_operation(first["id"], data["operationId"])["variant"] == saved_variant
            assert calls == [first["id"], second["id"], second["id"]]
            duplicate = await client.post(url, json=data, headers=headers())
            assert duplicate.status_code == 202 and duplicate.json()["jobId"] == job_id
            assert calls == [first["id"], second["id"], second["id"]]
            changed = {**data, "photos": [*data["photos"]]}
            changed["photos"][0] = {**changed["photos"][0], "note": "changed"}
            conflict = await client.post(url, json=changed, headers=headers())
            assert conflict.status_code == 409 and conflict.json()["detail"]["code"] == "OPERATION_CONFLICT"
            status = await client.get(f"/api/media/dynamic-photo/jobs/{job_id}", headers=headers())
            assert status.json()["status"] == "queued"
            assert status.json()["sourceSnapshot"]["inputs"][0]["sourceVariant"] == saved_variant
    asyncio.run(scenario())


def test_batch_recovers_file_written_before_metadata_receipt_without_rerender(tmp_path, monkeypatch):
    app, _, media, trip, _, first, second, _ = setup(tmp_path, monkeypatch)
    data = batch_payload(media, trip, first, second)
    data["photos"][1] = {"photoId": second["id"], "action": "none"}
    artifact = media.development_artifact_for_operation(first["id"], data["operationId"])
    artifact.write_bytes(jpeg("purple"))  # Simulate crash after artifact write, before metadata/receipt.
    async def must_not_render(*args):
        pytest.fail("existing operation artifact must be recovered without a second render")
    monkeypatch.setattr("pyserver.media.dynamic_routes._render_development", must_not_render)
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            result = await client.post(f"/api/media/trips/{trip['id']}/dynamic-photo/develop-batch-and-settle",
                                       json=data, headers=headers())
            assert result.status_code == 202, result.text
            assert media.development_for_operation(first["id"], data["operationId"])["variant"] in artifact.name
    asyncio.run(scenario())


def test_execution_contract_change_gets_new_job_identity(tmp_path, monkeypatch):
    _, _, media, trip, _, first, second, _ = setup(tmp_path, monkeypatch)
    sources = DynamicPhotoSources(media)
    selection = media.selected(trip["id"])
    payload = {"batchId": selection["batchId"], "selectionUpdatedAt": selection["updatedAt"],
               "photos": [{"photoId": first["id"], "status": "none"},
                          {"photoId": second["id"], "status": "none"}]}
    original = sources.settle(trip["id"], payload)
    monkeypatch.setattr("pyserver.media.dynamic_sources.vision_model", lambda: "model-updated")
    updated = sources.settle(trip["id"], payload)
    assert updated["id"] != original["id"]
    assert updated["sourceSnapshot"] == original["sourceSnapshot"]
    assert updated["executionContract"]["visionModel"] == "model-updated"
    assert len(list(sources.root.glob("*.json"))) == 2


def test_shared_worker_selects_then_runs_h3_once_and_restart_reuses_success(tmp_path, monkeypatch):
    _, _, media, trip, _, first, second, _ = setup(tmp_path, monkeypatch)
    sources = DynamicPhotoSources(media)
    selection = media.selected(trip["id"])
    payload = {"batchId": selection["batchId"], "selectionUpdatedAt": selection["updatedAt"],
               "photos": [{"photoId": first["id"], "status": "none"},
                          {"photoId": second["id"], "status": "none"}]}
    job = sources.settle(trip["id"], payload)
    class Controller:
        pass
    jobs = JobStore(media, None, None, Controller())
    calls = []
    async def select(job_id):
        calls.append("vision")
        item = sources.get(job_id)
        item["status"] = "selected"
        item["selection"] = {"selectedPhotoId": first["id"], "motionPrompt": "small waves"}
        jobs._save_dynamic(item)
        return item
    class H3:
        async def run(self, job_id):
            calls.append("h3")
            item = sources.get(job_id)
            item["status"] = "succeeded"
            jobs._save_dynamic(item)
            return item
    jobs.dynamic_selector.run_managed = select
    jobs.dynamic_h3 = H3()
    jobs.enqueue_dynamic(job["id"])
    assert jobs.pending()[0]["id"] == job["id"]
    asyncio.run(jobs._drain())
    assert calls == ["vision", "h3"]
    assert sources.get(job["id"])["status"] == "succeeded"
    restarted = JobStore(media, None, None, Controller())
    assert restarted.pending() == []
    assert restarted.enqueue_dynamic(job["id"])["status"] == "succeeded"


def test_unknown_h3_retry_does_not_requeue_and_account_cannot_read_media(tmp_path, monkeypatch):
    app, _, media, trip, _, first, second, _ = setup(tmp_path, monkeypatch)
    sources = DynamicPhotoSources(media)
    selection = media.selected(trip["id"])
    job = sources.settle(trip["id"], {"batchId": selection["batchId"],
        "selectionUpdatedAt": selection["updatedAt"], "photos": [
            {"photoId": first["id"], "status": "none"},
            {"photoId": second["id"], "status": "none"}]})
    job["status"] = "failed"
    job["attempt"] = 1
    job["selection"] = {"selectedPhotoId": first["id"], "motionPrompt": "small waves"}
    job["h3"] = {"promptId": str(uuid.uuid4()), "submissionState": "submitting"}
    jobs = JobStore(media, None, None, None)
    jobs._save_dynamic(job)
    class Client:
        async def result(self, prompt_id):
            return "missing", None
    class H3:
        client = Client()
    jobs.dynamic_h3 = H3()
    class Controller:
        @asynccontextmanager
        async def use(self, name):
            yield
    jobs.controller = Controller()

    async def retry_scenario():
        with pytest.raises(ContractError) as unknown:
            await jobs.retry_dynamic(job["id"])
        assert unknown.value.code == "H3_SUBMISSION_UNKNOWN"
        assert sources.get(job["id"])["attempt"] == 1
        assert sources.get(job["id"])["selection"]["selectedPhotoId"] == first["id"]
    asyncio.run(retry_scenario())

    video = sources.root / job["id"] / "dynamic.mp4"
    cover = sources.root / job["id"] / "cover.jpg"
    video.write_bytes(b"private video test bytes")
    cover.write_bytes(jpeg("blue"))
    job = sources.get(job["id"])
    job["status"] = "succeeded"
    job["result"] = {"photoId": first["id"], "media": {
        "sha256": hashlib.sha256(video.read_bytes()).hexdigest(),
        "coverSha256": hashlib.sha256(cover.read_bytes()).hexdigest()}}
    jobs._save_dynamic(job)

    async def read_scenario():
        video_url = f"/api/media/dynamic-photo/jobs/{job['id']}/video"
        cover_url = f"/api/media/dynamic-photo/jobs/{job['id']}/cover"
        photo_url = f"/api/media/photos/{first['id']}/dynamic-photo"
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get(video_url)).status_code == 401
            assert (await client.get(video_url, headers=headers("other-token"))).status_code == 404
            assert (await client.get(cover_url, headers=headers("other-token"))).status_code == 404
            assert (await client.get(photo_url, headers=headers("other-token"))).status_code == 404
            assert (await client.get(video_url, headers=headers())).content == video.read_bytes()
            assert (await client.get(cover_url, headers=headers())).content == cover.read_bytes()
            assert (await client.get(photo_url, headers=headers())).status_code == 200
    asyncio.run(read_scenario())


def test_explicit_retry_reconciles_prompt_and_enforces_limit(tmp_path, monkeypatch):
    _, _, media, trip, _, first, second, _ = setup(tmp_path, monkeypatch)
    sources = DynamicPhotoSources(media)
    selection = media.selected(trip["id"])
    job = sources.settle(trip["id"], {"batchId": selection["batchId"],
        "selectionUpdatedAt": selection["updatedAt"], "photos": [
            {"photoId": first["id"], "status": "none"},
            {"photoId": second["id"], "status": "none"}]})
    class Controller:
        @asynccontextmanager
        async def use(self, name):
            yield
    jobs = JobStore(media, None, None, Controller())
    job.update(status="failed", attempt=1,
               selection={"selectedPhotoId": first["id"], "motionPrompt": "small waves"},
               h3={"promptId": str(uuid.uuid4()), "submissionState": "submitted"})
    jobs._save_dynamic(job)
    class Client:
        state = "running"
        async def result(self, prompt_id):
            return self.state, None
    class H3:
        client = Client()
    jobs.dynamic_h3 = H3()
    resumed = asyncio.run(jobs.retry_dynamic(job["id"]))
    assert resumed["status"] == "generating" and resumed["attempt"] == 2
    assert resumed["h3"]["promptId"] == job["h3"]["promptId"]
    resumed["status"] = "failed"
    jobs._save_dynamic(resumed)
    jobs.dynamic_h3.client.state = "failed"
    fresh = asyncio.run(jobs.retry_dynamic(job["id"]))
    assert fresh["status"] == "selected" and fresh["attempt"] == 3
    assert "h3" not in fresh and fresh["selection"]["selectedPhotoId"] == first["id"]
    fresh["status"] = "failed"
    jobs._save_dynamic(fresh)
    with pytest.raises(ContractError) as limited:
        asyncio.run(jobs.retry_dynamic(job["id"]))
    assert limited.value.code == "RETRY_LIMIT"
