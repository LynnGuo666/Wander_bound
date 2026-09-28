"""Private JPEG normalization and visual presets."""
from __future__ import annotations

import io
import math
import colorsys
from PIL import Image, ImageEnhance, ImageOps

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
