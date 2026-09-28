"""Server-owned selected-original input contracts for local media jobs."""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass


PRODUCT_KINDS = ("scrapbook", "storyboard", "video")
MAX_INPUT_PHOTOS = 32
MAX_PROMPT_LENGTH = 4000


@dataclass(frozen=True)
class ContractError(ValueError):
    code: str
    message: str
    status_code: int = 400

    def __str__(self) -> str:
        return self.message

    def body(self) -> dict:
        return {"code": self.code, "message": self.message}


def _ids(value: object, *, maximum: int) -> list[str]:
    if not isinstance(value, list) or not 1 <= len(value) <= maximum:
        raise ContractError("PHOTO_IDS_INVALID", f"photoIds 必须包含 1–{maximum} 张照片")
    if any(not isinstance(item, str) or not item for item in value):
        raise ContractError("PHOTO_IDS_INVALID", "photoIds 必须是照片 ID 字符串数组")
    if len(value) != len(set(value)):
        raise ContractError("PHOTO_IDS_DUPLICATE", "photoIds 不能重复")
    return value


def _digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def selected_original_snapshot(media, trip_id: str, photo_ids: object,
                               *, maximum: int = MAX_INPUT_PHOTOS) -> dict:
    """Freeze the full committed selection and input originals from server storage."""
    try:
        uuid.UUID(trip_id)
    except (TypeError, ValueError):
        raise ContractError("TRIP_ID_INVALID", "tripId 无效") from None
    requested = _ids(photo_ids, maximum=maximum)
    selection = media.selection_record(trip_id)
    if selection is None:
        raise ContractError("SELECTION_MISSING", "请先提交选优清单", 409)
    committed = selection.get("photoIds")
    if not isinstance(committed, list) or not committed:
        raise ContractError("SELECTION_EMPTY", "选优清单为空，请先选优", 409)
    if (selection.get("tripId") != trip_id or not isinstance(selection.get("batchId"), str)
            or not selection["batchId"] or not isinstance(selection.get("source"), str)
            or not selection["source"] or not isinstance(selection.get("updatedAt"), str)
            or not selection["updatedAt"] or any(not isinstance(item, str) for item in committed)
            or len(committed) != len(set(committed))):
        raise ContractError("SELECTION_INVALID", "已提交选优清单无效", 409)
    selected_set = set(committed)
    originals = []
    for photo_id in requested:
        photo = media.get(photo_id)
        if photo is None:
            raise ContractError("PHOTO_NOT_FOUND", "照片不存在", 404)
        if photo.get("tripId") != trip_id:
            raise ContractError("PHOTO_WRONG_TRIP", "照片不属于该行程", 409)
        if photo_id not in selected_set:
            raise ContractError("PHOTO_NOT_SELECTED", "照片未在选优清单中", 409)
        try:
            original = media.bytes(photo_id, "original")
        except OSError:
            original = None
        if not original:
            raise ContractError("ORIGINAL_UNREADABLE", "规范化原图不可读", 409)
        originals.append({"photoId": photo_id, "sha256": hashlib.sha256(original).hexdigest()})
    selection_fields = {key: selection[key] for key in
                        ("tripId", "batchId", "source", "updatedAt", "photoIds")}
    selection_fields["photoIds"] = list(committed)
    return {"schemaVersion": 1, "tripId": trip_id,
            "selection": {**selection_fields, "sha256": _digest(selection_fields)},
            "inputPhotoIds": list(requested), "originals": originals,
            "inputVariant": "original"}


def original_from_snapshot(media, snapshot: dict, photo_id: str) -> bytes:
    """Read the fixed original; a replaced or deleted original is an error."""
    if not isinstance(snapshot, dict) or snapshot.get("inputVariant") != "original":
        raise ContractError("SNAPSHOT_INVALID", "任务缺少有效的原图快照", 409)
    if photo_id not in snapshot.get("inputPhotoIds", []):
        raise ContractError("SNAPSHOT_INVALID", "照片不在任务输入快照中", 409)
    photo = media.get(photo_id)
    if not photo or photo.get("tripId") != snapshot.get("tripId"):
        raise ContractError("ORIGINAL_UNREADABLE", "任务原图已删除或行程已变化", 409)
    try:
        content = media.bytes(photo_id, "original")
    except OSError:
        content = None
    if not content:
        raise ContractError("ORIGINAL_UNREADABLE", "任务原图不可读", 409)
    expected = next((item.get("sha256") for item in snapshot.get("originals", [])
                     if item.get("photoId") == photo_id), None)
    if not expected or hashlib.sha256(content).hexdigest() != expected:
        raise ContractError("ORIGINAL_CHANGED", "任务原图内容已变化", 409)
    return content


def product_contract(media, payload: object) -> dict:
    """Validate a future product request without pretending a workflow exists yet."""
    if not isinstance(payload, dict) or set(payload) - {"productKind", "tripId", "photoIds", "prompt"}:
        raise ContractError("REQUEST_INVALID", "请求包含未支持字段")
    kind = payload.get("productKind")
    if kind not in PRODUCT_KINDS:
        raise ContractError("PRODUCT_KIND_INVALID", "productKind 必须是 scrapbook、storyboard 或 video")
    prompt = payload.get("prompt")
    if prompt is not None and (not isinstance(prompt, str) or not prompt.strip()
                               or len(prompt) > MAX_PROMPT_LENGTH):
        raise ContractError("PROMPT_INVALID", f"prompt 必须是 1–{MAX_PROMPT_LENGTH} 字符")
    snapshot = selected_original_snapshot(media, payload.get("tripId"), payload.get("photoIds"))
    return {"productKind": kind, "snapshot": snapshot,
            "prompt": prompt.strip() if prompt is not None else None,
            "resultKind": {"scrapbook": "image", "storyboard": "storyboard_json",
                           "video": "video"}[kind]}
