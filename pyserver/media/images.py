"""图片处理，以及选优信号的抽取。

一边是 normalize / enhance：上传时把图归一到长边 2560、去掉 EXIF，或按预设修图；
另一边是 extract_exif：从原图读出拍摄时间、GPS、设备和曝光三要素，供选优判断，
读不出就返回空 dict，不影响上传。对外交付的都是 normalize 后的 JPEG，不带 EXIF，
位置信息不外泄。
"""
from __future__ import annotations

import io
import math
from PIL import Image, ImageEnhance, ImageOps

def _to_float(value):
    if value is None:
        return None
    try:
        if isinstance(value, (tuple, list)) and len(value) == 2:
            numerator, denominator = value
            return float(numerator) / float(denominator) if denominator else float(numerator)
        return float(value)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _dms_to_deg(dms, ref):
    if not dms or len(dms) != 3:
        return None
    parts = [_to_float(part) or 0.0 for part in dms]
    deg = parts[0] + parts[1] / 60 + parts[2] / 3600
    if str(ref).upper() in ("S", "W"):
        deg = -deg
    return round(deg, 6)


def extract_exif(image_bytes: bytes) -> dict:
    """抽取结构化 EXIF（时间/GPS/设备/三要素+EV）作选片信号；解析失败返回 {}，不阻断上传。

    对外下载的是 normalize 去 EXIF 后的 JPEG，位置不会泄露。
    """
    result: dict = {}
    try:
        image = Image.open(io.BytesIO(image_bytes))
        exif = image.getexif()
        exif_ifd = exif.get_ifd(0x8769)
        captured = exif_ifd.get(0x9003) or exif.get(0x0132)
        if captured:
            text = str(captured).strip()
            if text:
                result["capturedAt"] = text
                result["capturedDay"] = text[:10].replace(":", "-")
        make = exif.get(0x010F)
        model = exif.get(0x0110)
        if make:
            result["cameraMake"] = str(make).strip().strip("\x00")
        if model:
            result["cameraModel"] = str(model).strip().strip("\x00")
        focal = _to_float(exif_ifd.get(0x920A))
        if focal is not None:
            result["focalLength"] = round(focal, 1)
        if exif_ifd.get(0x9209) is not None:
            result["flash"] = int(exif_ifd.get(0x9209))
        f_number = _to_float(exif_ifd.get(0x829D))
        exposure = _to_float(exif_ifd.get(0x829A))
        iso = exif_ifd.get(0x8827)
        iso = int(iso) if iso is not None else None
        if f_number:
            result["fNumber"] = round(f_number, 1)
        if exposure:
            result["exposureTime"] = exposure
        if iso:
            result["iso"] = iso
        if f_number and exposure and exposure > 0 and iso:
            ev = math.log2((f_number * f_number) / (exposure * (iso / 100.0)))
            result["exposureValue"] = round(ev, 2)
            result["lighting"] = "bright" if ev >= 12 else ("normal" if ev >= 8 else "low-light")
        gps = exif.get_ifd(0x8825)
        if gps:
            # GPS IFD 的 tag 编号：1/3 是纬度/经度方向(ASCII)，2/4 才是度分秒(RATIONAL)。
            # 早期把纬度的 1、2 传反了，方向字符串当度分秒（长度不是 3）直接返回 None，
            # 于是 lat 恒为 None、GPS 整块写不进去——经纬度都取不到。
            lat = _dms_to_deg(gps.get(2), gps.get(1))
            lon = _dms_to_deg(gps.get(4), gps.get(3))
            if lat is not None and lon is not None:
                altitude = _to_float(gps.get(6))
                result["gps"] = {"lat": lat, "lng": lon}
                if altitude is not None:
                    result["gps"]["alt"] = round(altitude, 1)
    except Exception:
        return {}
    return result


def normalize(image_bytes: bytes) -> tuple[bytes, int, int]:
    image = ImageOps.exif_transpose(Image.open(io.BytesIO(image_bytes))).convert("RGB")
    image.thumbnail((2560, 2560))
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=90, optimize=True)
    return output.getvalue(), image.width, image.height

def enhance(image_bytes: bytes, preset: str) -> bytes:
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    image = ImageEnhance.Contrast(image).enhance(1.08 if preset == "natural" else 1.22)
    image = ImageEnhance.Color(image).enhance(1.08 if preset == "natural" else 0.88)
    image = ImageEnhance.Sharpness(image).enhance(1.1)
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=90, optimize=True)
    return output.getvalue()
