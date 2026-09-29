"""Committed-selection and settled-development inputs for dynamic photos.

This module prepares immutable source contracts. AI selection and H3 execution
are attached by later stages; a prepared record never claims a video exists.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import time
import uuid
from pathlib import Path

from PIL import Image

from ..accounts import current_user
from ..trips import now
from .contracts import ContractError
from .vision import vision_model
from . import workflow_versions


PRODUCT_VERSION = "dynamic-photo@1"
SELECTOR_PROMPT_VERSION = "dynamic-photo-selection@1"
H3_RUNNER_VERSION = "dynamic-photo-h3@1"


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def _image_info(content: bytes, variant: str) -> tuple[int, int]:
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.format != "JPEG":
                raise ValueError("not JPEG")
            image.load()
            return image.size
    except (OSError, ValueError):
        code = "DEVELOPMENT_UNREADABLE" if variant != "original" else "ORIGINAL_UNREADABLE"
        raise ContractError(code, "已声明的照片版本不可读", 409) from None


class DynamicPhotoSources:
    def __init__(self, media):
        self.media = media
        self.root = media.root / "dynamic-photo" / "jobs"
        self.developing = media.root / "dynamic-photo" / "developing"
        self.batches = media.root / "dynamic-photo" / "batch-operations"

    def begin_batch_operation(self, trip_id: str, payload: dict) -> dict:
        try:
            operation_id = str(uuid.UUID(payload["operationId"]))
        except (KeyError, TypeError, ValueError):
            raise ContractError("OPERATION_ID_INVALID", "批次操作编号必须是 UUID") from None
        if operation_id != payload["operationId"]:
            raise ContractError("OPERATION_ID_INVALID", "批次操作编号必须是规范 UUID")
        owner = (current_user.get() or {}).get("id")
        if not owner:
            raise ContractError("OWNER_MISSING", "需要登录后才能处理精修批次", 401)
        fingerprint = _digest(payload)
        with self.media.selection_guard(trip_id):
            self.batches.mkdir(parents=True, exist_ok=True, mode=0o700)
            path = self.batches / f"{operation_id}.json"
            try:
                existing = json.loads(path.read_text())
            except FileNotFoundError:
                existing = None
            except (OSError, ValueError):
                raise ContractError("OPERATION_INVALID", "已保存的批次操作记录损坏", 409) from None
            if existing:
                if (existing.get("ownerId") != owner or existing.get("tripId") != trip_id
                        or existing.get("payloadSha256") != fingerprint):
                    raise ContractError("OPERATION_CONFLICT", "批次操作编号已用于不同输入", 409)
                self._selection(trip_id, payload["batchId"], payload["selectionUpdatedAt"],
                                [entry["photoId"] for entry in payload["photos"]])
                return existing
            self._selection(trip_id, payload["batchId"], payload["selectionUpdatedAt"],
                            [entry["photoId"] for entry in payload["photos"]])
            receipt = {"operationId": operation_id, "ownerId": owner, "tripId": trip_id,
                       "batchId": payload["batchId"], "selectionUpdatedAt": payload["selectionUpdatedAt"],
                       "payloadSha256": fingerprint, "completedPhotoIds": [],
                       "status": "running", "jobId": None, "createdAt": now(), "updatedAt": now()}
            temporary = self.batches / f"{operation_id}.{uuid.uuid4().hex}.tmp"
            try:
                temporary.write_text(json.dumps(receipt, ensure_ascii=False))
                os.chmod(temporary, 0o600)
                os.link(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
            return receipt

    def update_batch_operation(self, receipt: dict, *, completed_photo_id: str | None = None,
                               job_id: str | None = None) -> dict:
        with self.media.selection_guard(receipt["tripId"]):
            path = self.batches / f"{receipt['operationId']}.json"
            current = json.loads(path.read_text())
            if current["payloadSha256"] != receipt["payloadSha256"]:
                raise ContractError("OPERATION_CONFLICT", "精修批次操作已改变", 409)
            if completed_photo_id and completed_photo_id not in current["completedPhotoIds"]:
                current["completedPhotoIds"].append(completed_photo_id)
            if job_id:
                current["jobId"] = job_id
                current["status"] = "settled"
            current["updatedAt"] = now()
            temporary = self.batches / f"{receipt['operationId']}.{uuid.uuid4().hex}.tmp"
            try:
                temporary.write_text(json.dumps(current, ensure_ascii=False))
                os.chmod(temporary, 0o600)
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
            return current

    def _existing_settlement(self, trip_id: str, selection_sha: str, outcomes: list[dict],
                             execution_sha: str) -> dict | None:
        for path in self.root.glob("*.json"):
            job = self.get(path.stem)
            snapshot = (job or {}).get("sourceSnapshot") or {}
            if (job and job.get("tripId") == trip_id
                    and (snapshot.get("selection") or {}).get("sha256") == selection_sha
                    and (snapshot.get("settlement") or {}).get("photos") == outcomes
                    and ((job.get("executionContract") or {}).get("sha256") == execution_sha)):
                return job
        return None

    def mark_development_started(self, trip_id: str, photo_id: str,
                                 expected_updated_at: str | None = None) -> tuple[str, str]:
        """Record an in-flight save before its slow rendering starts."""
        with self.media.selection_guard(trip_id):
            selection = self.media.selection_record(trip_id)
            photo = self.media.get(photo_id)
            if not selection or not photo or photo.get("tripId") != trip_id or photo_id not in selection.get("photoIds", []):
                raise ContractError("PHOTO_NOT_SELECTED", "照片不在当前精选清单中", 409)
            if expected_updated_at is not None and selection.get("updatedAt") != expected_updated_at:
                raise ContractError("SELECTION_CHANGED", "精选清单版本已改变", 409)
            fields = {key: selection.get(key) for key in ("tripId", "batchId", "source", "updatedAt", "photoIds")}
            # Any settlement for this exact committed selection closes it.
            for path in self.root.glob("*.json"):
                job = self.get(path.stem)
                if (job and job.get("tripId") == trip_id
                        and ((job.get("sourceSnapshot") or {}).get("selection") or {}).get("sha256") == _digest(fields)):
                    raise ContractError("BATCH_SETTLED", "该批精修已结算", 409)
            marker_id = str(uuid.uuid4())
            folder = self.developing / trip_id
            folder.mkdir(parents=True, exist_ok=True, mode=0o700)
            marker = folder / f"{marker_id}.json"
            temporary = folder / f"{marker_id}.tmp"
            try:
                temporary.write_text(json.dumps({"photoId": photo_id, "batchId": selection["batchId"],
                                                 "startedAt": now(), "startedAtEpoch": time.time(), "pid": os.getpid()}))
                os.chmod(temporary, 0o600)
                os.replace(temporary, marker)
            finally:
                temporary.unlink(missing_ok=True)
            return marker_id, selection["batchId"]

    def mark_development_finished(self, trip_id: str, marker_id: str) -> None:
        with self.media.selection_guard(trip_id):
            (self.developing / trip_id / f"{uuid.UUID(marker_id)}.json").unlink(missing_ok=True)

    @staticmethod
    def _attempt_state(marker: dict) -> str:
        pid = marker.get("pid")
        if not isinstance(pid, int) or pid <= 0:
            return "interrupted"
        try:
            os.kill(pid, 0)
            return "in_progress"
        except ProcessLookupError:
            return "interrupted"
        except PermissionError:
            return "in_progress"

    def list_developments(self, trip_id: str) -> list[dict]:
        records = []
        with self.media.selection_guard(trip_id):
            for path in (self.developing / trip_id).glob("*.json"):
                try:
                    marker = json.loads(path.read_text())
                    records.append({"id": path.stem, "photoId": marker.get("photoId"),
                                    "batchId": marker.get("batchId"), "startedAt": marker.get("startedAt"),
                                    "state": self._attempt_state(marker)})
                except (OSError, ValueError):
                    records.append({"id": path.stem, "state": "interrupted"})
        return records

    def resolve_interrupted(self, trip_id: str, marker_id: str, batch_id: str, reason: str) -> dict:
        try:
            marker_id = str(uuid.UUID(marker_id))
        except (TypeError, ValueError):
            raise ContractError("ATTEMPT_INVALID", "精修尝试编号无效") from None
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 300:
            raise ContractError("RECOVERY_REASON_REQUIRED", "需记录精修中断原因")
        with self.media.selection_guard(trip_id):
            path = self.developing / trip_id / f"{marker_id}.json"
            try:
                marker = json.loads(path.read_text())
            except (OSError, ValueError):
                raise ContractError("ATTEMPT_NOT_FOUND", "精修尝试不存在", 404) from None
            if marker.get("batchId") != batch_id:
                raise ContractError("BATCH_CHANGED", "精修尝试不属于所指批次", 409)
            if self._attempt_state(marker) != "interrupted":
                raise ContractError("DEVELOPMENT_IN_PROGRESS", "精修进程仍在运行", 409)
            receipt = {"id": marker_id, "tripId": trip_id, "photoId": marker.get("photoId"),
                       "batchId": batch_id, "resolution": "interrupted_no_result",
                       "reason": reason.strip(), "resolvedAt": now()}
            folder = self.media.root / "dynamic-photo" / "development-recovery"
            folder.mkdir(parents=True, exist_ok=True, mode=0o700)
            destination = folder / f"{marker_id}.json"
            temporary = folder / f"{marker_id}.{uuid.uuid4().hex}.tmp"
            try:
                temporary.write_text(json.dumps(receipt, ensure_ascii=False))
                os.chmod(temporary, 0o600)
                os.replace(temporary, destination)
            finally:
                temporary.unlink(missing_ok=True)
            path.unlink()
            return receipt

    def _in_flight(self, trip_id: str, batch_id: str) -> str | None:
        for path in (self.developing / trip_id).glob("*.json"):
            try:
                marker = json.loads(path.read_text())
                if marker.get("batchId") == batch_id:
                    return self._attempt_state(marker)
            except (OSError, ValueError):
                return "interrupted"
        return None

    def get(self, job_id: str) -> dict | None:
        try:
            if str(uuid.UUID(job_id)) != job_id:
                return None
            record = json.loads((self.root / f"{job_id}.json").read_text())
            user = current_user.get()
            return record if user is None or record.get("ownerId") == user["id"] else None
        except (ValueError, FileNotFoundError, json.JSONDecodeError, TypeError):
            return None

    def _selection(self, trip_id: str, batch_id: str, updated_at: str, photo_ids: list[str]) -> dict:
        try:
            if str(uuid.UUID(trip_id)) != trip_id:
                raise ValueError("noncanonical trip ID")
        except (TypeError, ValueError):
            raise ContractError("TRIP_ID_INVALID", "tripId 无效") from None
        record = self.media.selection_record(trip_id)
        if not record or not record.get("photoIds"):
            raise ContractError("SELECTION_MISSING", "请先提交非空精选清单", 409)
        fields = {key: record.get(key) for key in ("tripId", "batchId", "source", "updatedAt", "photoIds")}
        if (fields["tripId"] != trip_id or fields["batchId"] != batch_id
                or fields["updatedAt"] != updated_at or fields["photoIds"] != photo_ids
                or not isinstance(fields["source"], str) or not fields["source"]):
            raise ContractError("SELECTION_CHANGED", "精选批次或清单已改变，请重新读取", 409)
        return {**fields, "sha256": _digest(fields)}

    def settle(self, trip_id: str, payload: dict) -> dict:
        if not isinstance(payload, dict) or set(payload) != {"batchId", "selectionUpdatedAt", "photos"}:
            raise ContractError("SETTLEMENT_INVALID", "结算请求字段无效")
        batch_id, updated_at, outcomes = (payload[key] for key in ("batchId", "selectionUpdatedAt", "photos"))
        if (not isinstance(batch_id, str) or not batch_id or not isinstance(updated_at, str)
                or not updated_at or not isinstance(outcomes, list) or not outcomes or len(outcomes) > 10000):
            raise ContractError("SETTLEMENT_INVALID", "结算批次与照片清单无效")
        photo_ids = []
        for item in outcomes:
            if (not isinstance(item, dict) or set(item) != {"photoId", "status"}
                    or not isinstance(item["photoId"], str)
                    or not isinstance(item["status"], str)
                    or item["status"] not in {"developed", "none"}):
                raise ContractError("DEVELOPMENT_UNSETTLED", "每张精选照片必须明确已精修或无精修结果", 409)
            photo_ids.append(item["photoId"])
        if len(set(photo_ids)) != len(photo_ids):
            raise ContractError("SETTLEMENT_INVALID", "结算照片不能重复")
        owner = (current_user.get() or {}).get("id")
        if not owner:
            raise ContractError("OWNER_MISSING", "需要登录后才能结算", 401)
        workflow_file = Path(os.getenv("SPARK_H3_WORKFLOW_FILE", "workflows/minimax-h3-i2v-api.json"))
        try:
            workflow = workflow_versions.freeze_workflow(workflow_file, "dynamic_video")
        except (OSError, ValueError) as exc:
            raise ContractError("WORKFLOW_UNAVAILABLE", "动态照片 H3 工作流不可用", 503) from exc
        execution_fields = {"productVersion": PRODUCT_VERSION, "visionModel": vision_model(),
                            "selectionPromptVersion": SELECTOR_PROMPT_VERSION,
                            "h3RunnerVersion": H3_RUNNER_VERSION,
                            "h3WorkflowSnapshot": workflow}
        execution = {**execution_fields, "sha256": _digest(execution_fields)}

        # Shared with set_selected and save_develop, including across processes.
        with self.media.selection_guard(trip_id):
            selection = self._selection(trip_id, batch_id, updated_at, photo_ids)
            attempt_state = self._in_flight(trip_id, batch_id)
            if attempt_state:
                code = "DEVELOPMENT_IN_PROGRESS" if attempt_state == "in_progress" else "DEVELOPMENT_INTERRUPTED"
                raise ContractError(code, "本批精修尝试尚未结算，请检查并恢复", 409)
            existing = self._existing_settlement(trip_id, selection["sha256"], outcomes,
                                                 execution["sha256"])
            if existing:
                for source in existing["sourceSnapshot"]["inputs"]:
                    self._frozen_bytes(existing, source)
                return existing
            inputs = []
            source_bytes = []
            for item in outcomes:
                pid = item["photoId"]
                photo = self.media.get(pid)
                if not photo or photo.get("tripId") != trip_id:
                    raise ContractError("PHOTO_WRONG_TRIP", "照片不存在或不属于本行程", 409)
                developments = photo.get("developments") or []
                if not isinstance(developments, list):
                    raise ContractError("DEVELOPMENT_INVALID", "精修记录结构无效", 409)
                latest = developments[-1] if developments else None
                if latest is not None and not isinstance(latest, dict):
                    raise ContractError("DEVELOPMENT_INVALID", "精修记录结构无效", 409)
                if item["status"] == "none" and latest:
                    raise ContractError("DEVELOPMENT_MISMATCH", "已有精修结果，不能声明无结果", 409)
                if item["status"] == "developed" and not latest:
                    raise ContractError("DEVELOPMENT_MISMATCH", "声明精修完成但没有结果", 409)
                variant = "original" if latest is None else latest.get("variant")
                if (not isinstance(variant, str) or not variant
                        or variant != "original" and
                        (not variant.startswith("develop-") or variant not in photo.get("variants", []))):
                    raise ContractError("DEVELOPMENT_INVALID", "已声明的精修版本无效", 409)
                content = self.media.bytes(pid, variant)
                if not content:
                    code = "DEVELOPMENT_UNREADABLE" if variant != "original" else "ORIGINAL_UNREADABLE"
                    raise ContractError(code, "已声明的照片版本缺失", 409)
                width, height = _image_info(content, variant)
                inputs.append({"photoId": pid, "sourceVariant": variant,
                               "variantCreatedAt": latest.get("createdAt") if latest else photo.get("createdAt"),
                               "sha256": hashlib.sha256(content).hexdigest(), "width": width, "height": height})
                source_bytes.append(content)
            settlement = {"batchId": batch_id, "selectionSha256": selection["sha256"],
                          "photos": outcomes}
            snapshot = {"schemaVersion": 1, "sourceContractVersion": "dynamic-photo-sources@1",
                        "tripId": trip_id, "selection": selection,
                        "settlement": {**settlement, "sha256": _digest(settlement)}, "inputs": inputs}
            identity = _digest({"ownerId": owner, "snapshot": snapshot,
                                "executionContract": execution})
            job_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"travel.dynamic-photo.sources:{identity}"))
            existing = self.get(job_id)
            if existing:
                return existing
            job = {"id": job_id, "kind": "dynamic-photo", "tripId": trip_id, "ownerId": owner,
                   "batchId": batch_id, "status": "prepared", "executionReady": False,
                   "identitySha256": identity, "sourceSnapshot": snapshot,
                   "executionContract": execution,
                   "associations": [{"photoId": source["photoId"],
                                     "sourceVariant": source["sourceVariant"], "dynamicVersionId": None}
                                    for source in inputs],
                   "selection": None, "result": None, "error": None,
                   "createdAt": now(), "updatedAt": now()}
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            destination = self.root / f"{job_id}.json"
            input_dir = self.root / job_id / "inputs"
            input_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            for source, content in zip(inputs, source_bytes):
                frozen = input_dir / f"{source['photoId']}.jpg"
                temporary_input = input_dir / f"{source['photoId']}.{uuid.uuid4().hex}.tmp"
                try:
                    temporary_input.write_bytes(content)
                    os.chmod(temporary_input, 0o600)
                    os.replace(temporary_input, frozen)
                finally:
                    temporary_input.unlink(missing_ok=True)
            temporary = self.root / f"{job_id}.{uuid.uuid4().hex}.tmp"
            try:
                temporary.write_text(json.dumps(job, ensure_ascii=False))
                os.chmod(temporary, 0o600)
                try:
                    os.link(temporary, destination)
                except FileExistsError:
                    return self.get(job_id) or job
            finally:
                temporary.unlink(missing_ok=True)
            return job

    def _frozen_bytes(self, job: dict, source: dict) -> bytes:
        path = self.root / job["id"] / "inputs" / f"{source['photoId']}.jpg"
        try:
            content = path.read_bytes()
        except FileNotFoundError:
            raise ContractError("INPUT_UNREADABLE", "冻结的任务输入副本已丢失", 409) from None
        width, height = _image_info(content, source["sourceVariant"])
        if (hashlib.sha256(content).hexdigest() != source["sha256"]
                or [width, height] != [source["width"], source["height"]]):
            raise ContractError("INPUT_CHANGED", "冻结的任务输入副本已变化", 409)
        return content

    def read_input(self, job: dict, photo_id: str) -> bytes:
        snapshot = job.get("sourceSnapshot")
        if (not isinstance(snapshot, dict) or snapshot.get("schemaVersion") != 1
                or snapshot.get("sourceContractVersion") != "dynamic-photo-sources@1"):
            raise ContractError("SNAPSHOT_INVALID", "动态照片输入快照无效", 409)
        selection = snapshot.get("selection") or {}
        selection_fields = {key: selection.get(key) for key in
                            ("tripId", "batchId", "source", "updatedAt", "photoIds")}
        settlement = snapshot.get("settlement") or {}
        settlement_fields = {key: settlement.get(key) for key in
                             ("batchId", "selectionSha256", "photos")}
        inputs = snapshot.get("inputs") or []
        if (not isinstance(inputs, list) or not isinstance(selection_fields["photoIds"], list)
                or [item.get("photoId") for item in inputs if isinstance(item, dict)] != selection_fields["photoIds"]
                or len(inputs) != len(selection_fields["photoIds"])
                or selection.get("sha256") != _digest(selection_fields)
                or settlement.get("sha256") != _digest(settlement_fields)
                or settlement_fields["selectionSha256"] != selection["sha256"]
                or settlement_fields["batchId"] != selection["batchId"]
                or (job.get("executionContract") or {}).get("sha256") != _digest({
                    key: value for key, value in (job.get("executionContract") or {}).items()
                    if key != "sha256"})
                or job.get("identitySha256") != _digest({"ownerId": job.get("ownerId"),
                    "snapshot": snapshot, "executionContract": job.get("executionContract")})
                or job.get("id") != str(uuid.uuid5(uuid.NAMESPACE_URL,
                    f"travel.dynamic-photo.sources:{job.get('identitySha256')}"))):
            raise ContractError("SNAPSHOT_INVALID", "动态照片输入快照身份或哈希无效", 409)
        source = next((item for item in inputs if item.get("photoId") == photo_id), None)
        if not source:
            raise ContractError("PHOTO_NOT_SELECTED", "照片不在冻结清单中", 409)
        with self.media.selection_guard(snapshot["tripId"]):
            current = self._selection(snapshot["tripId"], selection.get("batchId"),
                                      selection.get("updatedAt"), selection.get("photoIds"))
            if current["sha256"] != selection["sha256"]:
                raise ContractError("SELECTION_CHANGED", "精选清单来源已变化", 409)
            photo = self.media.get(photo_id)
            if not photo or photo.get("tripId") != snapshot["tripId"]:
                raise ContractError("PHOTO_WRONG_TRIP", "照片不属于冻结行程", 409)
            return self._frozen_bytes(job, source)
