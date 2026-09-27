"""Private JPEG normalization and visual presets."""
from __future__ import annotations

import io
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
