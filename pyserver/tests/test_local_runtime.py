"""Runtime preparation uses synthetic JPEGs and fake Comfy responses only."""
import asyncio
import copy
import json
from pathlib import Path

import httpx

from pyserver.media import workflow_versions
from pyserver.media.jobs import JobStore
from test_generation_contract import fixture


class TrackingAdapter:
    configured = True

    def __init__(self, kind, workflow_file):
        self.kind = kind
        self.workflow_file = Path(workflow_file)
        self.calls = []
        self.states = {}

    def freeze_workflow(self):
        return workflow_versions.freeze_workflow(self.workflow_file, self.kind)

    async def queue(self, image, prompt, seed, *, workflow_snapshot, parameters):
        self.calls.append((image, prompt, seed, copy.deepcopy(workflow_snapshot), copy.deepcopy(parameters)))
        return f"prompt-{len(self.calls)}"

    async def result(self, prompt_id):
        return self.states.get(prompt_id, ("completed", {"filename": "output.mp4" if self.kind == "video" else "output.jpg"}))

    async def download(self, _file):
        from test_generation_contract import jpeg
        return b"fake-video" if self.kind == "video" else jpeg("green")


class Controller:
    def __init__(self):
        self.active = 0
        self.maximum = 0
        self.primary_chat = False

    def use(self, _kind):
        from contextlib import asynccontextmanager
        @asynccontextmanager
        async def context():
            self.active += 1
            self.maximum = max(self.maximum, self.active)
            try:
                yield
            finally:
                self.active -= 1
        return context()


def make_jobs(tmp_path, monkeypatch):
    _, media, _, _, trip, chosen, other, _ = fixture(tmp_path, monkeypatch)
    media.set_selected(trip["id"], {"batchId": "runtime", "source": "test", "photoIds": [chosen["id"], other["id"]]})
    root = Path(__file__).resolve().parents[2] / "workflows"
    image_file = tmp_path / "image.json"
    image_file.write_bytes((root / "qwen-image-2.1-edit-api.json").read_bytes())
    image = TrackingAdapter("image", image_file)
    video = TrackingAdapter("video", root / "minimax-h3-i2v-api.json")
    controller = Controller()
    jobs = JobStore(media, image, video, controller)
    jobs._schedule = lambda: None
    return jobs, image, video, controller, trip, chosen, other


def test_http_parameters_are_bounded_and_persisted(tmp_path, monkeypatch):
    app, media, jobs, _, trip, chosen, _, _ = fixture(tmp_path, monkeypatch)
    media.set_selected(trip["id"], {"batchId": "runtime", "source": "test", "photoIds": [chosen["id"]]})

    async def scenario():
        headers = {"Authorization": "Bearer contract-test-token"}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            url = f"/api/media/photos/{chosen['id']}/redraw"
            accepted = await client.post(url, headers=headers, json={"prompt": "travel", "parameters": {"aspect_ratio": "3:2"}})
            assert accepted.status_code == 202, accepted.text
            saved = jobs.get(accepted.json()["id"])
            assert saved["parameters"] == {"aspect_ratio": "3:2"}
            assert accepted.json()["seed"] == saved["seed"]
            rejected = await client.post(url, headers=headers, json={"prompt": "travel", "parameters": {"aspect_ratio": "4:3"}})
            assert rejected.status_code == 400 and rejected.json()["detail"]["code"] == "WORKFLOW_PARAMETERS_INVALID"
            memory = await client.post("/api/media/memories", headers=headers,
                json={"tripId": trip["id"], "photoIds": [chosen["id"]], "parameters": {"frames": 141}})
            assert memory.status_code == 202, memory.text
            assert jobs.get(memory.json()["id"])["parameters"] == {"aspect_ratio": "16:9", "frames": 141, "fps": 24}
            invalid = await client.post("/api/media/memories", headers=headers,
                json={"tripId": trip["id"], "photoIds": [chosen["id"]], "parameters": {"aspect_ratio": "3:2"}})
            assert invalid.status_code == 400 and invalid.json()["detail"]["code"] == "WORKFLOW_PARAMETERS_INVALID"

    asyncio.run(scenario())


def test_frozen_image_workflow_survives_file_change_and_restart(tmp_path, monkeypatch):
    jobs, image, video, controller, _, chosen, _ = make_jobs(tmp_path, monkeypatch)
    job = jobs.submit("edit", {"photoId": chosen["id"], "prompt": "travel", "parameters": {"aspect_ratio": "3:2"}})
    original = copy.deepcopy(job["workflowSnapshot"])
    assert job["parameters"] == {"aspect_ratio": "3:2"} and isinstance(job["seed"], int)
    graph = json.loads(image.workflow_file.read_text())
    graph["5"]["inputs"]["prompt"] = "new current workflow"
    image.workflow_file.write_text(json.dumps(graph))
    restarted = JobStore(jobs.media, image, video, controller)
    asyncio.run(restarted._run(job["id"]))
    saved = restarted.get(job["id"])
    assert saved["status"] == "succeeded"
    assert image.calls[0][3] == original
    assert image.calls[0][4] == {"aspect_ratio": "3:2"}
    assert image.calls[0][2] == job["seed"]
    assert image.calls[0][0] == jobs.media.bytes(chosen["id"], "original")


def test_old_job_without_workflow_snapshot_fails_before_model(tmp_path, monkeypatch):
    jobs, image, _, controller, _, chosen, _ = make_jobs(tmp_path, monkeypatch)
    job = jobs.submit("edit", {"photoId": chosen["id"], "prompt": "travel"})
    job["promptId"] = "historical-prompt"
    del job["workflowSnapshot"]
    jobs.save(job)
    asyncio.run(jobs._drain())
    assert jobs.get(job["id"])["errorCode"] == "WORKFLOW_SNAPSHOT_INVALID"
    assert controller.maximum == 0 and image.calls == []


def test_failed_prompt_is_terminal_then_explicit_retry_is_bounded(tmp_path, monkeypatch):
    jobs, image, _, _, _, chosen, _ = make_jobs(tmp_path, monkeypatch)
    job = jobs.submit("edit", {"photoId": chosen["id"], "prompt": "travel", "seed": 7})
    image.states["prompt-1"] = ("failed", None)
    asyncio.run(jobs._run(job["id"]))
    assert jobs.get(job["id"])["status"] == "failed" and len(image.calls) == 1
    assert jobs.retry(job["id"], expected_kind="edit")["attempt"] == 2
    assert jobs.get(job["id"]).get("promptId") is None
    image.states["prompt-2"] = ("failed", None)
    asyncio.run(jobs._run(job["id"]))
    assert jobs.retry(job["id"], expected_kind="edit")["attempt"] == 3
    image.states["prompt-3"] = ("failed", None)
    asyncio.run(jobs._run(job["id"]))
    assert jobs.retry(job["id"], expected_kind="edit") is None
    assert len(image.calls) == 3


def test_missing_prompt_and_controller_resource_retries_are_bounded(tmp_path, monkeypatch):
    jobs, image, _, _, _, chosen, _ = make_jobs(tmp_path, monkeypatch)
    job = jobs.submit("edit", {"photoId": chosen["id"], "prompt": "travel"})
    image.states["prompt-1"] = ("missing", None)
    async def fast_sleep(_seconds):
        return None
    monkeypatch.setattr("pyserver.media.jobs.asyncio.sleep", fast_sleep)
    asyncio.run(jobs._run(job["id"]))
    assert jobs.get(job["id"])["status"] == "failed"
    assert len(image.calls) == 1

    class BusyController:
        primary_chat = False
        def use(self, _kind):
            from contextlib import asynccontextmanager
            @asynccontextmanager
            async def context():
                raise RuntimeError("resource busy")
                yield
            return context()
    busy = JobStore(jobs.media, image, None, BusyController())
    busy._schedule = lambda: None
    second = busy.submit("edit", {"photoId": chosen["id"], "prompt": "travel"})
    asyncio.run(busy._drain())
    saved = busy.get(second["id"])
    assert saved["status"] == "failed" and saved["errorCode"] == "RESOURCE_RETRY_EXHAUSTED"
    assert saved["resourceRetries"] == 3


def test_completed_clip_is_not_regenerated_after_restart(tmp_path, monkeypatch):
    jobs, _, video, controller, trip, chosen, other = make_jobs(tmp_path, monkeypatch)
    job = jobs.submit("memory", {"tripId": trip["id"], "photoIds": [chosen["id"], other["id"]], "title": "旅行", "seed": 10})
    assert [clip["seed"] for clip in job["clips"]] == [10, 11]
    assert job["parameters"] == {"aspect_ratio": "16:9", "frames": 124, "fps": 24}
    clip_dir = jobs.root / job["id"]
    clip_dir.mkdir()
    (clip_dir / "0.mp4").write_bytes(b"first clip")
    job["clips"][0].update({"promptId": "already-complete"})
    job["completedClips"] = 1
    jobs.save(job)

    class FakeProcess:
        returncode = 0
        async def communicate(self):
            return b"", b""
    async def fake_ffmpeg(*args, **_kwargs):
        Path(args[-1]).write_bytes(b"combined")
        return FakeProcess()
    monkeypatch.setattr("pyserver.media.jobs.asyncio.create_subprocess_exec", fake_ffmpeg)
    restarted = JobStore(jobs.media, None, video, controller)
    asyncio.run(restarted._run(job["id"]))
    saved = restarted.get(job["id"])
    assert saved["status"] == "succeeded" and len(video.calls) == 1
    assert video.calls[0][2] == 11
    assert (clip_dir / "0.mp4").read_bytes() == b"first clip"
    assert (clip_dir / "memory.mp4").read_bytes() == b"combined"
    assert controller.maximum == 0
