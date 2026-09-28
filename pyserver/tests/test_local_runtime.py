"""Runtime preparation uses synthetic JPEGs and fake Comfy responses only."""
import asyncio
import copy
import json
from pathlib import Path

import httpx
import pytest

from pyserver.media import workflow_versions
from pyserver.media.contracts import ContractError
from pyserver.media.jobs import JobStore
from test_generation_contract import fixture


class TrackingAdapter:
    configured = True

    def __init__(self, kind, workflow_file):
        self.kind = kind
        self.workflow_file = Path(workflow_file)
        self.calls = []
        self.states = {}
        self.next_state = None
        self.response_lost = False
        self.reject_submission = False

    def freeze_workflow(self):
        return workflow_versions.freeze_workflow(self.workflow_file, self.kind)

    async def queue(self, image, prompt, seed, *, prompt_id, workflow_snapshot, parameters):
        self.calls.append((image, prompt, seed, copy.deepcopy(workflow_snapshot), copy.deepcopy(parameters), prompt_id))
        if self.next_state is not None:
            self.states[prompt_id] = self.next_state
            self.next_state = None
        if self.response_lost:
            raise httpx.ReadTimeout("response lost after acceptance")
        if self.reject_submission:
            request = httpx.Request("POST", "http://127.0.0.1/prompt")
            raise httpx.HTTPStatusError("invalid workflow", request=request,
                                        response=httpx.Response(400, request=request))
        return prompt_id

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
            saved_memory = jobs.get(memory.json()["id"])
            assert {key: saved_memory["parameters"][key] for key in ("aspect_ratio", "frames", "fps")} == {"aspect_ratio": "16:9", "frames": 141, "fps": 24}
            assert set(saved_memory["parameters"]) == set(saved_memory["workflowSnapshot"]["parameter_schema"]) - {"seed"}
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


def test_response_lost_reconciles_precommitted_prompt_without_resubmission(tmp_path, monkeypatch):
    jobs, image, video, controller, _, chosen, _ = make_jobs(tmp_path, monkeypatch)
    job = jobs.submit("edit", {"photoId": chosen["id"], "prompt": "travel"})
    image.response_lost = True
    asyncio.run(jobs._run(job["id"]))
    saved = jobs.get(job["id"])
    assert saved["status"] == "succeeded" and saved["submissionState"] == "completed"
    assert saved["promptId"] == image.calls[0][5] and len(image.calls) == 1

    another = jobs.submit("edit", {"photoId": chosen["id"], "prompt": "travel"})
    image.response_lost = False
    original_queue = image.queue
    async def accepted_then_interrupted(*args, **kwargs):
        await original_queue(*args, **kwargs)
        raise asyncio.CancelledError()
    image.queue = accepted_then_interrupted
    try:
        asyncio.run(jobs._run(another["id"]))
    except asyncio.CancelledError:
        pass
    interrupted = jobs.get(another["id"])
    assert interrupted["submissionState"] == "intent_recorded"
    assert interrupted["promptId"] == image.calls[-1][5]
    image.queue = original_queue
    restarted = JobStore(jobs.media, image, video, controller)
    asyncio.run(restarted._run(another["id"]))
    assert restarted.get(another["id"])["status"] == "succeeded"
    assert len(image.calls) == 2


def test_response_lost_and_missing_prompt_fails_without_resubmission(tmp_path, monkeypatch):
    jobs, image, _, _, _, chosen, _ = make_jobs(tmp_path, monkeypatch)
    job = jobs.submit("edit", {"photoId": chosen["id"], "prompt": "travel"})
    image.response_lost = True
    image.next_state = ("missing", None)
    async def fast_sleep(_seconds):
        return None
    monkeypatch.setattr("pyserver.media.jobs.asyncio.sleep", fast_sleep)
    asyncio.run(jobs._run(job["id"]))
    saved = jobs.get(job["id"])
    assert saved["status"] == "failed" and saved["promptId"] == image.calls[0][5]
    assert len(image.calls) == 1
    with pytest.raises(ContractError) as error:
        jobs.retry(job["id"], expected_kind="edit")
    assert error.value.code == "PROMPT_OUTCOME_UNKNOWN"
    assert jobs.get(job["id"]) == saved and len(image.calls) == 1


def test_comfy_validation_rejection_is_bounded_and_retry_keeps_frozen_graph(tmp_path, monkeypatch):
    jobs, image, _, _, _, chosen, _ = make_jobs(tmp_path, monkeypatch)
    job = jobs.submit("edit", {"photoId": chosen["id"], "prompt": "fault injection", "seed": 2026092899})
    frozen = copy.deepcopy(job["workflowSnapshot"])
    image.reject_submission = True
    image.next_state = ("missing", None)
    async def fast_sleep(_seconds):
        return None
    monkeypatch.setattr("pyserver.media.jobs.asyncio.sleep", fast_sleep)
    graph = json.loads(image.workflow_file.read_text())
    graph["6"]["inputs"]["sampler_name"] = "new-default-after-submission"
    image.workflow_file.write_text(json.dumps(graph))
    for attempt in (1, 2, 3):
        image.next_state = ("missing", None)
        asyncio.run(jobs._run(job["id"]))
        saved = jobs.get(job["id"])
        assert saved["status"] == "failed" and saved["attempt"] == attempt
        assert saved["workflowSnapshot"] == frozen
        assert saved["submissionState"] == "rejected"
        if attempt < 3:
            assert jobs.retry(job["id"], expected_kind="edit")["attempt"] == attempt + 1
    assert jobs.retry(job["id"], expected_kind="edit") is None
    assert len(image.calls) == 3
    assert len({call[5] for call in image.calls}) == 3
    assert all(call[3] == frozen for call in image.calls)


def test_http_retry_rejects_ambiguous_image_and_video_without_mutation(tmp_path, monkeypatch):
    app, media, jobs, _, trip, chosen, _, _ = fixture(tmp_path, monkeypatch)
    media.set_selected(trip["id"], {"batchId": "runtime", "source": "test", "photoIds": [chosen["id"]]})
    edit = jobs.submit("edit", {"photoId": chosen["id"], "prompt": "travel"})
    memory = jobs.submit("memory", {"tripId": trip["id"], "photoIds": [chosen["id"]], "title": "旅行"})
    edit.update({"status": "failed", "submissionState": "unknown", "promptId": "old-image-id"})
    memory["clips"][0].update({"submissionState": "accepted", "promptId": "old-video-id"})
    memory["status"] = "failed"
    for job in (edit, memory):
        jobs.save(job)
    before = {job["id"]: jobs.get(job["id"]) for job in (edit, memory)}
    scheduled = []
    jobs._schedule = lambda: scheduled.append(True)

    async def scenario():
        headers = {"Authorization": "Bearer contract-test-token"}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            for path in (f"/api/media/edits/{edit['id']}/retry",
                         f"/api/media/memories/{memory['id']}/retry"):
                response = await client.post(path, headers=headers)
                assert response.status_code == 409
                assert response.json()["detail"]["code"] == "PROMPT_OUTCOME_UNKNOWN"

    asyncio.run(scenario())
    assert not scheduled
    assert all(jobs.get(job_id) == saved for job_id, saved in before.items())


def test_running_and_success_clear_stale_resource_error_but_keep_retry_history(tmp_path, monkeypatch):
    jobs, image, _, _, _, chosen, _ = make_jobs(tmp_path, monkeypatch)
    job = jobs.submit("edit", {"photoId": chosen["id"], "prompt": "travel"})
    job.update({"error": "previous model busy", "errorCode": "RESOURCE_WAIT", "resourceRetries": 2})
    jobs.save(job)
    release = asyncio.Event()
    original_result = image.result
    async def delayed_result(prompt_id):
        await release.wait()
        return await original_result(prompt_id)
    image.result = delayed_result

    async def scenario():
        task = asyncio.create_task(jobs._run(job["id"]))
        for _ in range(100):
            current = jobs.get(job["id"])
            if current["status"] == "running" and current.get("promptId"):
                break
            await asyncio.sleep(0)
        assert current["status"] == "running"
        assert current["error"] is None and "errorCode" not in current
        assert current["resourceRetries"] == 2
        release.set()
        await task
        completed = jobs.get(job["id"])
        assert completed["status"] == "succeeded"
        assert completed["error"] is None and "errorCode" not in completed
        assert completed["resourceRetries"] == 2

    asyncio.run(scenario())


def test_failed_prompt_is_terminal_then_explicit_retry_is_bounded(tmp_path, monkeypatch):
    jobs, image, _, _, _, chosen, _ = make_jobs(tmp_path, monkeypatch)
    job = jobs.submit("edit", {"photoId": chosen["id"], "prompt": "travel", "seed": 7})
    image.next_state = ("failed", None)
    asyncio.run(jobs._run(job["id"]))
    # Explicit retry must allocate another UUID after a terminal failure.
    assert jobs.get(job["id"])["status"] == "failed" and len(image.calls) == 1
    assert jobs.retry(job["id"], expected_kind="edit")["attempt"] == 2
    assert jobs.get(job["id"]).get("promptId") is None
    image.next_state = ("failed", None)
    asyncio.run(jobs._run(job["id"]))
    assert jobs.retry(job["id"], expected_kind="edit")["attempt"] == 3
    image.next_state = ("failed", None)
    asyncio.run(jobs._run(job["id"]))
    assert jobs.retry(job["id"], expected_kind="edit") is None
    assert len(image.calls) == 3
    assert len({call[5] for call in image.calls}) == 3


def test_missing_prompt_and_controller_resource_retries_are_bounded(tmp_path, monkeypatch):
    jobs, image, _, _, _, chosen, _ = make_jobs(tmp_path, monkeypatch)
    job = jobs.submit("edit", {"photoId": chosen["id"], "prompt": "travel"})
    image.next_state = ("missing", None)
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
    assert {key: job["parameters"][key] for key in ("aspect_ratio", "frames", "fps")} == {"aspect_ratio": "16:9", "frames": 124, "fps": 24}
    assert set(job["parameters"]) == set(job["workflowSnapshot"]["parameter_schema"]) - {"seed"}
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
    monkeypatch.setattr(JobStore, "_video_file_valid", staticmethod(lambda path: path.is_file() and path.stat().st_size > 0))
    restarted = JobStore(jobs.media, None, video, controller)
    asyncio.run(restarted._run(job["id"]))
    saved = restarted.get(job["id"])
    assert saved["status"] == "succeeded" and len(video.calls) == 1
    assert video.calls[0][2] == 11
    assert (clip_dir / "0.mp4").read_bytes() == b"first clip"
    assert (clip_dir / "memory.mp4").read_bytes() == b"combined"
    assert (clip_dir / "clips.txt").read_text() == "file '0.mp4'\nfile '1.mp4'"
    assert controller.maximum == 0


def test_retry_completed_clip_composes_without_loading_model(tmp_path, monkeypatch):
    jobs, _, video, _, trip, chosen, _ = make_jobs(tmp_path, monkeypatch)
    job = jobs.submit("memory", {"tripId": trip["id"], "photoIds": [chosen["id"]], "title": "旅行", "seed": 10})
    clip_dir = jobs.root / job["id"]
    clip_dir.mkdir()
    (clip_dir / "0.mp4").write_bytes(b"valid fake clip")
    job["clips"][0].update({"done": True, "promptId": "saved-engine-prompt", "submissionState": "completed"})
    job.update({"status": "failed", "error": "previous concat path failure", "errorCode": "JOB_FAILED", "completedClips": 1})
    jobs.save(job)
    monkeypatch.setattr(JobStore, "_video_file_valid", staticmethod(lambda path: path.is_file() and path.stat().st_size > 0))

    class NoModelController:
        primary_chat = False
        def use(self, _kind):
            raise AssertionError("all local clips must compose without loading a model")

    class FakeProcess:
        returncode = 0
        async def communicate(self):
            return b"", b""
    async def fake_ffmpeg(*args, **_kwargs):
        Path(args[-1]).write_bytes(b"combined")
        return FakeProcess()
    monkeypatch.setattr("pyserver.media.jobs.asyncio.create_subprocess_exec", fake_ffmpeg)
    resumed = JobStore(jobs.media, None, video, NoModelController())
    resumed._schedule = lambda: None
    assert resumed.retry(job["id"], expected_kind="memory")["attempt"] == 2
    asyncio.run(resumed._drain())
    saved = resumed.get(job["id"])
    assert saved["status"] == "succeeded" and saved["clips"][0]["promptId"] == "saved-engine-prompt"
    assert len(video.calls) == 0
    assert (clip_dir / "clips.txt").read_text() == "file '0.mp4'"
    assert (clip_dir / "memory.mp4").read_bytes() == b"combined"


def test_unreadable_video_is_not_a_completed_clip(tmp_path):
    path = tmp_path / "corrupt.mp4"
    path.write_bytes(b"not an MP4")
    assert JobStore._video_file_valid(path) is False


def test_existing_valid_image_recovers_without_loading_model(tmp_path, monkeypatch):
    from test_generation_contract import jpeg
    jobs, image, _, _, _, chosen, _ = make_jobs(tmp_path, monkeypatch)
    job = jobs.submit("edit", {"photoId": chosen["id"], "prompt": "travel"})
    jobs.media.save_variant(chosen["id"], f"ai-{job['id']}", jpeg("green"))
    job.update({"status": "failed", "error": "previous save interruption", "errorCode": "JOB_FAILED"})
    jobs.save(job)

    class NoModelController:
        primary_chat = False
        def use(self, _kind):
            raise AssertionError("existing valid image must recover without loading a model")

    resumed = JobStore(jobs.media, image, None, NoModelController())
    resumed._schedule = lambda: None
    assert resumed.retry(job["id"], expected_kind="edit")["attempt"] == 2
    asyncio.run(resumed._drain())
    saved = resumed.get(job["id"])
    assert saved["status"] == "succeeded" and saved["variant"] == f"ai-{job['id']}"
    assert image.calls == []
