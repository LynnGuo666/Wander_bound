"""Private local photo storage with EXIF removal and trip association."""
from __future__ import annotations

import json
import os
import uuid
from datetime import date
from pathlib import Path


from ..trips import now
from . import images


class MediaStore:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or os.getenv("MEDIA_STORAGE_DIR") or "data/media")
        self.photos_dir = self.root / "photos"
        self.meta_dir = self.root / "metadata"
        self.selections_dir = self.root / "selections"

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

    def selected(self, trip_id: str) -> dict:
        selection = self.selection_record(trip_id)
        if selection is None:
            selection = {"tripId": trip_id, "batchId": None, "source": None, "photoIds": [], "updatedAt": None}
        selection = {**selection}
        selection["photos"] = [photo for photo_id in selection["photoIds"]
                               if (photo := self.get(photo_id)) and photo.get("tripId") == trip_id]
        return selection

    def selection_record(self, trip_id: str) -> dict | None:
        """Return only a real committed selection, without response-only photo data."""
        try:
            uuid.UUID(trip_id)
            selection = json.loads((self.selections_dir / f"{trip_id}.json").read_text())
        except (ValueError, FileNotFoundError, json.JSONDecodeError):
            return None
        return selection if isinstance(selection, dict) else None

    def is_selected(self, photo: dict) -> bool:
        return photo["id"] in self.selected(photo["tripId"])["photoIds"]

    def set_selected(self, trip_id: str, payload: dict) -> dict:
        photo_ids = payload.get("photoIds")
        batch_id = payload.get("batchId")
        source = payload.get("source")
        if (not isinstance(photo_ids, list) or len(photo_ids) > 10000
                or any(not isinstance(item, str) for item in photo_ids)
                or len(photo_ids) != len(set(photo_ids))):
            raise ValueError("photoIds 必须是不重复的照片 ID 数组，最多 10000 张")
        if not isinstance(batch_id, str) or not 1 <= len(batch_id) <= 128:
            raise ValueError("batchId 必须是 1 到 128 字符的字符串")
        if not isinstance(source, str) or not 1 <= len(source) <= 128:
            raise ValueError("source 必须是 1 到 128 字符的字符串")
        if any(not (photo := self.get(photo_id)) or photo.get("tripId") != trip_id for photo_id in photo_ids):
            raise ValueError("photoIds 包含不存在或不属于该行程的照片")
        previous = self.selected(trip_id)
        if all(previous[key] == value for key, value in
               (("batchId", batch_id), ("source", source), ("photoIds", photo_ids))):
            return previous
        self.selections_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        selection = {"tripId": trip_id, "batchId": batch_id, "source": source,
                     "photoIds": photo_ids, "updatedAt": now()}
        destination = self.selections_dir / f"{trip_id}.json"
        temporary = self.selections_dir / f"{trip_id}.{uuid.uuid4().hex}.tmp"
        try:
            temporary.write_text(json.dumps(selection, ensure_ascii=False))
            os.chmod(temporary, 0o600)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        return self.selected(trip_id)

    def add(self, image_bytes: bytes, trip_id: str, captured_day: str | None) -> dict:
        if len(image_bytes) > 15 * 1024 * 1024:
            raise ValueError("图片不能超过 15 MB")
        if captured_day:
            date.fromisoformat(captured_day)
        normalized, width, height = images.normalize(image_bytes)
        photo_id = str(uuid.uuid4())
        self._dirs()
        (self.photos_dir / f"{photo_id}.jpg").write_bytes(normalized)
        photo = {"id": photo_id, "tripId": trip_id, "capturedDay": captured_day, "width": width,
                 "height": height, "analysis": {"width": width, "height": height},
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
        enhanced = images.enhance(self.bytes(photo_id), preset)
        (self.photos_dir / f"{photo_id}-{preset}.jpg").write_bytes(enhanced)
        photo["variants"] = sorted(set([*photo["variants"], preset]))
        (self.meta_dir / f"{photo_id}.json").write_text(json.dumps(photo, ensure_ascii=False))
        return photo

    def save_variant(self, photo_id: str, variant: str, image_bytes: bytes) -> dict:
        photo = self.get(photo_id)
        if not photo or not variant.startswith("ai-"):
            raise ValueError("照片或版本不存在")
        normalized, _, _ = images.normalize(image_bytes)
        filename = self.photos_dir / f"{photo_id}-{variant}.jpg"
        filename.write_bytes(normalized)
        os.chmod(filename, 0o600)
        photo["variants"] = sorted(set([*photo["variants"], variant]))
        (self.meta_dir / f"{photo_id}.json").write_text(json.dumps(photo, ensure_ascii=False))
        return photo

    def save_develop(self, photo_id: str, image_bytes: bytes, settings: dict, note: str = "") -> dict | None:
        photo = self.get(photo_id)
        if not photo:
            return None
        normalized, width, height = images.normalize(image_bytes)
        variant = f"develop-{uuid.uuid4().hex[:12]}"
        filename = self.photos_dir / f"{photo_id}-{variant}.jpg"
        filename.write_bytes(normalized)
        os.chmod(filename, 0o600)
        photo["variants"] = sorted(set([*photo.get("variants", []), variant]))
        photo.setdefault("developments", []).append({"variant": variant, "settings": settings,
            "note": str(note)[:300], "width": width, "height": height, "createdAt": now()})
        (self.meta_dir / f"{photo_id}.json").write_text(json.dumps(photo, ensure_ascii=False))
        return {"photo": photo, "variant": variant}
