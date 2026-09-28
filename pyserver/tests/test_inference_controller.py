"""The media worker must preserve jobs and never overlap heavy inference."""
import asyncio
import io
from contextlib import asynccontextmanager

import httpx
from PIL import Image as PillowImage

from pyserver.app import create_app
from pyserver.inference.controller import ModelController, ModelSpec
from pyserver.media.jobs import JobStore
from pyserver.media import workflow_versions
from pathlib import Path
from pyserver.media import MediaStore
from pyserver.settings import ConfigStore
from pyserver.trips import TripStore


class Memory:
    def __init__(self, root):
        self.root = root
        self.saved = []
        self.trip_id = "11111111-1111-4111-8111-111111111111"

    def get(self, photo_id):
        return {"id": photo_id, "tripId": self.trip_id}

    def selection_record(self, trip_id):
        return {"tripId": trip_id, "batchId": "controller-test", "source": "fixture",
                "photoIds": ["photo-0", "photo-1", "photo-2"], "updatedAt": "2026-09-28T00:00:00Z"}

    def bytes(self, _photo_id, variant="original"):
        assert variant == "original"
        output = io.BytesIO()
        PillowImage.new("RGB", (8, 8), "red").save(output, format="JPEG")
        return output.getvalue()

    def save_variant(self, photo_id, variant, content):
        self.saved.append((photo_id, variant, content))


class Image:
    configured = True

    def freeze_workflow(self):
        return workflow_versions.freeze_workflow(Path(__file__).resolve().parents[2] / "workflows/qwen-image-2.1-edit-api.json", "image")

    async def queue(self, *_args, **_kwargs):
        return "prompt-id"

    async def result(self, _prompt_id):
        await asyncio.sleep(0.02)
        return "completed", {"filename": "image.png"}

    async def download(self, _file):
        return b"rendered"


class Controller:
    def __init__(self):
        self.active = 0
        self.maximum = 0

    @asynccontextmanager
    async def use(self, name):
        assert name == "image"
        self.active += 1
        self.maximum = max(self.maximum, self.active)
        try:
            yield
        finally:
            self.active -= 1


def test_media_jobs_are_serialized_and_saved(tmp_path):
    async def scenario():
        media, controller = Memory(tmp_path), Controller()
        jobs = JobStore(media, Image(), None, controller)
        ids = [jobs.submit("edit", {"photoId": f"photo-{index}", "prompt": "redraw", "seed": 1})["id"] for index in range(3)]
        await jobs.worker
        assert controller.maximum == 1
        assert [jobs.get(job_id)["status"] for job_id in ids] == ["succeeded"] * 3
        assert all(jobs.get(job_id)["progressPercent"] == 100 for job_id in ids)
        assert len(media.saved) == 3
    asyncio.run(scenario())


def test_media_job_reports_generation_stage(tmp_path):
    class SlowImage(Image):
        def __init__(self, event):
            self.event = event

        async def result(self, _prompt_id):
            await self.event.wait()
            return "completed", {"filename": "image.png"}

    async def scenario():
        event = asyncio.Event()
        jobs = JobStore(Memory(tmp_path), SlowImage(event), None, Controller())
        job = jobs.submit("edit", {"photoId": "photo-1", "prompt": "redraw", "seed": 1})
        for _ in range(50):
            current = jobs.get(job["id"])
            if current["progressLabel"] == "图片生成中":
                break
            await asyncio.sleep(0.01)
        assert current["status"] == "running"
        assert current["progressPercent"] is None
        event.set()
        await jobs.worker
        assert jobs.get(job["id"])["progressPercent"] == 100
    asyncio.run(scenario())


def test_interrupted_job_is_resumed_once(tmp_path):
    async def scenario():
        media = Memory(tmp_path)
        controller = Controller()
        jobs = JobStore(media, Image(), None, controller)
        job = jobs.submit("edit", {"photoId": "photo-1", "prompt": "redraw", "seed": 1})
        await jobs.close()
        resumed = JobStore(media, Image(), None, controller)
        await resumed.resume()
        await resumed.worker
        assert resumed.get(job["id"])["status"] == "succeeded"
        assert len(media.saved) == 1
    asyncio.run(scenario())


def test_busy_comfy_service_cannot_be_stopped():
    class BusyController(ModelController):
        async def _service_state(self, _spec):
            return "active"

        async def _comfy_busy(self, _spec):
            return True

        async def _command(self, *_args, **_kwargs):
            raise AssertionError("must not stop a busy service")

    async def scenario():
        controller = BusyController(enabled=True, specs=(ModelSpec("image", "Image", "image.service", "http://127.0.0.1:1", "/system_stats", 1),))
        try:
            await controller.release("image")
        except RuntimeError as exc:
            assert "仍有任务" in str(exc)
        else:
            raise AssertionError("busy service was stopped")
    asyncio.run(scenario())


def test_background_warm_reports_loading_then_ready():
    class SlowController(ModelController):
        def __init__(self, event):
            super().__init__(enabled=True, specs=(ModelSpec("chat", "Chat", "chat.service", "http://127.0.0.1:1", "/v1/models", 1),))
            self.event = event

        async def _ensure(self, _name):
            await self.event.wait()

    async def scenario():
        event = asyncio.Event()
        controller = SlowController(event)
        controller.begin_warm("chat")
        assert controller.loading_model == "chat"
        assert controller.phase == "loading_model"
        event.set()
        await controller.warm_task
        assert controller.loading_model is None
        assert controller.phase == "cooling"
    asyncio.run(scenario())


def test_primary_chat_shares_with_image_but_yields_to_video():
    specs = (
        ModelSpec("image", "Image", "image.service", "http://127.0.0.1:1", "/system_stats", 1),
        ModelSpec("video", "Video", "video.service", "http://127.0.0.1:2", "/system_stats", 1),
        ModelSpec("chat", "Chat", "chat.service", "http://127.0.0.1:3", "/v1/models", 1),
    )

    class Controller(ModelController):
        def __init__(self):
            super().__init__(enabled=True, specs=specs)
            self.running = {"chat"}
            self.stopped = []
            self.available = 53

        async def _service_state(self, spec):
            return "active" if spec.name in self.running else "stopped"

        async def _ready(self, spec):
            return spec.name in self.running

        async def _stop(self, spec):
            if spec.name in self.running:
                self.running.remove(spec.name)
                self.stopped.append(spec.name)

        async def _start(self, spec):
            self.running.add(spec.name)

        def _memory(self):
            return {"availableGiB": self.available}

    async def scenario():
        controller = Controller()
        await controller._ensure("image")
        assert controller.running == {"chat", "image"}
        controller.available = 32
        await controller._ensure("chat")
        assert controller.running == {"chat", "image"}
        await controller._ensure("video")
        assert controller.running == {"video"}
        assert controller.stopped == ["image", "chat"]
    asyncio.run(scenario())


def test_qwen_loading_progress_uses_current_journal_stage():
    class Controller(ModelController):
        async def _command(self, *_args, **_kwargs):
            return "Loading safetensors checkpoint shards:  57% Completed\nModel loading took 174 seconds\ntorch.compile took 57 seconds"

    async def scenario():
        controller = Controller(enabled=True)
        controller.load_since = "2026-09-28 18:00:00"
        await controller._track_chat_progress(controller.specs["chat"])
        assert controller.load_progress == {"model": "chat", "stage": "编译完成，预热推理内核", "percent": 78, "estimated": True}
    asyncio.run(scenario())


def test_web_status_and_control_auth(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_API_TOKEN", "test-token")
    monkeypatch.delenv("SPARK_MODEL_CONTROL", raising=False)
    app = create_app(config=ConfigStore(tmp_path / "config.yml"), trips=TripStore(tmp_path / "trips"),
                     media=MediaStore(tmp_path / "media"))

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            status = await client.get("/api/inference/status")
            assert status.status_code == 200
            assert status.json()["enabled"] is False
            assert len(status.json()["models"]) == 3
            assert (await client.post("/api/inference/models/image/warm")).status_code == 401
            assert (await client.post("/api/inference/models/unknown/warm", headers={"Authorization": "Bearer test-token"})).status_code == 404
    asyncio.run(scenario())
