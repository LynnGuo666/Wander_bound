"""Product contracts/CPU layout; actual Qwen evidence is kept separately."""
import asyncio
import io
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest
from PIL import Image

from pyserver.media import scrapbook
from pyserver.media.contracts import ContractError
from pyserver.media.jobs import JobStore
from test_generation_contract import fixture
from test_local_runtime import Controller


def landscape():
    out = io.BytesIO()
    Image.new("RGB", (600, 400), "#bbaa77").save(out, "JPEG")
    return out.getvalue()


def test_missing_title_font_preserves_contract_error(monkeypatch):
    monkeypatch.setattr(scrapbook.Path, "is_file", lambda _path: False)

    @contextmanager
    def request_scope():
        yield

    with pytest.raises(ContractError) as caught:
        with request_scope():
            scrapbook.title_contract("黄石的秋天")
    assert caught.value.code == "TITLE_FONT_UNAVAILABLE"
    assert caught.value.status_code == 503
    assert scrapbook.title_contract("") == ("", None)


def test_scrapbook_http_freezes_inputs_style_and_downloads_after_restart(tmp_path, monkeypatch):
    app, media, jobs, adapter, trip, photo, other, _ = fixture(tmp_path, monkeypatch)
    media.set_selected(trip["id"], {"batchId": "first", "source": "test", "photoIds": [photo["id"]]})
    async def download(_file):
        return landscape()
    adapter.download = download
    jobs.controller = Controller()

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test",
                                     headers={"Authorization": "Bearer contract-test-token"}) as c:
            catalog = await c.get("/api/media/scrapbook-styles")
            assert len(catalog.json()["styles"]) == 5
            assert all("prompt" not in s for s in catalog.json()["styles"])
            request = {"tripId": trip["id"], "photoId": photo["id"], "styleId": "watercolor"}
            response = await c.post("/api/media/scrapbooks", json=request)
            assert response.status_code == 202, response.text
            job_id = response.json()["id"]
            works = await c.get(f"/api/media/trips/{trip['id']}/works")
            assert works.status_code == 200
            assert works.json()["works"][0]["id"] == job_id
            assert "selectionSnapshot" not in works.json()["works"][0]
            assert (await c.get(f"/api/media/trips/{trip['id']}/works",
                                headers={"Authorization": ""})).status_code == 401
            before = jobs.get(job_id)
            assert before["kind"] == "scrapbook" and before["productKind"] == "scrapbook"
            assert (await c.get(f"/api/media/generation-jobs/{job_id}/image")).status_code == 409
            media.set_selected(trip["id"], {"batchId": "second", "source": "test", "photoIds": [other["id"]]})
            monkeypatch.setattr(scrapbook, "style_snapshot", lambda _: (_ for _ in ()).throw(AssertionError("reread preset")))
            await jobs._drain()
            after = jobs.get(job_id)
            assert after["status"] == "succeeded", after
            assert after["selectionSnapshot"] == before["selectionSnapshot"]
            assert adapter.queued[0][0] == media.bytes(photo["id"], "original")
            assert adapter.queued[0][1] == before["styleSnapshot"]["prompt"]
            status = (await c.get(f"/api/media/generation-jobs/{job_id}")).json()
            assert status["resultKind"] == "image" and status["styleVersion"] == "1.1.0"
            for path in ("image", "thumbnail"):
                response = await c.get(f"/api/media/generation-jobs/{job_id}/{path}")
                assert response.status_code == 200
                im = Image.open(io.BytesIO(response.content))
                assert im.width * 2 == im.height * 3
            # Simulate interruption after raw output persists but before CPU completion.
            after.update(status="running", result=None)
            jobs.save(after)
            restarted = JobStore(media, adapter, None, Controller())
            assert restarted._can_finish_without_model(after)
            calls = len(adapter.queued)
            await restarted._drain()
            assert restarted.get(job_id)["status"] == "succeeded"
            assert len(adapter.queued) == calls
    asyncio.run(scenario())


def test_scrapbook_rejects_unselected_cross_trip_style_and_title(tmp_path, monkeypatch):
    app, media, jobs, _, trip, photo, other, foreign = fixture(tmp_path, monkeypatch)
    media.set_selected(trip["id"], {"batchId": "test", "source": "test", "photoIds": [photo["id"]]})
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test",
                                     headers={"Authorization": "Bearer contract-test-token"}) as c:
            base = {"tripId": trip["id"], "photoId": photo["id"], "styleId": "clay"}
            cases = [({"photoId": other["id"]}, "PHOTO_NOT_SELECTED"),
                     ({"photoId": foreign["id"]}, "PHOTO_WRONG_TRIP"),
                     ({"styleId": "oil"}, "STYLE_INVALID"),
                     ({"title": "x" * 33}, "TITLE_INVALID"),
                     ({"title": "a\nb"}, "TITLE_INVALID"),
                     ({"seed": True}, "WORKFLOW_PARAMETERS_INVALID"),
                     ({"selectionSnapshot": {}}, "REQUEST_INVALID")]
            for override, code in cases:
                response = await c.post("/api/media/scrapbooks", json={**base, **override})
                assert response.status_code >= 400, response.text
                assert response.json()["detail"]["code"] == code
            assert not jobs.root.exists() or not list(jobs.root.glob("*.json"))
    asyncio.run(scenario())


def test_title_no_title_and_font_change(tmp_path, monkeypatch):
    raw = landscape()
    for title in ("", "Yellowstone", "黄石的秋天"):
        normalized, font = scrapbook.title_contract(title)
        full, thumb, info = scrapbook.render_page(raw, normalized, font)
        assert info["width"] == 600 and info["height"] == 400
        assert Image.open(io.BytesIO(full)).size == (600, 400)
        assert Image.open(io.BytesIO(thumb)).size == (480, 320)
        if title:
            assert full != scrapbook.render_page(raw, "", None)[0]
            bad_font = {**font, "sha256": "0" * 64}
            with pytest.raises(ContractError, match="字体已变化"):
                scrapbook.render_page(raw, normalized, bad_font)
    with pytest.raises(ContractError):
        scrapbook.title_contract("\U0010ffff")
    out = io.BytesIO(); Image.new("RGB", (600, 399)).save(out, "JPEG")
    with pytest.raises(ContractError, match="3:2"):
        scrapbook.render_page(out.getvalue(), "", None)


def test_scrapbook_queue_is_image_and_cannot_be_released(tmp_path, monkeypatch):
    from pyserver.inference.routes import router_for
    app, media, jobs, _, trip, photo, _, _ = fixture(tmp_path, monkeypatch)
    media.set_selected(trip['id'], {'batchId': 'test', 'source': 'test', 'photoIds': [photo['id']]})
    class StatusController:
        async def status(self):
            return {}
        async def release(self, _name):
            raise AssertionError('must not release queued image model')
    app.include_router(router_for(StatusController(), jobs))
    job = jobs.submit_scrapbook({'tripId': trip['id'], 'photoId': photo['id'], 'styleId': 'clay'})
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test',
                headers={'Authorization':'Bearer contract-test-token'}) as c:
            body = (await c.get('/api/inference/status')).json()
            assert body['queue']['image'] == 1 and body['queue']['video'] == 0
            assert (await c.post('/api/inference/models/image/release')).status_code == 409
    asyncio.run(scenario())
    job['styleSnapshot']['prompt'] = 'changed'
    with pytest.raises(ContractError, match='风格'):
        jobs._validate_job_inputs(job)
