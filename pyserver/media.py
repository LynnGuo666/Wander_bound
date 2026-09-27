"""Private local photo storage with EXIF removal and trip association."""
from __future__ import annotations

import io
import json
import os
import uuid
from datetime import date
from pathlib import Path

from PIL import Image, ImageEnhance, ImageOps

from .trips import now


class MediaStore:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or os.getenv("MEDIA_STORAGE_DIR") or "data/media")
        self.photos_dir = self.root / "photos"
        self.meta_dir = self.root / "metadata"

    def _dirs(self):
        self.photos_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.meta_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    def get(self, photo_id: str) -> dict | None:
        try:
            uuid.UUID(photo_id)
            return json.loads((self.meta_dir / f"{photo_id}.json").read_text())
        except (ValueError, FileNotFoundError, json.JSONDecodeError):
            return None

    def list(self, trip_id: str) -> list[dict]:
        self._dirs()
        items = [self.get(path.stem) for path in self.meta_dir.glob("*.json")]
        return sorted((item for item in items if item and item.get("tripId") == trip_id),
                      key=lambda item: item.get("capturedDay") or "")

    def add(self, image_bytes: bytes, trip_id: str, captured_day: str | None) -> dict:
        if len(image_bytes) > 15 * 1024 * 1024:
            raise ValueError("图片不能超过 15 MB")
        if captured_day:
            date.fromisoformat(captured_day)
        image = Image.open(io.BytesIO(image_bytes))
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.thumbnail((2560, 2560))
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=90, optimize=True)
        photo_id = str(uuid.uuid4())
        self._dirs()
        (self.photos_dir / f"{photo_id}.jpg").write_bytes(output.getvalue())
        photo = {"id": photo_id, "tripId": trip_id, "capturedDay": captured_day, "width": image.width,
                 "height": image.height, "analysis": {"width": image.width, "height": image.height},
                 "variants": [], "createdAt": now()}
        (self.meta_dir / f"{photo_id}.json").write_text(json.dumps(photo, ensure_ascii=False))
        os.chmod(self.photos_dir / f"{photo_id}.jpg", 0o600)
        os.chmod(self.meta_dir / f"{photo_id}.json", 0o600)
        return photo

    def bytes(self, photo_id: str, variant: str = "original") -> bytes | None:
        photo = self.get(photo_id)
        if not photo or variant not in ["original", *photo.get("variants", [])]:
            return None
        try:
            return (self.photos_dir / f"{photo_id}{'' if variant == 'original' else '-' + variant}.jpg").read_bytes()
        except FileNotFoundError:
            return None

    def enhance(self, photo_id: str, preset: str) -> dict | None:
        photo = self.get(photo_id)
        if not photo:
            return None
        if preset not in {"natural", "cinematic"}:
            raise ValueError("不支持的修图风格")
        image = Image.open(io.BytesIO(self.bytes(photo_id))).convert("RGB")
        image = ImageEnhance.Contrast(image).enhance(1.08 if preset == "natural" else 1.22)
        image = ImageEnhance.Color(image).enhance(1.08 if preset == "natural" else 0.88)
        image = ImageEnhance.Sharpness(image).enhance(1.1)
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=90, optimize=True)
        (self.photos_dir / f"{photo_id}-{preset}.jpg").write_bytes(output.getvalue())
        photo["variants"] = sorted(set([*photo["variants"], preset]))
        (self.meta_dir / f"{photo_id}.json").write_text(json.dumps(photo, ensure_ascii=False))
        return photo

    def save_variant(self, photo_id: str, variant: str, image_bytes: bytes) -> dict:
        photo = self.get(photo_id)
        if not photo or not variant.startswith("ai-"):
            raise ValueError("照片或版本不存在")
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        image.thumbnail((2560, 2560))
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=90, optimize=True)
        filename = self.photos_dir / f"{photo_id}-{variant}.jpg"
        filename.write_bytes(output.getvalue())
        os.chmod(filename, 0o600)
        photo["variants"] = sorted(set([*photo["variants"], variant]))
        (self.meta_dir / f"{photo_id}.json").write_text(json.dumps(photo, ensure_ascii=False))
        return photo
