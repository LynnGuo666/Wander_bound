"""The media worker must preserve jobs and never overlap heavy inference."""
import asyncio
from contextlib import asynccontextmanager

import httpx

from pyserver.app import create_app
from pyserver.inference.controller import ModelController, ModelSpec
from pyserver.media.jobs import JobStore
from pyserver.media import MediaStore
from pyserver.settings import ConfigStore
from pyserver.trips import TripStore


class Memory:
    def __init__(self, root):
        self.root = root
        self.saved = []

    def bytes(self, _photo_id):
        return b"photo"

    def save_variant(self, photo_id, variant, content):
        self.saved.append((photo_id, variant, content))


class Image:
    configured = True

    async def queue(self, *_args):
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
        assert len(media.saved) == 3
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
