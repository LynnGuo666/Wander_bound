"""图片处理，以及选优信号的抽取。

一边是 normalize / enhance：上传时把图归一到长边 2560、去掉 EXIF，或按预设修图；
另一边是 extract_exif：从原图读出拍摄时间、GPS、设备、曝光三要素，加上朝向和
35mm 等效焦距、手持安全快门，供选优判断，读不出就返回空 dict，不影响上传。
对外交付的都是 normalize 后的 JPEG，不带 EXIF，位置信息不外泄。
"""
from __future__ import annotations

import io
import math
import colorsys
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


DEFAULT_DEVELOP = {
    "exposure": 0.0, "contrast": 1.0, "saturation": 1.0, "sharpness": 1.0,
    "highlights": 0.0, "shadows": 0.0, "gamma": 1.0,
    "hsl": {name: {"hue": 0.0, "saturation": 0.0, "luminance": 0.0}
            for name in ("red", "orange", "yellow", "green", "cyan", "blue", "purple", "magenta")},
    "curve": {"master": [0.0, 0.25, 0.5, 0.75, 1.0]},
    "crop": {"left": 0.0, "top": 0.0, "width": 1.0, "height": 1.0},
}

def normalize_develop(params: dict) -> dict:
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise ValueError("修图参数格式无效")
    values = {**DEFAULT_DEVELOP, **params}
    bounds = {"exposure": (-2, 2), "contrast": (0.5, 1.5), "saturation": (0, 2),
              "sharpness": (0, 2), "highlights": (-1, 1), "shadows": (-1, 1), "gamma": (0.5, 1.5)}
    for key, (minimum, maximum) in bounds.items():
        try:
            value = float(values[key])
        except (TypeError, ValueError):
            raise ValueError(f"{key} 必须是数字") from None
        if not math.isfinite(value) or not minimum <= value <= maximum:
            raise ValueError(f"{key} 必须在 {minimum} 到 {maximum} 之间")
        values[key] = value
    crop = values.get("crop") or DEFAULT_DEVELOP["crop"]
    if not isinstance(crop, dict):
        raise ValueError("crop 格式无效")
    try:
        crop = {key: float(crop[key]) for key in ("left", "top", "width", "height")}
    except (KeyError, TypeError, ValueError):
        raise ValueError("crop 格式无效") from None
    if not all(math.isfinite(value) for value in crop.values()) or crop["left"] < 0 or crop["top"] < 0 or crop["width"] <= 0 or crop["height"] <= 0 or crop["left"] + crop["width"] > 1 or crop["top"] + crop["height"] > 1:
        raise ValueError("裁切范围必须在照片边界内")
    values["crop"] = crop
    hsl = values.get("hsl") or DEFAULT_DEVELOP["hsl"]
    if not isinstance(hsl, dict):
        raise ValueError("hsl 格式无效")
    normalized_hsl = {}
    for name in DEFAULT_DEVELOP["hsl"]:
        channel = hsl.get(name) or DEFAULT_DEVELOP["hsl"][name]
        if not isinstance(channel, dict):
            raise ValueError("hsl 格式无效")
        try:
            hue, saturation, luminance = (float(channel.get(key, 0.0)) for key in ("hue", "saturation", "luminance"))
        except (TypeError, ValueError):
            raise ValueError("hsl 参数必须是数字") from None
        if not all(math.isfinite(v) for v in (hue, saturation, luminance)) or not -1 <= hue <= 1 or not -1 <= saturation <= 1 or not -1 <= luminance <= 1:
            raise ValueError("hsl 参数必须在 -1 到 1 之间")
        normalized_hsl[name] = {"hue": hue, "saturation": saturation, "luminance": luminance}
    values["hsl"] = normalized_hsl
    curve = values.get("curve") or DEFAULT_DEVELOP["curve"]
    if not isinstance(curve, dict):
        raise ValueError("curve 格式无效")
    points = curve.get("master", DEFAULT_DEVELOP["curve"]["master"])
    if not isinstance(points, list) or len(points) != 5:
        raise ValueError("curve.master 必须包含 5 个点")
    if points and isinstance(points[0], dict):
        try:
            points = [point["y"] for point in points]
        except (KeyError, TypeError):
            raise ValueError("curve.master 点格式无效") from None
    try:
        points = [float(point) for point in points]
    except (TypeError, ValueError):
        raise ValueError("curve.master 必须是数字") from None
    if not all(math.isfinite(point) and 0 <= point <= 1 for point in points) or any(a > b for a, b in zip(points, points[1:])):
        raise ValueError("curve.master 必须是 0 到 1 之间的递增点")
    values["curve"] = {"master": points}
    return values

def _curve_lut(points):
    return [round(value * 0.65 + max(0, min(1, points[min(4, int(value / 64))] +
        (points[min(4, int(value / 64) + 1)] - points[min(4, int(value / 64))]) * ((value % 64) / 64))) * 255 * 0.35) for value in range(256)]

def _apply_hsl(image, hsl):
    centers = {"red": 0.0, "orange": 30 / 360, "yellow": 60 / 360, "green": 120 / 360,
               "cyan": 180 / 360, "blue": 240 / 360, "purple": 285 / 360, "magenta": 325 / 360}
    pixels = list(image.getdata())
    output = []
    for red, green, blue in pixels:
        hue, lightness, saturation = colorsys.rgb_to_hls(red / 255, green / 255, blue / 255)
        if saturation:
            name = min(centers, key=lambda key: min((hue - centers[key]) % 1, (centers[key] - hue) % 1))
            adjustment = hsl[name]
            hue = (hue + adjustment["hue"] * 0.04) % 1
            saturation = max(0, min(1, saturation * (1 + adjustment["saturation"] * 0.45)))
            lightness = max(0, min(1, lightness + adjustment["luminance"] * 0.07))
        red, green, blue = colorsys.hls_to_rgb(hue, lightness, saturation)
        output.append((round(red * 255), round(green * 255), round(blue * 255)))
    image.putdata(output)
    return image

def develop(image_bytes: bytes, params: dict) -> bytes:
    settings = normalize_develop(params)
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    crop = settings["crop"]
    width, height = image.size
    left, top = round(crop["left"] * width), round(crop["top"] * height)
    box = (left, top, max(left + 1, round((crop["left"] + crop["width"]) * width)),
           max(top + 1, round((crop["top"] + crop["height"]) * height)))
    image = image.crop(box)
    exposure = 2 ** settings["exposure"]
    contrast = settings["contrast"]
    gamma = settings["gamma"]
    highlights = settings["highlights"]
    shadows = settings["shadows"]
    lut = []
    for value in range(256):
        normalized = value / 255
        shadow_weight = max(0, 1 - normalized * 2) ** 1.5
        highlight_weight = max(0, normalized * 2 - 1) ** 1.5
        tone = normalized * exposure
        tone += shadows * shadow_weight * 0.22
        tone -= highlights * highlight_weight * 0.22
        tone = ((tone - 0.5) * contrast + 0.5)
        tone = max(0, min(1, tone)) ** (1 / gamma)
        lut.append(round(tone * 255))
    image = image.point(lut * 3)
    image = image.point(_curve_lut(settings["curve"]["master"]) * 3)
    image = ImageEnhance.Color(image).enhance(settings["saturation"])
    image = _apply_hsl(image, settings["hsl"])
    image = ImageEnhance.Sharpness(image).enhance(settings["sharpness"])
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=92, optimize=True)
    return output.getvalue()

def finish_local_curves(image_bytes: bytes, params: dict) -> bytes:
    settings = normalize_develop(params)
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    lut = []
    for value in range(256):
        normalized = value / 255
        shadow_weight = max(0, 1 - normalized * 2) ** 1.5
        highlight_weight = max(0, normalized * 2 - 1) ** 1.5
        tone = normalized + settings["shadows"] * shadow_weight * 0.22
        tone -= settings["highlights"] * highlight_weight * 0.22
        lut.append(round(max(0, min(1, tone)) * 255))
    image = image.point(lut * 3)
    image = image.point(_curve_lut(settings["curve"]["master"]) * 3)
    image = _apply_hsl(image, settings["hsl"])
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=92, optimize=True)
    return output.getvalue()
