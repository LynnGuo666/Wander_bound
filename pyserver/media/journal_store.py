"""Private journal pages with page-level user ownership and optimistic revisions."""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path
from threading import RLock

from ..trips import now

MAX_PAGES = 12
MAX_ITEMS = 40
KINDS = {"cover", "photo", "video", "text", "sticker", "postcard", "clip", "ticket", "boarding", "illustration"}


class JournalConflict(ValueError):
    pass


class JournalStore:
    def __init__(self, root: str | Path, templates: list[dict]):
        self.root = Path(root)
        self.templates = {item["id"]: item for item in templates}
        self.lock = RLock()

    def _path(self, trip_id: str) -> Path:
        return self.root / f"{uuid.UUID(trip_id)}.json"

    def _seed_page(self, template_id: str, trip: dict, page_index: int) -> dict:
        title = (trip.get("plan") or {}).get("destination") or trip.get("title") or "旅途"
        items = []
        photo_index = page_index * 2
        for slot in self.templates[template_id]["slots"]:
            item = {**slot, "id": str(uuid.uuid4())}
            if item["kind"] == "photo":
                item["photoIndex"] = photo_index
                photo_index += 1
            elif item["kind"] == "text":
                item["text"] = f"{title}\n写下旅途中最想留住的一刻。"
            elif item["kind"] == "postcard":
                item["text"] = f"{title}\n寄给未来的自己"
            items.append(item)
        return {"templateId": template_id, "items": items, "source": "system", "protected": False}

    def _initial(self, trip: dict) -> dict:
        ids = list(self.templates)
        return {"tripId": trip["id"], "version": 0, "pages": [
            self._seed_page(ids[0], trip, 0), self._seed_page(ids[min(3, len(ids) - 1)], trip, 1)],
            "updatedAt": now()}

    def _read(self, trip: dict) -> dict:
        try:
            document = json.loads(self._path(trip["id"]).read_text())
        except FileNotFoundError:
            return self._initial(trip)
        collage = self.templates.get("book-and-clip", {}).get("slots", [])
        if not collage or collage[-1]["kind"] != "illustration":
            return document
        upgraded = False
        for page in document["pages"]:
            if (page.get("source") != "system" or page.get("protected")
                    or page.get("templateId") != "book-and-clip"):
                continue
            items = page.get("items") or []
            if len(items) != len(collage) - 1 or any(
                    item.get("kind") != slot["kind"] for item, slot in zip(items, collage)):
                continue
            items.append({**collage[-1], "id": str(uuid.uuid4())})
            upgraded = True
        return self._write(document) if upgraded else document

    def get(self, trip: dict) -> dict:
        with self.lock:
            return self._read(trip)

    def _write(self, document: dict) -> dict:
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        document["version"] += 1
        document["updatedAt"] = now()
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.root, delete=False) as temporary:
            os.chmod(temporary.name, 0o600)
            json.dump(document, temporary, ensure_ascii=False)
        os.replace(temporary.name, self._path(document["tripId"]))
        return document

    def _validate_page(self, page: dict) -> dict:
        if not isinstance(page, dict) or page.get("templateId") not in self.templates:
            raise ValueError("手账模板不存在")
        items = page.get("items")
        if not isinstance(items, list) or len(items) > MAX_ITEMS:
            raise ValueError("每页最多 40 个素材")
        ids = set()
        clean = []
        for item in items:
            if not isinstance(item, dict) or item.get("kind") not in KINDS:
                raise ValueError("手账素材类型无效")
            try:
                item_id = str(uuid.UUID(item.get("id", "")))
            except (ValueError, TypeError, AttributeError) as exc:
                raise ValueError("手账素材 ID 无效") from exc
            if item_id in ids:
                raise ValueError("手账素材 ID 重复")
            ids.add(item_id)
            normalized = {"id": item_id, "kind": item["kind"]}
            for name in ("x", "y", "w", "h", "r", "z"):
                value = item.get(name)
                if not isinstance(value, (int, float)) or isinstance(value, bool) or abs(value) > 10000:
                    raise ValueError("手账素材位置无效")
                normalized[name] = value
            if not 1 <= normalized["w"] <= 100 or not 1 <= normalized["h"] <= 100:
                raise ValueError("手账素材尺寸无效")
            if "text" in item:
                if not isinstance(item["text"], str) or len(item["text"]) > 2000:
                    raise ValueError("手账文字过长")
                normalized["text"] = item["text"]
            if "photoIndex" in item:
                if not isinstance(item["photoIndex"], int) or not 0 <= item["photoIndex"] < 10000:
                    raise ValueError("照片序号无效")
                normalized["photoIndex"] = item["photoIndex"]
            for name in ("stickerId", "stampId", "assetId", "photoId", "videoId"):
                if item.get(name):
                    try:
                        normalized[name] = str(uuid.UUID(item[name]))
                    except (ValueError, TypeError, AttributeError) as exc:
                        raise ValueError("素材引用无效") from exc
            clean.append(normalized)
        return {"templateId": page["templateId"], "items": clean}

    def edit_page(self, trip: dict, index: int, page: dict, expected_version: int) -> dict:
        with self.lock:
            document = self._read(trip)
            if document["version"] != expected_version:
                raise JournalConflict("手账已在其他位置更新，请刷新后重试")
            if not 0 <= index < len(document["pages"]):
                raise ValueError("手账页码无效")
            document["pages"][index] = {**self._validate_page(page), "source": "user", "protected": True}
            return self._write(document)

    def append_spread(self, trip: dict, expected_version: int) -> dict:
        with self.lock:
            document = self._read(trip)
            if document["version"] != expected_version:
                raise JournalConflict("手账已在其他位置更新，请刷新后重试")
            if len(document["pages"]) + 2 > MAX_PAGES:
                raise ValueError("每趟旅程最多 12 页")
            ids = list(self.templates)
            first_index = len(document["pages"])
            for offset in range(2):
                page_index = first_index + offset
                page = self._seed_page(ids[page_index % len(ids)], trip, page_index)
                page.update(source="user", protected=True)
                document["pages"].append(page)
            return self._write(document)

    def apply_ai(self, trip: dict, pages: list[dict]) -> dict:
        if not isinstance(pages, list) or len(pages) != 2:
            raise ValueError("AI 每次必须生成左右两页")
        clean = [self._validate_page(page) for page in pages]
        with self.lock:
            document = self._read(trip)
            writable = [index for index, page in enumerate(document["pages"][:2]) if not page["protected"]]
            preserved = [index for index, page in enumerate(document["pages"][:2]) if page["protected"]]
            if not writable:
                if len(document["pages"]) + 2 > MAX_PAGES:
                    raise ValueError("所有页面都由用户修改，且已达到 12 页上限")
                writable = [len(document["pages"]), len(document["pages"]) + 1]
                document["pages"].extend([None, None])
            for source_index, target_index in enumerate(writable):
                template_page = clean[target_index] if target_index < 2 else clean[source_index]
                document["pages"][target_index] = {**template_page, "source": "ai", "protected": False}
            result = self._write(document)
            return {**result, "updatedPageIndices": writable, "preservedPageIndices": preserved}
