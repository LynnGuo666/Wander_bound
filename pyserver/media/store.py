"""私有照片存储，按行程归档。

上传时用 images.normalize 去掉 EXIF、压到长边 2560，下载不会泄露位置；同时用
extract_exif 把结构化 EXIF 存进 metadata 当选优信号。set_quality 供 L0 或 VLM 把
选优分写回照片，供排序和去重复用。上传上限 40 MB，装得下手机和无人机的 48/108MP
原图，归一化之后产物仍然很小。
"""
from __future__ import annotations

import json
import os
import uuid
import base64
import hashlib
import fcntl
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from threading import RLock
from PIL import Image
import io


from ..trips import now
from ..accounts import current_user
from . import images


class MediaStore:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or os.getenv("MEDIA_STORAGE_DIR") or "data/media")
        self.photos_dir = self.root / "photos"
        self.meta_dir = self.root / "metadata"
        self.selections_dir = self.root / "selections"
        self.lock = RLock()

    @staticmethod
    def public_photo(photo: dict) -> dict:
        """Only fields required by clients; private camera and location metadata stays server-side."""
        return {key: photo.get(key) for key in
                ("id", "tripId", "capturedDay", "width", "height", "variants", "createdAt")}

    def _dirs(self):
        self.photos_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.meta_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    def get(self, photo_id: str) -> dict | None:
        try:
            uuid.UUID(photo_id)
            photo = json.loads((self.meta_dir / f"{photo_id}.json").read_text())
            user = current_user.get()
            return photo if user is None or photo.get("ownerId") == user["id"] else None
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

    @contextmanager
    def selection_guard(self, trip_id: str):
        """Serialize a selection update with development saves and batch settlement."""
        uuid.UUID(trip_id)
        self.selections_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.lock:
            with (self.selections_dir / f"{trip_id}.lock").open("a+b") as lock_file:
                os.chmod(lock_file.fileno(), 0o600)
                fcntl.flock(lock_file, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock_file, fcntl.LOCK_UN)

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
        with self.selection_guard(trip_id):
            previous = self.selected(trip_id)
            if all(previous[key] == value for key, value in
                   (("batchId", batch_id), ("source", source), ("photoIds", photo_ids))):
                return previous
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

    def add(self, image_bytes: bytes, trip_id: str, captured_day: str | None,
            asset_key: str | None = None) -> dict:
        if len(image_bytes) > 40 * 1024 * 1024:  # 容纳 48/108MP 原图(可达数十 MB)；normalize 会压到 2560，存储产物仍小
            raise ValueError("图片不能超过 40 MB")
        if asset_key is not None and (not 1 <= len(asset_key) <= 128 or any(ord(c) < 33 for c in asset_key)):
            raise ValueError("资源标识无效")
        digest = hashlib.sha256(image_bytes).hexdigest()
        with self.lock:
            if asset_key:
                for previous in self.list(trip_id):
                    if previous.get("clientAssetKey") == asset_key:
                        if previous.get("sourceSha256") != digest:
                            raise ValueError("资源标识已用于另一张照片")
                        return previous
            normalized, width, height = images.normalize(image_bytes)
            exif = images.extract_exif(image_bytes)
            try:
                source = Image.open(io.BytesIO(image_bytes))
                exif_raw = next((payload for marker, payload in source.applist
                                 if marker == "APP1" and payload.startswith(b"Exif\x00\x00")), b"")
            except (OSError, ValueError, TypeError):
                exif_raw = b""
            captured_at = exif.get("capturedAt")
            day = captured_day or exif.get("capturedDay")
            if day:
                try:
                    date.fromisoformat(day)
                except ValueError:
                    day = None
            photo_id = str(uuid.uuid4())
            self._dirs()
            (self.photos_dir / f"{photo_id}.jpg").write_bytes(normalized)
            photo = {"id": photo_id, "tripId": trip_id, "capturedDay": day, "capturedAt": captured_at,
                     "gps": exif.get("gps"), "width": width, "height": height,
                     "analysis": {"width": width, "height": height}, "exif": exif,
                     "exifRaw": base64.b64encode(exif_raw).decode("ascii") if exif_raw else None,
                     "clientAssetKey": asset_key, "sourceSha256": digest,
                     "ownerId": (current_user.get() or {}).get("id"),
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

    def set_quality(self, photo_id: str, quality_score: dict) -> dict | None:
        """把选优分（锐度、曝光、dHash、flags 等）写回照片 metadata，供后续排序和去重读取。
        """
        photo = self.get(photo_id)
        if not photo:
            return None
        photo["quality"] = quality_score
        meta = self.meta_dir / f"{photo_id}.json"
        meta.write_text(json.dumps(photo, ensure_ascii=False))
        os.chmod(meta, 0o600)
        return photo

    def set_tags(self, photo_id: str, tags: dict) -> dict | None:
        """把 VLM 打标（场景/人物/情绪/物体 + keep/highlight 等）写回照片 metadata，
        供剪辑和回忆编排按内容选取和排序。tags 为空就存空 dict，不阻断后续。
        """
        photo = self.get(photo_id)
        if not photo:
            return None
        photo["tags"] = tags or {}
        meta = self.meta_dir / f"{photo_id}.json"
        meta.write_text(json.dumps(photo, ensure_ascii=False))
        os.chmod(meta, 0o600)
        return photo

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

    def save_develop(self, photo_id: str, image_bytes: bytes, settings: dict, note: str = "",
                     expected_batch_id: str | None = None,
                     expected_selection_updated_at: str | None = None,
                     operation_id: str | None = None) -> dict | None:
        photo = self.get(photo_id)
        if not photo:
            return None
        with self.selection_guard(photo["tripId"]):
            photo = self.get(photo_id)
            selection = self.selection_record(photo["tripId"])
            if (not photo or not selection or photo_id not in selection.get("photoIds", [])
                    or expected_batch_id is not None and selection.get("batchId") != expected_batch_id
                    or expected_selection_updated_at is not None and
                    selection.get("updatedAt") != expected_selection_updated_at):
                return None
            if operation_id is not None:
                operation_id = str(uuid.UUID(operation_id))
                prior = next((item for item in photo.get("developments", [])
                              if item.get("operationId") == operation_id), None)
                if prior:
                    content = self.bytes(photo_id, prior["variant"])
                    if not content:
                        raise ValueError("已保存的精修操作文件丢失")
                    return {"photo": photo, "variant": prior["variant"]}
            variant = (f"develop-{uuid.uuid5(uuid.NAMESPACE_URL, f'travel.develop:{photo_id}:{operation_id}').hex[:12]}"
                       if operation_id else f"develop-{uuid.uuid4().hex[:12]}")
            filename = self.photos_dir / f"{photo_id}-{variant}.jpg"
            if filename.exists():
                normalized, width, height = images.normalize(filename.read_bytes())
            else:
                normalized, width, height = images.normalize(image_bytes)
                filename.write_bytes(normalized)
                os.chmod(filename, 0o600)
            photo["variants"] = sorted(set([*photo.get("variants", []), variant]))
            photo.setdefault("developments", []).append({"variant": variant, "settings": settings,
                "note": str(note)[:300], "width": width, "height": height, "createdAt": now(),
                "selectionBatchId": selection["batchId"], **({"operationId": operation_id} if operation_id else {})})
            metadata = self.meta_dir / f"{photo_id}.json"
            temporary = self.meta_dir / f"{photo_id}.{uuid.uuid4().hex}.tmp"
            try:
                temporary.write_text(json.dumps(photo, ensure_ascii=False))
                os.chmod(temporary, 0o600)
                os.replace(temporary, metadata)
            finally:
                temporary.unlink(missing_ok=True)
            return {"photo": photo, "variant": variant}

    def development_for_operation(self, photo_id: str, operation_id: str) -> dict | None:
        photo = self.get(photo_id)
        if not photo:
            return None
        return next((item for item in photo.get("developments", [])
                     if item.get("operationId") == operation_id), None)

    def development_artifact_for_operation(self, photo_id: str, operation_id: str) -> Path:
        variant = f"develop-{uuid.uuid5(uuid.NAMESPACE_URL, f'travel.develop:{photo_id}:{operation_id}').hex[:12]}"
        return self.photos_dir / f"{photo_id}-{variant}.jpg"
