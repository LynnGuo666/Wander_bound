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


# EXIF Orientation(0x0112) 取值：1=正常，8/6=旋转90°，5/7= transpose，3=180°，2/4=镜像。
# 只有 1 和 undefined 是"正常方向"；其余说明相机记录的像素方向和观看方向不一致。
_ORIENTATION_NORMAL = {1}

# 传感器画幅 → 等效焦距换算系数(focalLength × crop = 35mm 等效)。
# 只列常见机型片段，命中不了就返回 None，不用默认值猜——猜错会让"安全快门"整条判断失效。
# 匹配按片段长度从长到短，避免 "eos r" 抢先命中全幅而漏掉后面的 APS-C "eos r7"。
_CROP_BY_PREFIX = [
    (("ilce-7m", "ilce-7r", "ilce-7s", "ilce-9", "d850", "d810", "d750", "d6", "d5", "d4",
      "eos r5", "eos r6", "eos r3", "eos r8", "eos 5d", "eos-1d", "eos 6d", "z6", "z7", "z8", "z9",
      "gfx", "gfx", "sl3", "sl2"), 1.0),
    (("xt-5", "xt-4", "xt-3", "x-t5", "x-t4", "x-t3", "x-pro", "x100", "gx9", "gx85",
      "pen-f", "pen e", "om-1", "om-5", "e-m1", "e-m5", "e-m10", "eos r7", "eos r10", "eos r50",
      "eos 7d", "eos 90d", "eos 80d", "eos 77d", "eos m50", "d7200", "d7500", "d500", "z50", "z fc",
      "gr iii", "gr iii", "g7x", "g5x", "ricoh gr"), 1.5),
    (("iphone", "pixel", "sm-g", "sm-s", "mi ", "redmi", "huawei", "mate ", "honor", "oneplus",
      "find x", "reno", "vivo", "oppo", "mi 1", "m2007", "le210", "2201", "2301"), 6.0),
]


def _crop_factor(make=None, model=None):
    """按机型推 crop 系数；认不出返回 None（不猜）。长片段优先，避免误判画幅。"""
    text = f"{make or ''} {model or ''}".strip().lower()
    if not text:
        return None
    # 按片段长度降序匹配：片段越具体越先判
    for prefixes, crop in sorted(_CROP_BY_PREFIX, key=lambda g: -max(len(p) for p in g[0])):
        if any(p in text for p in prefixes):
            return crop
    return None


def _equivalent_focal(focal_length, crop):
    """35mm 等效焦距 = 实际焦距 × crop。缺任一参数返回 None。"""
    if focal_length is None or crop is None:
        return None
    return round(focal_length * crop, 1)


def shake_assessment(exposure_time, focal_equiv):
    """手持安全快门判据：安全速度≈1/等效焦距，实际更慢就有手抖风险。

    返回安全快门值、慢了几档、风险档位。调用方保证两个参数都有才进来；
    这里仍守一次空，宁可不判也不给错判。
    """
    if not exposure_time or exposure_time <= 0 or not focal_equiv or focal_equiv <= 0:
        return {"safeShutter": None, "slowStops": None, "shakeRisk": None}
    safe_shutter = round(1.0 / focal_equiv, 6)
    # 慢几档 = log2(实际快门 / 安全快门)；正数越大手抖风险越高
    slow_stops = round(math.log2(exposure_time / safe_shutter), 2)
    if slow_stops >= 3.0:
        risk = "high"
    elif slow_stops >= 1.0:
        risk = "medium"
    else:
        risk = "low"
    return {"safeShutter": safe_shutter, "slowStops": slow_stops, "shakeRisk": risk}


def extract_exif(image_bytes: bytes) -> dict:
    """抽取结构化 EXIF（时间/GPS/设备/曝光三要素+EV/朝向/安全快门）作选片信号。

    解析失败返回 {}，不阻断上传。对外下载的是 normalize 去 EXIF 后的 JPEG，位置不泄露。
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

        # 朝向：竖拍横放这类"方向错了"是确定性判据，不用 VLM 目测。
        orientation = exif.get(0x0112)
        if orientation is not None:
            result["orientation"] = int(orientation)
            result["rotated"] = int(orientation) not in _ORIENTATION_NORMAL

        # 等效焦距 + 手持安全快门：判"是不是手抖糊"的物理先验，比图像特征更硬。
        focal_equiv_raw = _to_float(exif_ifd.get(0xA405))
        if focal_equiv_raw is not None:
            focal_equiv = round(focal_equiv_raw, 1)
        elif focal is not None:
            focal_equiv = _equivalent_focal(focal, _crop_factor(make, model))
        else:
            focal_equiv = None
        if focal_equiv is not None:
            result["focalEquiv"] = focal_equiv
        # 安全快门：有拍摄参数才判，判不了就不写这几个 key（保持"没信息=空字段"，
        # 别拿三个 None 把结果撑满）。等效焦距拿不到时快门也无从比起。
        if exposure and focal_equiv is not None:
            result.update(shake_assessment(exposure, focal_equiv))

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
