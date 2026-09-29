"""New H3 contract tests; fake Comfy output is not model-quality evidence."""
import asyncio
import json
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from PIL import Image

from pyserver.media.comfy import ComfyClient
from pyserver.media.dynamic_h3 import DynamicPhotoH3, choose_canvas, inspect_video
from pyserver.media.dynamic_selection import DynamicPhotoSelector
from pyserver.media.dynamic_sources import DynamicPhotoSources
from pyserver.media import workflow_versions
from pyserver.tests.test_dynamic_selection import ready, verdict
from pyserver.tests.test_workflow_versions import WORKFLOWS, mock_client, uploaded_image


def selected(tmp_path):
    _, sources, job, first, _, _ = ready(tmp_path)
    def analyze(_content, pid):
        return verdict(pid, suitable=pid == first["id"], score=80,
                       reason="水纹适合轻微运动", motion="Small ripples, fixed camera." if pid == first["id"] else None)
    return sources, DynamicPhotoSelector(sources).run(job["id"], analyze), first


def test_canvas_preserves_source_ratio_and_rejects_unsupported_extreme():
    portrait = choose_canvas(600, 900)
    assert portrait["width"] % 32 == portrait["height"] % 32 == 0
    assert portrait["width"] * portrait["height"] <= 768 * 1344
    assert portrait["relativeAspectError"] <= 0.02
    assert portrait["sourceWidth"] == 600 and portrait["sourceHeight"] == 900
    assert choose_canvas(1920, 1080)["relativeAspectError"] == 0
    with pytest.raises(Exception) as unsupported:
        choose_canvas(5000, 100)
    assert unsupported.value.code == "ASPECT_UNSUPPORTED"


def test_dynamic_input_contains_all_pixels_without_crop_or_stretch():
    from io import BytesIO
    image = Image.new("RGB", (600, 900), "red")
    image.putpixel((0, 0), (0, 0, 255))
    image.putpixel((599, 899), (0, 255, 0))
    output = BytesIO()
    image.save(output, format="JPEG", quality=100)
    canvas = choose_canvas(600, 900)
    prepared = workflow_versions.prepare_dynamic_image(output.getvalue(), canvas["width"], canvas["height"])
    result = Image.open(BytesIO(prepared))
    assert result.size == (canvas["width"], canvas["height"])
    assert max(result.getpixel((canvas["width"] // 2, canvas["height"] // 2))) > 100
    assert canvas["paddingX"] <= 32 and canvas["paddingY"] <= 32


def test_dynamic_comfy_queue_changes_only_new_kind_and_freezes_parameters(monkeypatch):
    async def scenario():
        seen = mock_client(monkeypatch)
        dynamic = ComfyClient("http://127.0.0.1:8188", WORKFLOWS / "minimax-h3-i2v-api.json", "dynamic_video")
        snapshot = dynamic.freeze_workflow()
        assert snapshot["workflow_id"] == "travel.minimax-h3.dynamic-photo.i2v"
        parameters = {"width": 864, "height": 1152, "frames": 124, "fps": 24}
        await dynamic.queue(__import__("pyserver.tests.test_dynamic_sources", fromlist=["jpeg"]).jpeg("green", (600, 900)),
                            "Gentle leaves, steady camera.", 42, workflow_snapshot=snapshot,
                            parameters=parameters)
        graph = seen["graphs"][0]
        assert (graph["6"]["inputs"]["width"], graph["6"]["inputs"]["height"]) == (864, 1152)
        assert graph["6"]["inputs"]["length"] == 124 and graph["14"]["inputs"]["fps"] == 24
        assert graph["7"]["inputs"]["noise_seed"] == 42
        assert uploaded_image(seen["uploads"][0]).size == (864, 1152)
        assert snapshot["api_graph"]["6"]["inputs"]["width"] == 1024  # frozen graph unchanged
        with pytest.raises(ValueError):
            await dynamic.queue(b"private", "prompt", 42, workflow_snapshot=snapshot,
                                parameters={"width": 1344, "height": 1344, "frames": 124, "fps": 24})
    asyncio.run(scenario())


def test_h3_intent_persists_prompt_seed_graph_and_reuses_terminal_result(tmp_path, monkeypatch):
    sources, job, first = selected(tmp_path)
    calls = []
    class FakeClient:
        kind = "dynamic_video"
        def freeze_workflow(self):
            return workflow_versions.freeze_workflow(WORKFLOWS / "minimax-h3-i2v-api.json", "dynamic_video")
        async def result(self, prompt_id):
            calls.append(("result", prompt_id))
            return ("missing", None) if not any(item[0] == "queue" for item in calls) else ("completed", {"filename": "fake.mp4"})
        async def queue(self, image, prompt, seed, *, workflow_snapshot, parameters, prompt_id):
            calls.append(("queue", prompt_id, prompt, seed, parameters))
            assert image == sources.read_input(job, first["id"])
            return prompt_id
        async def download(self, file):
            calls.append(("download", file["filename"]))
            return b"fake video for postprocessor stub"
    class Controller:
        @asynccontextmanager
        async def use(self, model):
            assert model == "video"
            calls.append(("controller", model))
            yield
    def fake_finish(raw, final, cover, width, height):
        assert raw.read_bytes().startswith(b"fake video")
        final.write_bytes(b"processed")
        cover.write_bytes(b"cover")
        return {"width": width, "height": height, "frames": 124, "durationSeconds": 124 / 24,
                "hasAudio": False, "fullDecode": True, "sha256": "fake", "coverSha256": "fake"}
    monkeypatch.setattr("pyserver.media.dynamic_h3.finish_video", fake_finish)
    runner = DynamicPhotoH3(sources, FakeClient(), Controller())
    result = asyncio.run(runner.run(job["id"]))
    assert result["status"] == "succeeded" and result["result"]["photoId"] == first["id"]
    assert result["h3"]["promptId"] == next(item[1] for item in calls if item[0] == "queue")
    assert result["h3"]["workflowSnapshot"]["workflow_id"] == "travel.minimax-h3.dynamic-photo.i2v"
    assert result["h3"]["canvas"]["sourceWidth"] == 48
    assert result["result"]["promptVersion"] == "dynamic-photo-selection@1"
    assert asyncio.run(runner.run(job["id"]))["result"] == result["result"]
    assert len([item for item in calls if item[0] == "queue"]) == 1


def test_h3_failure_keeps_selected_target_and_static_snapshot(tmp_path):
    sources, job, first = selected(tmp_path)
    class FakeClient:
        kind = "dynamic_video"
        def freeze_workflow(self):
            return workflow_versions.freeze_workflow(WORKFLOWS / "minimax-h3-i2v-api.json", "dynamic_video")
        async def result(self, prompt_id):
            return "missing", None
        async def queue(self, *args, **kwargs):
            raise RuntimeError("model offline")
    class Controller:
        @asynccontextmanager
        async def use(self, name):
            yield
    result = asyncio.run(DynamicPhotoH3(sources, FakeClient(), Controller()).run(job["id"]))
    assert result["status"] == "failed"
    assert result["selection"]["selectedPhotoId"] == first["id"]
    assert result["sourceSnapshot"] == job["sourceSnapshot"]
    assert result["h3"]["promptId"]
    assert result["h3"]["submissionState"] == "submitting"


def test_unknown_h3_submission_after_process_interruption_never_requeues(tmp_path):
    sources, job, first = selected(tmp_path)
    class Client:
        kind = "dynamic_video"
        def freeze_workflow(self):
            return workflow_versions.freeze_workflow(WORKFLOWS / "minimax-h3-i2v-api.json", "dynamic_video")
        async def queue(self, *args, **kwargs):
            raise KeyboardInterrupt("simulated process death after outbound request started")
        async def result(self, prompt_id):
            return "missing", None
    class Controller:
        @asynccontextmanager
        async def use(self, name):
            yield
    runner = DynamicPhotoH3(sources, Client(), Controller())
    with pytest.raises(KeyboardInterrupt):
        asyncio.run(runner.run(job["id"]))
    persisted = sources.get(job["id"])
    assert persisted["status"] == "generating"
    assert persisted["h3"]["submissionState"] == "submitting"
    recovered = asyncio.run(runner.run(job["id"]))
    assert recovered["status"] == "failed"
    assert recovered["error"]["code"] == "H3_SUBMISSION_UNKNOWN"
    assert recovered["selection"]["selectedPhotoId"] == first["id"]


def test_video_probe_rejects_audio_and_requires_full_decode(tmp_path, monkeypatch):
    output = tmp_path / "video.mp4"
    output.write_bytes(b"synthetic probe fixture")
    calls = []
    streams = [{"codec_type": "video", "codec_name": "h264", "pix_fmt": "yuv420p",
                "width": 320, "height": 256, "nb_read_frames": "124", "avg_frame_rate": "24/1"}]
    def run(command, **kwargs):
        calls.append(command[0])
        if command[0] == "ffprobe":
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps(
                {"streams": streams, "format": {"duration": "5.167"}}))
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr("pyserver.media.dynamic_h3.subprocess.run", run)
    metadata = inspect_video(output, 320, 256)
    assert metadata["frames"] == 124 and metadata["hasAudio"] is False
    assert calls == ["ffprobe", "ffmpeg"]
    streams.append({"codec_type": "audio", "codec_name": "aac"})
    with pytest.raises(Exception) as invalid:
        inspect_video(output, 320, 256)
    assert invalid.value.code == "VIDEO_INVALID"
