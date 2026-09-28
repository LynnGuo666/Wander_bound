"""L0 算法选优信号：锐度、曝光、dHash 近重复。纯 Pillow，无模型、无网络。

在 VLM 到位前先剔掉糊/曝光崩/连拍冗余，产物可被后续 VLM 打标与排序叠加复用。
"""
from __future__ import annotations

import io
from PIL import Image, ImageFilter, ImageOps, ImageStat

_LAPLACIAN = ImageFilter.Kernel((3, 3), (-1, -1, -1, -1, 8, -1, -1, -1, -1), scale=1)


def load_gray(image_bytes: bytes, max_side: int = 1024) -> Image.Image:
    gray = ImageOps.exif_transpose(Image.open(io.BytesIO(image_bytes))).convert("L")
    if max(gray.size) > max_side:
        gray.thumbnail((max_side, max_side))
    return gray


def blur(gray: Image.Image) -> float:
    """Laplacian 方差：越高越清晰；糊/纯色趋 0。"""
    return round(ImageStat.Stat(gray.filter(_LAPLACIAN)).stddev[0] ** 2, 1)


def exposure(gray: Image.Image) -> dict:
    hist = gray.histogram()
    total = sum(hist) or 1
    clip_low = sum(hist[0:6]) / total
    clip_high = sum(hist[250:256]) / total
    mean = ImageStat.Stat(gray).mean[0]
    verdict = "over" if clip_high > 0.25 else ("under" if clip_low > 0.25 or mean < 16 else "ok")
    return {"mean": round(mean, 1), "clipLow": round(clip_low, 3), "clipHigh": round(clip_high, 3), "verdict": verdict}


def dhash(gray: Image.Image, size: int = 16) -> int:
    small = gray.resize((size + 1, size))
    px = list(small.getdata())
    bits = 0
    width = size + 1
    for row in range(size):
        base = row * width
        for col in range(size):
            bits = (bits << 1) | (1 if px[base + col] > px[base + col + 1] else 0)
    return bits


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def quality(image_bytes: bytes, iso: int | None = None) -> dict:
    gray = load_gray(image_bytes)
    lap = blur(gray)
    exp = exposure(gray)
    flags = []
    if lap < 150:
        flags.append("blurry")
    if exp["verdict"] != "ok":
        flags.append(exp["verdict"])
    if iso and iso >= 1600:
        flags.append("noisy")
    return {
        "blur": lap,
        "sharpness": round(min(1.0, lap / 800.0), 3),
        "exposure": exp,
        "dhashBits": dhash(gray),
        "flags": flags,
        "reject": bool(flags),
    }
