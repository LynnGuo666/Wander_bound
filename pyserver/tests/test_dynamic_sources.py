"""Dynamic-photo source settlement uses real stored JPEGs and no model substitute."""
import asyncio
import hashlib
import io
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from PIL import Image

from pyserver.accounts import AccountStore, current_user
from pyserver.app import create_app
from pyserver.media import MediaStore
from pyserver.media.contracts import ContractError, selected_original_snapshot
from pyserver.media.dynamic_sources import DynamicPhotoSources
from pyserver.settings import ConfigStore
from pyserver.trips import TripStore


def jpeg(color, size=(64, 48)):
    output = io.BytesIO()
    Image.new("RGB", size, color).save(output, format="JPEG")
    return output.getvalue()


def fixture(tmp_path):
    trips = TripStore(tmp_path / "trips")
    trip = trips.create({"query": "selected trip"})
    other = trips.create({"query": "other trip"})
    media = MediaStore(tmp_path / "media")
    first = media.add(jpeg("blue"), trip["id"], None)
    second = media.add(jpeg("green"), trip["id"], None)
    foreign = media.add(jpeg("red"), other["id"], None)
    selected = media.set_selected(trip["id"], {"batchId": "batch-1", "source": "test", "photoIds": [first["id"], second["id"]]})
    payload = {"batchId": "batch-1", "selectionUpdatedAt": selected["updatedAt"],
               "photos": [{"photoId": first["id"], "status": "developed"},
                          {"photoId": second["id"], "status": "none"}]}
    return trips, media, trip, other, first, second, foreign, payload


def test_settlement_freezes_latest_development_and_original_without_changing_legacy_product(tmp_path):
    _, media, trip, _, first, second, _, payload = fixture(tmp_path)
    developed = media.save_develop(first["id"], jpeg("purple", (48, 64)), {"exposure": 0.2})
    sources = DynamicPhotoSources(media)
    job = sources.settle(trip["id"], payload)
    assert job["status"] == "prepared" and job["executionReady"] is False
    assert job["selection"] is None and job["result"] is None
    assert job["sourceSnapshot"]["selection"]["photoIds"] == [first["id"], second["id"]]
    assert job["sourceSnapshot"]["settlement"]["sha256"]
    left, right = job["sourceSnapshot"]["inputs"]
    assert left["sourceVariant"] == developed["variant"] and (left["width"], left["height"]) == (48, 64)
    assert right["sourceVariant"] == "original" and (right["width"], right["height"]) == (64, 48)
    assert left["sha256"] == hashlib.sha256(media.bytes(first["id"], developed["variant"])).hexdigest()
    assert sources.read_input(job, first["id"]) == media.bytes(first["id"], developed["variant"])
    assert sources.read_input(job, second["id"]) == media.bytes(second["id"])
    assert all(item["dynamicVersionId"] is None for item in job["associations"])
    forged = {**job, "sourceSnapshot": {**job["sourceSnapshot"], "inputs": [
        {**left, "sha256": "0" * 64}, right]}}
    with pytest.raises(ContractError) as invalid:
        sources.read_input(forged, first["id"])
    assert invalid.value.code == "SNAPSHOT_INVALID"
    assert sources.settle(trip["id"], payload)["id"] == job["id"]
    assert len(list(sources.root.glob("*.json"))) == 1
    legacy = selected_original_snapshot(media, trip["id"], [first["id"]], maximum=1)
    assert legacy["inputVariant"] == "original"
    assert legacy["originals"][0]["sha256"] == hashlib.sha256(media.bytes(first["id"])).hexdigest()


def test_settlement_rejects_unfinished_changed_foreign_and_unreadable_inputs(tmp_path):
    _, media, trip, _, first, second, foreign, payload = fixture(tmp_path)
    sources = DynamicPhotoSources(media)
    def code(body):
        try:
            sources.settle(trip["id"], body)
        except ContractError as exc:
            return exc.code
        raise AssertionError("expected contract error")
    assert code({**payload, "photos": [{"photoId": first["id"], "status": "none"}]}) == "SELECTION_CHANGED"
    assert code({**payload, "photos": [{"photoId": first["id"], "status": "pending"},
                                          payload["photos"][1]]}) == "DEVELOPMENT_UNSETTLED"
    assert code({**payload, "photos": [{"photoId": foreign["id"], "status": "none"},
                                          payload["photos"][1]]}) == "SELECTION_CHANGED"
    assert code({**payload, "photos": [{"photoId": first["id"], "status": "developed"},
                                          payload["photos"][1]]}) == "DEVELOPMENT_MISMATCH"
    developed = media.save_develop(first["id"], jpeg("purple"), {})
    assert code({**payload, "photos": [{"photoId": first["id"], "status": "none"},
                                          payload["photos"][1]]}) == "DEVELOPMENT_MISMATCH"
    path = media.photos_dir / f"{first['id']}-{developed['variant']}.jpg"
    content = path.read_bytes()
    path.unlink()
    assert code(payload) == "DEVELOPMENT_UNREADABLE"
    path.write_bytes(b"broken JPEG")
    assert code(payload) == "DEVELOPMENT_UNREADABLE"
    path.write_bytes(content)
    job = sources.settle(trip["id"], payload)
    path.write_bytes(jpeg("yellow"))
    assert sources.read_input(job, first["id"]) == content
    frozen = sources.root / job["id"] / "inputs" / f"{first['id']}.jpg"
    frozen.write_bytes(jpeg("orange"))
    with pytest.raises(ContractError) as changed:
        sources.read_input(job, first["id"])
    assert changed.value.code == "INPUT_CHANGED"
    media.set_selected(trip["id"], {"batchId": "batch-2", "source": "test", "photoIds": [second["id"]]})
    try:
        sources.read_input(job, second["id"])
    except ContractError as exc:
        assert exc.code == "SELECTION_CHANGED"
    else:
        raise AssertionError("changed selection must fail")
    assert len(list(sources.root.glob("*.json"))) == 1


def test_in_flight_development_blocks_settlement_and_batch_change_blocks_late_save(tmp_path):
    _, media, trip, _, first, second, _, payload = fixture(tmp_path)
    sources = DynamicPhotoSources(media)
    marker, batch = sources.mark_development_started(trip["id"], first["id"])
    assert batch == "batch-1"
    with pytest.raises(ContractError) as pending:
        sources.settle(trip["id"], {**payload, "photos": [
            {"photoId": first["id"], "status": "none"}, payload["photos"][1]]})
    assert pending.value.code == "DEVELOPMENT_IN_PROGRESS"
    media.set_selected(trip["id"], {"batchId": "batch-2", "source": "test", "photoIds": [second["id"]]})
    assert media.save_develop(first["id"], jpeg("purple"), {}, expected_batch_id=batch) is None
    sources.mark_development_finished(trip["id"], marker)
    assert not list((sources.developing / trip["id"]).glob("*.json"))


def test_prior_batch_development_is_latest_valid_input_and_new_batch_allows_new_save(tmp_path):
    _, media, trip, _, first, second, _, payload = fixture(tmp_path)
    prior = media.save_develop(first["id"], jpeg("purple"), {})
    media.set_selected(trip["id"], {"batchId": "batch-2", "source": "test", "photoIds": [first["id"], second["id"]]})
    selection = media.selected(trip["id"])
    payload["batchId"] = "batch-2"
    payload["selectionUpdatedAt"] = selection["updatedAt"]
    sources = DynamicPhotoSources(media)
    job = sources.settle(trip["id"], payload)
    assert job["sourceSnapshot"]["inputs"][0]["sourceVariant"] == prior["variant"]
    media.set_selected(trip["id"], {"batchId": "batch-3", "source": "test", "photoIds": [first["id"], second["id"]]})
    marker, batch = sources.mark_development_started(trip["id"], first["id"])
    try:
        assert batch == "batch-3"
        newer = media.save_develop(first["id"], jpeg("orange"), {}, expected_batch_id=batch)
        assert newer["variant"] != prior["variant"]
    finally:
        sources.mark_development_finished(trip["id"], marker)


def test_interrupted_development_requires_explicit_audited_recovery(tmp_path):
    import json
    _, media, trip, _, first, _, _, payload = fixture(tmp_path)
    sources = DynamicPhotoSources(media)
    marker, _ = sources.mark_development_started(trip["id"], first["id"])
    path = sources.developing / trip["id"] / f"{marker}.json"
    body = json.loads(path.read_text())
    body["pid"] = -1  # Simulate a process that no longer exists.
    path.write_text(json.dumps(body))
    payload["photos"][0]["status"] = "none"
    with pytest.raises(ContractError) as interrupted:
        sources.settle(trip["id"], payload)
    assert interrupted.value.code == "DEVELOPMENT_INTERRUPTED"
    recovery = sources.resolve_interrupted(trip["id"], marker, "batch-1", "worker exited before saving")
    assert recovery["resolution"] == "interrupted_no_result"
    assert (media.root / "dynamic-photo" / "development-recovery" / f"{marker}.json").is_file()
    assert sources.settle(trip["id"], payload)["status"] == "prepared"


def test_concurrent_settlement_is_one_durable_job(tmp_path):
    _, media, trip, _, first, _, _, payload = fixture(tmp_path)
    media.save_develop(first["id"], jpeg("purple"), {})
    sources = DynamicPhotoSources(media)
    user = current_user.get()
    def settle():
        reset = current_user.set(user)
        try:
            return sources.settle(trip["id"], payload)["id"]
        finally:
            current_user.reset(reset)
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(lambda _: settle(), range(8)))
    assert len(set(ids)) == 1
    assert len(list(sources.root.glob("*.json"))) == 1
    restarted = DynamicPhotoSources(MediaStore(media.root))
    assert restarted.settle(trip["id"], payload)["id"] == ids[0]

    worker = """import json,sys
from pyserver.accounts import current_user
from pyserver.media import MediaStore
from pyserver.media.dynamic_sources import DynamicPhotoSources
current_user.set({'id':'legacy-feature-test','username':'test','role':'admin'})
print(DynamicPhotoSources(MediaStore(sys.argv[1])).settle(sys.argv[2],json.loads(sys.argv[3]))['id'])
"""
    def external():
        return subprocess.run([sys.executable, "-c", worker, str(media.root), trip["id"], json.dumps(payload)],
                              capture_output=True, text=True, check=True, timeout=15).stdout.strip()
    with ThreadPoolExecutor(max_workers=2) as pool:
        external_ids = list(pool.map(lambda _: external(), range(2)))
    assert external_ids == [ids[0], ids[0]]
    assert len(list(sources.root.glob("*.json"))) == 1


def test_http_requires_owner_and_correct_trip(tmp_path, monkeypatch):
    alice = {"id": "alice", "username": "alice", "role": "user"}
    bob = {"id": "bob", "username": "bob", "role": "user"}
    reset = current_user.set(alice)
    try:
        trips, media, trip, other, first, _, _, payload = fixture(tmp_path)
    finally:
        current_user.reset(reset)
    payload["photos"][0]["status"] = "none"
    monkeypatch.setattr(AccountStore, "authenticate", lambda self, token: {"alice-token": alice, "bob-token": bob}.get(token))
    app = create_app(config=ConfigStore(tmp_path / "config.yml"), trips=trips, media=media)

    async def scenario():
        endpoint = f"/api/media/trips/{trip['id']}/dynamic-photo/settle"
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.post(endpoint, json=payload)).status_code == 401
            assert (await client.post(endpoint, json=payload, headers={"Authorization": "Bearer bob-token"})).status_code == 404
            created = await client.post(endpoint, json=payload, headers={"Authorization": "Bearer alice-token"})
            assert created.status_code == 202, created.text
            job_id = created.json()["id"]
            status_url = f"/api/media/dynamic-photo/jobs/{job_id}"
            assert (await client.get(status_url, headers={"Authorization": "Bearer bob-token"})).status_code == 404
            own = await client.get(status_url, headers={"Authorization": "Bearer alice-token"})
            assert own.status_code == 200 and own.json()["sourceSnapshot"]["tripId"] == trip["id"]
            late_save = await client.post(f"/api/media/photos/{first['id']}/develop/save",
                                          headers={"Authorization": "Bearer alice-token"}, json={"params": {}})
            assert late_save.status_code == 409 and late_save.json()["detail"]["code"] == "BATCH_SETTLED"
            assert (await client.post(f"/api/media/trips/{other['id']}/dynamic-photo/settle",
                                      json=payload, headers={"Authorization": "Bearer alice-token"})).status_code == 409
    asyncio.run(scenario())
