"""L0 算法选优信号：锐度、曝光、dHash 近重复。纯 Pillow，无模型、无网络。

在 VLM 到位前先剔掉糊/曝光崩/连拍冗余，产物可被后续 VLM 打标与排序叠加复用。
"""
from __future__ import annotations

import io
import numpy as np
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


def _blur_inner(gray: Image.Image) -> float:
    """切掉 1 像素边框后的 Laplacian 方差。

    _LAPLACIAN 这个 kernel 不处理边界：边框那一圈像素保留了原值，平坦区域因此在边框上
    留下一个恒定的假响应（纯色图的 Laplacian 只有 0 和原值两档）。块越小边框占比越高，
    所以分块统计必须用这个版本，否则纯色/糊块都会被边框垫高成“清晰”。
    """
    if min(gray.size) > 2:
        gray = gray.crop((1, 1, gray.width - 1, gray.height - 1))
    return round(ImageStat.Stat(gray.filter(_LAPLACIAN)).stddev[0] ** 2, 1)


def sharpness_map(gray: Image.Image, grid: int = 6) -> dict:
    """分块清晰度图：把图切 grid×grid 块，各块单独算清晰度。

    为什么不全靠全局 blur：全局方差是“平均糊度”，会把两类完全不同的照片混为一谈——
    ① 整幅均匀糊（手抖/拖影/失焦拉满）：每块都低
    ② 浅景深/主体失焦：对焦区清晰、背景虚化，块间差异极大
    前者该拒，后者往往是好照片（虚化人像、特写），拒了就是误杀。

    所以看的是分布而不是均值：块间对比、以及达到清晰线的块占比。
    每块都先切掉边框（见 _blur_inner），否则小块的边框伪影会把平坦区域算成清晰。
    返回的是连续量，不给“是不是失焦”的布尔结论——那需要样本标定阈值，
    也怕把“只有一小块纹理的画面”误判成失焦。
    """
    width, height = gray.size
    block_w, block_h = width // grid, height // grid
    if block_w < 8 or block_h < 8:
        return {"grid": 0, "blocks": [], "contrast": 1.0, "sharpFraction": 0.0, "verdict": "unknown"}
    blocks = []
    for row in range(grid):
        for col in range(grid):
            box = (col * block_w, row * block_h, (col + 1) * block_w, (row + 1) * block_h)
            blocks.append(_blur_inner(gray.crop(box)))
    top = sorted(blocks)[-max(1, len(blocks) // 10):]   # 最清晰的 ~10% 块
    bottom = sorted(blocks)[:max(1, len(blocks) // 10)]  # 最糊的 ~10% 块
    top_mean = sum(top) / len(top)
    bottom_mean = sum(bottom) / len(bottom)
    return {
        "grid": grid,
        "blocks": [round(value, 1) for value in blocks],
        "contrast": round(top_mean / max(bottom_mean, 1.0), 2),   # 清晰块/糊块，越大越“分区明显”
        "sharpFraction": round(sum(1 for b in blocks if b >= 150) / len(blocks), 3),
        "dullFraction": round(sum(1 for b in blocks if b < 150) / len(blocks), 3),
        "verdict": "unknown",
    }


def motion_anisotropy(gray: Image.Image, work: int = 768) -> dict:
    """运动模糊的方向性：模糊会让某个方向的高频响应塌下去。

    原理：运动模糊把能量集中到一个方向上，该方向的梯度响应被压制、正交方向相对保留。
    实测 581 张上海扫街里，行人拖影/畸变的照片竖直向能明显低于正常照片
    （3-6% vs 9-16%），是个有分辨力的连续量。

    但场景本身也带方向性（站台/机场多水平结构、树林多竖直），所以这个量
    **只能当证据、不能当结论**——它分不清"因为拖影而各向异性"和"因为场景本身各向异性"。
    要下结论，须搭配样本标定或交给 VLM 结合画面判断。
    """
    w, h = gray.size
    if max(w, h) > work:
        gray = gray.copy(); gray.thumbnail((work, work))
    a = np.asarray(gray, dtype=np.float64)
    gy, gx = np.gradient(a)
    mag = np.hypot(gx, gy)
    if mag.sum() < 1e-6:
        return {"dominant": "unknown", "anisotropy": 0.0, "weakAxisEnergy": None}
    angle = np.degrees(np.arctan2(gy, gx)) % 180.0
    hist, _ = np.histogram(angle, bins=np.arange(0, 181, 2.0), weights=mag)
    p = hist / hist.sum()
    k = np.convolve(np.r_[p[-8:], p, p[:8]], np.ones(17) / 17, mode="same")[8:-8]
    # 约定：梯度方向 0° = 沿 x 变化 = 竖直边缘（竖条）；90° = 沿 y 变化 = 水平边缘（横条）。
    # 运动模糊沿某个方向涂抹，该方向上的梯度响应会被压制，只剩正交方向。
    edge_vertical = k[0:9].sum() + k[-9:].sum()    # 竖直边缘
    edge_horizontal = k[44:53].sum()               # 水平边缘
    total = max(k.sum(), 1e-9)
    strong, weak = max(edge_vertical, edge_horizontal), min(edge_vertical, edge_horizontal)
    return {
        "dominant": "vertical" if edge_vertical > edge_horizontal else "horizontal",
        "anisotropy": round(abs(edge_vertical - edge_horizontal) / total, 3),
        "weakAxisEnergy": round(weak / total, 3),  # 被压制的那一轴
    }


def quality(image_bytes: bytes, iso: int | None = None) -> dict:
    """汇总单张的质量信号：锐度、曝光、噪声、近重复指纹，并给出该不该拒（reject）。
    模糊（锐度 < 150）、过曝或欠曝、ISO >= 1600，都判为拒。
    """
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
        # 分块清晰度：区分"整幅糊"(该拒)和"浅景深/局部失焦"(常是好片，别误杀)。
        "spatial": sharpness_map(gray),
        # 运动模糊方向性：弱轴能量塌陷是拖影特征，但受场景方向性干扰，只作证据。
        "motion": motion_anisotropy(gray),
    }
