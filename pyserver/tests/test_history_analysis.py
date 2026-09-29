"""History reconstruction must inspect all selected photos, not only curation picks."""
import asyncio
import io
import uuid

from PIL import Image

from pyserver.media import MediaStore
from pyserver.media.analysis_jobs import AnalysisJobs


def test_history_analysis_uses_every_photo_and_skips_curation(tmp_path, monkeypatch):
    image = io.BytesIO()
    Image.new("RGB", (32, 32), "white").save(image, format="JPEG")
    media = MediaStore(tmp_path / "media")
    trip_id = str(uuid.uuid4())
    photo_ids = [media.add(image.getvalue(), trip_id, "2026-01-01", str(index))["id"]
                 for index in range(4)]
    jobs = AnalysisJobs(media)
    monkeypatch.setattr("pyserver.media.analysis_jobs.curate_trip",
                        lambda *_args: (_ for _ in ()).throw(AssertionError("history must not curate")))
    calls = []

    def tag(image_bytes):
        calls.append(image_bytes)
        return {"scene": "机场候机", "location_clue": "机场", "ocr": []}

    monkeypatch.setattr("pyserver.media.analysis_jobs.tag_history_image", tag)
    job = {"id": str(uuid.uuid4()), "tripId": trip_id, "photoIds": photo_ids,
           "purpose": "history", "total": len(photo_ids)}
    asyncio.run(jobs.run_one(job))

    assert job["status"] == "succeeded"
    assert job["completed"] == len(photo_ids) == len(calls)
    assert all(job["results"][pid]["verdict"] == "evidence" for pid in photo_ids)
    assert all(media.get(pid)["tags"]["scene"] == "机场候机" for pid in photo_ids)
