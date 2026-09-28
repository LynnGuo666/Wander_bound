"""选片信号：结构化 EXIF 抽取。只读、不阻断上传、对外下载不泄露位置。"""
from __future__ import annotations

import io
import math
from PIL import Image

from pyserver.media import images


def _jpeg(exif: Image.Exif | None = None) -> bytes:
    image = Image.new("RGB", (96, 64), (120, 130, 140))
    buffer = io.BytesIO()
    if exif is not None:
        image.save(buffer, format="JPEG", exif=exif.tobytes())
    else:
        image.save(buffer, format="JPEG")
    return buffer.getvalue()


def test_helpers():
    assert images._to_float(None) is None
    assert images._to_float((1, 125)) == 1 / 125
    assert images._to_float((5, 0)) == 5
    assert images._to_float(2.8) == 2.8
    assert images._to_float("bad") is None
    assert images._dms_to_deg(((31, 1), (12, 1), (0, 1)), "N") == round(31 + 12 / 60, 6)
    assert images._dms_to_deg(((31, 1), (12, 1), (0, 1)), "S") == -round(31 + 12 / 60, 6)
    assert images._dms_to_deg(((1, 1),), "N") is None


def test_extract_exif_absent_returns_empty():
    assert images.extract_exif(_jpeg()) == {}


def test_extract_exif_base_ifd():
    exif = Image.Exif()
    exif[0x010F] = "TestCam"
    exif[0x0110] = "Model X"
    exif[0x0132] = "2026:10:01 09:30:00"
    out = images.extract_exif(_jpeg(exif))
    assert out["cameraMake"] == "TestCam"
    assert out["cameraModel"] == "Model X"
    assert out["capturedAt"] == "2026:10:01 09:30:00"
    assert out["capturedDay"] == "2026-10-01"


def test_extract_exif_triplet_and_ev():
    exif = Image.Exif()
    ifd = exif.get_ifd(0x8769)
    ifd[0x9003] = "2026:10:01 10:00:00"
    ifd[0x829A] = (1, 125)
    ifd[0x829D] = (28, 10)
    ifd[0x8827] = 200
    exif[0x8769] = ifd
    out = images.extract_exif(_jpeg(exif))
    assert out["fNumber"] == 2.8
    assert abs(out["exposureTime"] - 1 / 125) < 1e-9
    assert out["iso"] == 200
    assert abs(out["exposureValue"] - math.log2(2.8 ** 2 / ((1 / 125) * 2))) < 0.01
    assert out["lighting"] in {"bright", "normal", "low-light"}


def test_extract_exif_gps():
    exif = Image.Exif()
    gps = exif.get_ifd(0x8825)
    gps[1] = ((31, 1), (12, 1), (0, 1))
    gps[2] = "N"
    gps[3] = ((121, 1), (28, 1), (12, 1))
    gps[4] = "E"
    exif[0x8825] = gps
    out = images.extract_exif(_jpeg(exif))
    assert abs(out["gps"]["lat"] - (31 + 12 / 60)) < 1e-6
    assert abs(out["gps"]["lng"] - (121 + 28 / 60 + 12 / 3600)) < 1e-6


def test_store_add_retains_exif(tmp_path):
    from pyserver.media.store import MediaStore
    import uuid

    store = MediaStore(root=tmp_path)
    exif = Image.Exif()
    exif[0x0132] = "2026:10:01 09:30:00"
    ifd = exif.get_ifd(0x8769)
    ifd[0x829D] = (28, 10)
    exif[0x8769] = ifd
    photo = store.add(_jpeg(exif), str(uuid.uuid4()), None)
    assert photo["capturedDay"] == "2026-10-01"
    assert photo["capturedAt"] == "2026:10:01 09:30:00"
    assert photo["exif"]["fNumber"] == 2.8
    assert Image.open(io.BytesIO(store.bytes(photo["id"]))).getexif().get(0x010F) is None
