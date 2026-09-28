"""Render 30 continuous page-turn frames from the Qwen-generated binder artwork.

Generation-only dependency: opencv-python-headless, Pillow, numpy. The web client
loads the checked-in animated WebP; no image processing runs in the browser.
"""
from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "public" / "art"
WIDTH, HEIGHT = 1008, 796
Y0, Y1 = 35, 760
HINGE_X = 504
PAGE_WIDTH = 455
FRAME_COUNT = 30

binder = Image.open(ART / "binder-spread.png").convert("RGBA").resize((WIDTH, HEIGHT))
background = Image.new("RGBA", (WIDTH, HEIGHT), (247, 244, 238))
background.alpha_composite(binder)
background_rgb = np.asarray(background.convert("RGB"), dtype=np.uint8)
# The blank ivory page texture and ring hardware both come from the Qwen image.
page = cv2.resize(background_rgb[Y0:Y1, HINGE_X + 35:HINGE_X + PAGE_WIDTH].copy(),
                  (PAGE_WIDTH, Y1 - Y0), interpolation=cv2.INTER_LINEAR)
page_back = cv2.flip(page, 1)
ring_strip = background_rgb[:, HINGE_X - 27:HINGE_X + 27].copy()
source = np.float32([[0, 0], [PAGE_WIDTH - 1, 0], [PAGE_WIDTH - 1, Y1 - Y0 - 1], [0, Y1 - Y0 - 1]])
frames: list[Image.Image] = []

for number in range(FRAME_COUNT):
    raw_progress = number / (FRAME_COUNT - 1)
    progress = .5 - .5 * math.cos(math.pi * raw_progress)
    if number in (0, FRAME_COUNT - 1):
        frame = Image.fromarray(background_rgb, "RGB")
        frames.append(frame)
        frame.save(ART / f"binder-turn-frame-{number + 1:02d}.webp", "WEBP", quality=88, method=4)
        continue
    angle = math.pi * progress
    cosine, sine = math.cos(angle), math.sin(angle)
    # A gentle twist separates the front and back edges at the edge-on phase.
    top_outer = HINGE_X + PAGE_WIDTH * cosine + 37 * sine
    bottom_outer = HINGE_X + PAGE_WIDTH * cosine - 37 * sine
    lift = 9 * sine
    destination = np.float32([
        [HINGE_X, Y0], [top_outer, Y0 - lift],
        [bottom_outer, Y1 + lift], [HINGE_X, Y1],
    ])
    matrix = cv2.getPerspectiveTransform(source, destination)
    texture = page if progress <= .5 else page_back
    warped = cv2.warpPerspective(texture, matrix, (WIDTH, HEIGHT), flags=cv2.INTER_LINEAR,
                                 borderMode=cv2.BORDER_CONSTANT)
    mask = cv2.warpPerspective(np.full(page.shape[:2], 255, dtype=np.uint8), matrix,
                               (WIDTH, HEIGHT), flags=cv2.INTER_LINEAR)
    # A moving, soft cast shadow supplies depth without changing the binder art.
    shadow_shift = 18 * sine * (1 if progress < .5 else -1)
    shifted = cv2.warpAffine(mask, np.float32([[1, 0, shadow_shift], [0, 1, 8 * sine]]),
                             (WIDTH, HEIGHT), flags=cv2.INTER_LINEAR)
    shadow = cv2.GaussianBlur(shifted, (0, 0), sigmaX=21)
    result = background_rgb.astype(np.float32)
    result *= (1 - shadow[:, :, None].astype(np.float32) / 255 * .19)
    # The underside dims smoothly near the center of the turn.
    light = .88 + .12 * abs(cosine)
    if progress > .5:
        light *= .97
    sheet = np.clip(warped.astype(np.float32) * light, 0, 255)
    alpha = mask[:, :, None].astype(np.float32) / 255
    result = result * (1 - alpha) + sheet * alpha
    result = np.clip(result, 0, 255).astype(np.uint8)
    # The Qwen-drawn rings sit in front of the turning sheet at the hinge.
    result[:, HINGE_X - 27:HINGE_X + 27] = ring_strip
    frame = Image.fromarray(result, "RGB")
    frames.append(frame)
    frame.save(ART / f"binder-turn-frame-{number + 1:02d}.webp", "WEBP", quality=88, method=4)

frames[0].save(ART / "binder-turn-30.webp", "WEBP", save_all=True,
               append_images=frames[1:], duration=30, loop=0, quality=88, method=4)
print(f"Rendered {len(frames)} continuous frames from {ART / 'binder-spread.png'}")
