"""选片信号：结构化 EXIF 抽取。只读、不阻断上传、对外下载不泄露位置。"""
from __future__ import annotations

import io
import math
import struct
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


def _jpeg_raw_exif(exif: bytes) -> bytes:
    """带原始 EXIF 字节的 JPEG。GPS 样本必须走这条路，原因见 _gps_exif。"""
    image = Image.new("RGB", (96, 64), (120, 130, 140))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", exif=exif)
    return buffer.getvalue()


def _gps_exif(lat, lat_ref, lon, lon_ref, altitude=None) -> bytes:
    """手工拼一份符合 EXIF 规范的 GPS EXIF（小端 TIFF）。

    不用 Image.Exif 构造：Pillow 12 的 Exif.tobytes() 写 GPS IFD 里的 ASCII 标签
    （纬度/经度方向）会抛 TypeError，参数在 write_string 处错位，所以这里直出字节。
    按规范编号：tag1/3 是方向(ASCII)，tag2/4 是度分秒(RATIONAL)，tag6 是海拔。
    """
    def rationals(values):
        return b"".join(struct.pack("<II", value, 1) for value in values)

    entries = [(1, 2, 2), (3, 2, 2), (2, 5, 3), (4, 5, 3)]
    if altitude is not None:
        entries.append((6, 5, 1))
    data_start = 8 + (2 + 12 + 4) + (2 + 12 * len(entries) + 4)  # TIFF 头 + IFD0 + GPS IFD
    inline = {1: lat_ref.encode() + b"\x00", 3: lon_ref.encode() + b"\x00"}
    offsets = {2: data_start, 4: data_start + 24}
    blob = rationals(lat) + rationals(lon)
    if altitude is not None:
        offsets[6] = data_start + 48
        blob += rationals([altitude])

    ifd0 = struct.pack("<H", 1) + struct.pack("<HHII", 0x8825, 4, 1, 8 + 2 + 12 + 4) + struct.pack("<I", 0)
    gps_ifd = struct.pack("<H", len(entries))
    for tag, kind, count in sorted(entries):
        if tag in inline:
            gps_ifd += struct.pack("<HHI", tag, kind, count) + inline[tag].ljust(4, b"\x00")[:4]
        else:
            gps_ifd += struct.pack("<HHII", tag, kind, count, offsets[tag])
    gps_ifd += struct.pack("<I", 0)
    return b"Exif\x00\x00" + b"II" + struct.pack("<HI", 42, 8) + ifd0 + gps_ifd + blob


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
    raw = _jpeg_raw_exif(_gps_exif((31, 12, 0), "N", (121, 28, 12), "E", altitude=120))
    out = images.extract_exif(raw)
    assert abs(out["gps"]["lat"] - (31 + 12 / 60)) < 1e-6
    assert abs(out["gps"]["lng"] - (121 + 28 / 60 + 12 / 3600)) < 1e-6
    assert out["gps"]["alt"] == 120.0


def test_extract_exif_gps_south_west_is_negative():
    """南纬/西经要取负：方向 tag(1/3) 必须落到 ref 位、度分秒 tag(2/4) 落到数值位。"""
    raw = _jpeg_raw_exif(_gps_exif((33, 52, 0), "S", (151, 12, 0), "W"))
    out = images.extract_exif(raw)
    assert abs(out["gps"]["lat"] + (33 + 52 / 60)) < 1e-6
    assert abs(out["gps"]["lng"] + (151 + 12 / 60)) < 1e-6


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
