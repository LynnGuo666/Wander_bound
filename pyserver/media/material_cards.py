"""Sourced, text-only descriptions bound to selected normalized originals."""
from __future__ import annotations

import copy
import json
import os
import uuid
from pathlib import Path

from .contracts import ContractError, original_from_snapshot, selected_original_snapshot
from ..trips import now

FIELDS = {"sceneDescription": 800, "subject": 300, "place": 200, "capturedAt": 100}


class MaterialCards:
    def __init__(self, media):
        self.media = media
        self.root = media.root / "material-cards"

    def read(self, photo_id: str) -> dict | None:
        try:
            uuid.UUID(photo_id)
            return json.loads((self.root / (photo_id + ".json")).read_text())
        except (TypeError, ValueError, OSError):
            return None

    def put(self, trip_id: str, photo_id: str, payload: dict) -> dict:
        snapshot = selected_original_snapshot(self.media, trip_id, [photo_id], maximum=1)
        if set(payload) != {"expectedVersion", "fields"} or type(payload["expectedVersion"]) is not int:
            raise ContractError("CARD_INVALID", "素材卡需要expectedVersion和fields")
        previous = self.read(photo_id)
        version = previous["version"] if previous else 0
        if payload["expectedVersion"] != version:
            raise ContractError("CARD_VERSION_CONFLICT", "素材卡已变化，请刷新后保存", 409)
        fields = payload["fields"]
        if not isinstance(fields, dict) or set(fields) - set(FIELDS):
            raise ContractError("CARD_INVALID", "素材卡字段不受支持")
        normalized = {}
        for name, limit in FIELDS.items():
            entry = fields.get(name)
            if entry is None:
                normalized[name] = {"value": None, "source": {"kind": "unknown", "reference": ""}}
                continue
            if not isinstance(entry, dict) or set(entry) != {"value", "source"}:
                raise ContractError("CARD_INVALID", "每个文字字段必须记录value与source")
            value, source = entry["value"], entry["source"]
            if (not isinstance(value, str) or not value.strip() or len(value) > limit
                    or any(ord(char) < 32 for char in value)
                    or not isinstance(source, dict) or set(source) != {"kind", "reference"}
                    or source["kind"] not in {"user", "documented_import"}
                    or not isinstance(source["reference"], str) or not 1 <= len(source["reference"].strip()) <= 500):
                raise ContractError("CARD_INVALID", "文字卡内容或来源格式无效")
            normalized[name] = {"value": value.strip(), "source": copy.deepcopy(source)}
        card = {"schemaVersion": 1, "photoId": photo_id, "tripId": trip_id, "version": version + 1,
                "originalSha256": snapshot["originals"][0]["sha256"], "fields": normalized, "updatedAt": now()}
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.root / (photo_id + ".json")
        temporary = self.root / (photo_id + "." + str(uuid.uuid4()) + ".tmp")
        temporary.write_text(json.dumps(card, ensure_ascii=False)); os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        return card

    def snapshot(self, selection_snapshot: dict) -> list[dict]:
        cards = []
        for original in selection_snapshot["originals"]:
            photo_id = original["photoId"]
            original_from_snapshot(self.media, selection_snapshot, photo_id)
            card = self.read(photo_id)
            if card:
                if card.get("tripId") != selection_snapshot["tripId"] or card.get("originalSha256") != original["sha256"]:
                    raise ContractError("CARD_ORIGINAL_CHANGED", "素材卡对应的原图已变化，请重新核对文字", 409)
                cards.append(copy.deepcopy(card))
            else:
                photo = self.media.get(photo_id)
                fields = {name: {"value": None, "source": {"kind": "unknown", "reference": ""}} for name in FIELDS}
                if photo.get("capturedDay"):
                    fields["capturedAt"] = {"value": photo["capturedDay"],
                                            "source": {"kind": "upload_metadata", "reference": "capturedDay"}}
                cards.append({"schemaVersion": 1, "photoId": photo_id, "tripId": selection_snapshot["tripId"],
                              "version": 0, "originalSha256": original["sha256"], "fields": fields})
        return cards
