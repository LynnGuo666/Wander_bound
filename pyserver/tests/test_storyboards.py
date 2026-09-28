import asyncio
import copy
import json

import httpx
import pytest

from pyserver.media import storyboard_routes, storyboards
from pyserver.media.material_cards import MaterialCards
from pyserver.media.contracts import ContractError
from test_generation_contract import fixture


class Config:
    def credentials(self):
        return {"stepfun": "test-key"}


def setup(tmp_path, monkeypatch):
    app, media, jobs, _, trip, photo, other, _ = fixture(tmp_path, monkeypatch)
    ids = [photo["id"], other["id"]]
    media.set_selected(trip["id"], {"batchId": "boards", "source": "test", "photoIds": ids})
    for pid in ids:
        MaterialCards(media).put(trip["id"], pid, {"expectedVersion": 0, "fields": {
            "sceneDescription": {"value": "山坡和树木", "source": {"kind": "user", "reference": "人工看图"}}}})
    boards = storyboards.Storyboards(jobs, Config())
    from pyserver.trips import TripStore
    app.include_router(storyboard_routes.router_for(TripStore(tmp_path / "trips"), boards))
    return app, media, jobs, boards, trip, ids


def draft_for(ids):
    return {"title": "山间回忆", "shots": [
        {"shotId": f"shot-{i+1}", "photoId": pid, "order": i, "role": "environment",
         "durationSeconds": 5, "prompt": "保留山坡和树木，微风轻拂树叶", "motion": "slow_push",
         "transition": "dissolve"} for i, pid in enumerate(ids)]}


def test_http_draft_edit_confirm_freezes_version_and_never_starts_gpu(tmp_path, monkeypatch):
    app, media, jobs, boards, trip, ids = setup(tmp_path, monkeypatch)
    outbound = []
    async def complete(messages, tools, key):
        outbound.append(copy.deepcopy(messages))
        assert tools == [] and key == "test-key"
        assert all(isinstance(m["content"], str) for m in messages)
        assert not any(word in json.dumps(messages) for word in ('image_url', 'data:image', 'base64'))
        yield {"type": "completion", "message": {"content": json.dumps(draft_for(ids))}, "usage": {}}
    monkeypatch.setattr(storyboards.step, "complete", complete)
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test",
                headers={"Authorization": "Bearer contract-test-token"}) as c:
            res = await c.post('/api/media/storyboards', json={"tripId": trip["id"], "photoIds": ids})
            assert res.status_code == 202, res.text
            job_id = res.json()["id"]
            # New selection cannot change this request's text or original snapshot.
            media.set_selected(trip["id"], {"batchId": "new", "source": "test", "photoIds": [ids[1]]})
            await asyncio.gather(*list(boards.tasks.values()))
            state = (await c.get('/api/media/storyboards/'+job_id)).json()
            assert state["status"] == "draft" and state["version"] == 1
            assert state["draft"]["shots"][0]["frames"] == 124
            assert state["selectionSnapshot"]["selection"]["batchId"] == "boards"
            body = {"version": 1, "draftDigest": state["draftDigest"], "confirmed": False}
            assert (await c.post(f'/api/media/storyboards/{job_id}/confirm', json=body)).status_code == 409
            confirmed = (await c.post(f'/api/media/storyboards/{job_id}/confirm', json={**body,"confirmed":True})).json()
            frozen = copy.deepcopy(confirmed["confirmedSnapshot"])
            draft = state["draft"]
            draft["shots"].reverse()
            for index, shot in enumerate(draft["shots"]):shot["order"] = index
            draft["shots"][0]["durationSeconds"] = 6
            edited = await c.put(f'/api/media/storyboards/{job_id}', json={"expectedVersion":1,"draft":draft})
            assert edited.status_code == 200, edited.text
            assert edited.json()["version"] == 2 and edited.json()["confirmedSnapshot"] is None
            assert edited.json()["draft"]["shots"][0]["frames"] == 141
            assert (await c.post(f'/api/media/storyboards/{job_id}/confirm', json={**body,"confirmed":True})).status_code == 409
            assert jobs.get(job_id)["confirmedVersions"] == [frozen]
            assert not jobs.pending() and jobs.worker is None
            assert len(outbound) == 1
    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["json", "foreign", "timeout"])
def test_bad_step_output_or_timeout_is_bounded_and_visible(tmp_path, monkeypatch, failure):
    _, _, jobs, boards, trip, ids = setup(tmp_path, monkeypatch)
    calls = []
    async def complete(messages, tools, key):
        calls.append(1)
        if failure == "timeout": raise httpx.ReadTimeout("test timeout")
        draft = draft_for(ids); draft["shots"][0]["photoId"] = "foreign"
        yield {"type":"completion","message":{"content":"not JSON" if failure=="json" else json.dumps(draft)}}
    monkeypatch.setattr(storyboards.step, "complete", complete)
    async def scenario():
        job = boards.create(trip["id"], ids)
        await asyncio.gather(*list(boards.tasks.values()))
        result = boards.get(job["id"])
        assert result["status"] == "failed" and result["stepAttempts"] == 2
        assert len(calls) == 2 and not jobs.pending()
    asyncio.run(scenario())


def test_schema_rejects_duplicate_order_type_and_duration():
    ids = ["a", "b"]; selection = {"inputPhotoIds": ids}
    for key, value in (("photoId", "b"), ("order", 2), ("role", []),
                       ("durationSeconds", float("nan")), ("durationSeconds", True),
                       ("durationSeconds", 9), ("motion", "fast_spin")):
        draft = draft_for(ids); draft["shots"][0][key] = value
        with pytest.raises(ContractError):storyboards.validate_draft(draft, selection)


def test_restart_requires_explicit_step_retry_and_missing_description_is_blocked(tmp_path, monkeypatch):
    _, media, jobs, boards, trip, ids = setup(tmp_path, monkeypatch)
    async def slow(*_args):
        await asyncio.sleep(30)
        if False: yield {}
    monkeypatch.setattr(storyboards.step, "complete", slow)
    async def scenario():
        job = boards.create(trip["id"], ids)
        await boards.close()
        saved = jobs.get(job["id"]); saved["status"] = "planning"; jobs.save(saved)
        restarted = storyboards.Storyboards(jobs, Config())
        await restarted.resume()
        assert restarted.get(job["id"])["errorCode"] == "STORYBOARD_INTERRUPTED"
        assert not restarted.tasks
        MaterialCards(media).put(trip["id"], ids[0], {"expectedVersion":1,"fields":{}})
        with pytest.raises(ContractError, match="场景描述"):
            restarted.create(trip["id"], ids)
    asyncio.run(scenario())
