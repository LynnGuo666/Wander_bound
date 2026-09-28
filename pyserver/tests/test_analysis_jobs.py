"""A queued analysis survives a process restart and does not commit selection."""
import asyncio
import io

from PIL import Image

from pyserver.media import MediaStore
from pyserver.media import analysis_jobs as module


def test_resume_analysis_keeps_selection_explicit(tmp_path, monkeypatch):
    media = MediaStore(tmp_path / "media")
    output = io.BytesIO()
    Image.new("RGB", (64, 48), "blue").save(output, format="JPEG")
    trip_id = "abfba2e7-6a13-4cba-8d7a-b75190ea0e2a"
    photo = media.add(output.getvalue(), trip_id, None)
    monkeypatch.setattr(module, "curate_trip", lambda _media, _trip, _target, _ids: {
        "keep": [photo["id"]], "verdicts": {photo["id"]: "keep"}})
    monkeypatch.setattr(module, "tag_image", lambda _bytes: {"scene": "海边", "quality": {"keep": 4, "trash": False}})

    async def scenario():
        first = module.AnalysisJobs(media)
        first.schedule = lambda: None
        queued = first.submit(trip_id, [photo["id"]], "batch-1")
        assert queued["status"] == "queued"
        restarted = module.AnalysisJobs(media)
        await restarted.resume()
        assert restarted.worker is not None
        await restarted.worker
        finished = restarted.get(queued["id"])
        assert finished["status"] == "succeeded"
        assert finished["completed"] == finished["total"] == 1
        assert finished["recommended"] == [photo["id"]]
        assert media.selected(trip_id)["photoIds"] == []

    asyncio.run(scenario())
