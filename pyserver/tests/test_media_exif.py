"""选片信号：结构化 EXIF 抽取。只读、不阻断上传、对外下载不泄露位置。"""
from __future__ import annotations

import io
import math
import struct
from fractions import Fraction
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


def _rational(value):
    if isinstance(value, Fraction):
        return (value.numerator, value.denominator)
    if isinstance(value, (tuple, list)) and len(value) == 2:   # 已经是 (num, den)
        return (int(value[0]), int(value[1]))
    return (int(value), 1)


def _exif_with(orientation=None, focal=None, focal_equiv=None, exposure=None,
               model=None, make="TestCam") -> bytes:
    """手工拼一份 EXIF 字节，tag 放在 extract_exif 真正会读的那一层。

    extract_exif 从 image.getexif() 读 IFD0（Make/Model/Orientation），从
    exif.get_ifd(0x8769) 读 Exif IFD（焦距 / 35mm 等效 / 快门）。这里照这个分层摆。
    不走 Pillow 的 Image.Exif.tobytes()：它在 GPS 的 ASCII tag 上会抛 TypeError。
    """
    ifd0, exif_ifd = [], []
    if model:
        ifd0.append((0x0110, 2, model.encode() + b"\x00"))
    if make:
        ifd0.append((0x010F, 2, make.encode() + b"\x00"))
    if orientation is not None:
        ifd0.append((0x0112, 3, struct.pack("<H", orientation)))
    if focal is not None:
        exif_ifd.append((0x920A, 5, struct.pack("<II", int(round(focal)), 1)))
    if focal_equiv is not None:
        exif_ifd.append((0xA405, 5, struct.pack("<II", int(round(focal_equiv * 10)), 10)))
    if exposure is not None:
        num, den = _rational(exposure)
        exif_ifd.append((0x829A, 5, struct.pack("<II", num, den)))

    # Exif IFD 跟在 IFD0 之后；IFD0 第 0 项是 0x8769 指向它
    exif_offset = 8 + (2 + 12 * (len(ifd0) + 1) + 4)
    tail = b""
    exif_packed = struct.pack("<H", len(exif_ifd))
    for tag, kind, value in exif_ifd:
        if len(value) <= 4:
            exif_packed += struct.pack("<HHI", tag, kind, 1) + value.ljust(4, b"\x00")[:4]
        else:
            exif_packed += struct.pack("<HHII", tag, kind, 1, exif_offset + 2 + 12 * len(exif_ifd) + 4 + len(tail))
            tail += value
    exif_packed += struct.pack("<I", 0)

    ifd0_packed = struct.pack("<H", len(ifd0) + 1)
    ifd0_packed += struct.pack("<HHII", 0x8769, 4, 1, exif_offset)   # 指向 Exif IFD
    for tag, kind, value in ifd0:
        if len(value) <= 4:
            ifd0_packed += struct.pack("<HHI", tag, kind, 1) + value.ljust(4, b"\x00")[:4]
        else:
            ifd0_packed += struct.pack("<HHII", tag, kind, len(value),
                                       exif_offset + 2 + 12 * len(exif_ifd) + 4 + len(tail))
            tail += value
    ifd0_packed += struct.pack("<I", 0)
    return b"Exif\x00\x00" + b"II" + struct.pack("<HI", 42, 8) + ifd0_packed + exif_packed + tail


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


# ---- 朝向 / 等效焦距 / 安全快门：废片判据的物理先验 ----


def test_orientation_marks_rotated():
    """Orientation≠1 就是方向记录与观看不一致——竖拍横放这类不用 VLM 目测。"""
    assert images.extract_exif(_jpeg_raw_exif(_exif_with(orientation=1))).get("rotated") is False
    assert images.extract_exif(_jpeg_raw_exif(_exif_with(orientation=6))).get("rotated") is True
    assert images.extract_exif(_jpeg_raw_exif(_exif_with(orientation=3))).get("rotated") is True


def test_focal_equiv_prefers_exif_tag_over_model_guess():
    """EXIF 里带了 35mm 等效焦距就用它，不靠机型猜画幅。"""
    out = images.extract_exif(_jpeg_raw_exif(_exif_with(focal_equiv=85.0, focal=50.0, model="EOS R7")))
    assert out["focalEquiv"] == 85.0          # 直接用 tag，而不是 50×1.5=75


def test_focal_equiv_falls_back_to_crop_factor():
    out = images.extract_exif(_jpeg_raw_exif(_exif_with(focal=50.0, model="ILCE-7M5")))
    assert out["focalEquiv"] == 50.0          # 全幅 crop=1
    out = images.extract_exif(_jpeg_raw_exif(_exif_with(focal=35.0, model="X-T5")))
    assert out["focalEquiv"] == 52.5          # APS-C crop=1.5


def test_focal_equiv_absent_is_none_not_guessed():
    """认不出机型、也没有等效焦距 tag 时不给默认值——猜错会让安全快门整条失效。
    拿不到等效焦距时，干脆不写快门那几个字段，而不是填三个 None 撑场面。
    """
    out = images.extract_exif(_jpeg_raw_exif(_exif_with(focal=50.0, model="MysteryCam")))
    assert "focalEquiv" not in out
    assert "safeShutter" not in out and "shakeRisk" not in out


def test_shake_risk_uses_safe_shutter():
    """安全快门≈1/等效焦距；慢够了才算高风险，缺参数就不判。"""
    # 105mm 等效 → 安全 1/105s≈0.0095；实际 1/4s 慢约 3.6 档 → high
    out = images.extract_exif(_jpeg_raw_exif(_exif_with(exposure=(1, 4), focal_equiv=105.0)))
    assert out["safeShutter"] == round(1 / 105, 6) and out["slowStops"] > 3.0
    assert out["shakeRisk"] == "high"
    # 广角 24mm，1/250s 远快于安全快门 → low
    out = images.extract_exif(_jpeg_raw_exif(_exif_with(exposure=(1, 250), focal_equiv=24.0)))
    assert out["slowStops"] < 0 and out["shakeRisk"] == "low"


def test_shake_risk_needs_both_shutter_and_focal():
    """判安全快门必须同时有快门和等效焦距；缺一个就不写这几个字段。"""
    only_shutter = images.extract_exif(_jpeg_raw_exif(_exif_with(exposure=(1, 8))))
    assert "safeShutter" not in only_shutter and "shakeRisk" not in only_shutter
    only_focal = images.extract_exif(_jpeg_raw_exif(_exif_with(focal_equiv=50.0)))
    assert "safeShutter" not in only_focal
