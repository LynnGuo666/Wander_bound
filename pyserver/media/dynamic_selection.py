"""Visual suitability and one-photo selection from frozen dynamic-photo inputs."""
from __future__ import annotations

import asyncio
import base64
import fcntl
import json
import os
import time
import uuid

import httpx

from ..trips import now
from .contracts import ContractError
from .dynamic_sources import DynamicPhotoSources, SELECTOR_PROMPT_VERSION
from .vision import vision_base_url, vision_model, vision_token
from .vlm import compress_for_vlm


PROMPT_VERSION = SELECTOR_PROMPT_VERSION
SYSTEM_PROMPT = """You review one real travel photo for subtle single-image video animation. Return only one JSON object with exactly: photoId (the supplied ID), suitable (boolean), score (integer 0..100), reason (short Chinese explanation grounded in the visible image), motionPrompt (short English description or null). Favor naturally moving water, clouds, mist, steam, foliage and similar small scene motion. Keep the main subject, composition and camera almost still. Be conservative with close faces, group portraits, signs and dense text. Do not invent people, places, events or unseen motion. If unsuitable, set motionPrompt to null. A merely ordinary photo is not automatically suitable. No markdown or extra fields."""


class SelectionError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _valid_text(value: object, maximum: int) -> bool:
    return (isinstance(value, str) and 1 <= len(value.strip()) <= maximum
            and not any(ord(char) < 32 for char in value))


def _safe_identifier(value: object) -> str | None:
    return value if _valid_text(value, 128) else None


def validate_assessment(data: object, photo_id: str) -> dict:
    if not isinstance(data, dict) or set(data) != {"photoId", "suitable", "score", "reason", "motionPrompt"}:
        raise SelectionError("MODEL_SCHEMA_INVALID", "视觉模型输出字段无效")
    if data["photoId"] != photo_id:
        raise SelectionError("MODEL_PHOTO_ID_INVALID", "视觉模型返回未知或重复的照片编号")
    if type(data["suitable"]) is not bool or type(data["score"]) is not int or not 0 <= data["score"] <= 100:
        raise SelectionError("MODEL_SCHEMA_INVALID", "视觉模型适合度或分数无效")
    if not _valid_text(data["reason"], 300):
        raise SelectionError("MODEL_SCHEMA_INVALID", "视觉模型没有提供有效理由")
    prompt = data["motionPrompt"]
    if data["suitable"] and not _valid_text(prompt, 500):
        raise SelectionError("MODEL_SCHEMA_INVALID", "适合的视频候选缺少运动描述")
    if not data["suitable"] and prompt is not None:
        raise SelectionError("MODEL_SCHEMA_INVALID", "不适合的视频候选不得带运动描述")
    return {"photoId": photo_id, "suitable": data["suitable"], "score": data["score"],
            "reason": data["reason"].strip(), "motionPrompt": prompt.strip() if prompt else None}


def analyze_image(image_bytes: bytes, photo_id: str, *, client: httpx.Client | None = None,
                  timeout: float = 180, base_url: str | None = None) -> dict:
    """Use the existing private Spark-compatible vision endpoint; retain no raw response."""
    model = vision_model()
    endpoint = (base_url or vision_base_url()).rstrip("/") + "/chat/completions"
    token = vision_token()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    image = compress_for_vlm(image_bytes)
    payload = {"model": model, "temperature": 0, "max_tokens": 550,
               "response_format": {"type": "json_object"},
               "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": [
                                {"type": "text", "text": f"photoId: {photo_id}. Judge this actual frozen photo."},
                                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," +
                                                                      base64.b64encode(image).decode("ascii")}},
                            ]}]}
    if model == "qwen38-27b":
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    owned = client is None
    if owned:
        client = httpx.Client(timeout=httpx.Timeout(timeout, connect=8))
    try:
        response = client.post(endpoint, headers=headers, json=payload)
        response.raise_for_status()
        body = response.json()
        content = body["choices"][0]["message"]["content"]
        assessment = validate_assessment(json.loads(content), photo_id)
        assessment["_providerReceipt"] = {"modelObserved": _safe_identifier(body.get("model")),
                                          "responseId": _safe_identifier(body.get("id")),
                                          "requestId": _safe_identifier(response.headers.get("x-request-id"))}
        return assessment
    except httpx.TimeoutException as exc:
        raise SelectionError("VISION_TIMEOUT", "视觉模型分析超时") from exc
    except httpx.HTTPStatusError as exc:
        raise SelectionError("VISION_HTTP_ERROR", f"视觉模型 HTTP {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise SelectionError("VISION_UNAVAILABLE", f"视觉模型连接失败：{type(exc).__name__}") from exc
    except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
        raise SelectionError("MODEL_SCHEMA_INVALID", f"视觉模型响应无法解析：{type(exc).__name__}") from exc
    finally:
        if owned:
            client.close()


class DynamicPhotoSelector:
    def __init__(self, sources: DynamicPhotoSources, controller=None):
        self.sources = sources
        self.controller = controller

    def _save(self, job: dict) -> None:
        path = self.sources.root / f"{job['id']}.json"
        temporary = path.with_name(f"{job['id']}.{uuid.uuid4().hex}.tmp")
        job["updatedAt"] = now()
        try:
            temporary.write_text(json.dumps(job, ensure_ascii=False))
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def run(self, job_id: str, analyzer=analyze_image) -> dict:
        """A job lock serializes model calls across processes and restart recovery."""
        job = self.sources.get(job_id)
        if not job:
            raise ContractError("JOB_NOT_FOUND", "动态照片任务不存在", 404)
        lock_path = self.sources.root / f"{job_id}.selection.lock"
        with lock_path.open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                job = self.sources.get(job_id)
                if not job:
                    raise ContractError("JOB_NOT_FOUND", "动态照片任务不存在", 404)
                if job["status"] in {"selected", "skipped", "failed"}:
                    return job
                if job["status"] not in {"prepared", "queued", "analyzing"}:
                    raise ContractError("JOB_STATE_INVALID", "动态照片任务状态不允许选图", 409)
                execution = job.get("executionContract") or {}
                if (execution.get("visionModel") != vision_model()
                        or execution.get("selectionPromptVersion") != PROMPT_VERSION):
                    raise SelectionError("ANALYSIS_VERSION_CHANGED", "分析模型或提示词版本已改变")
                inputs = job["sourceSnapshot"]["inputs"]
                ids = [item["photoId"] for item in inputs]
                if not ids or len(ids) != len(set(ids)):
                    raise SelectionError("SNAPSHOT_INVALID", "冻结候选清单无效")
                assessments = job.get("selectionAssessments") or {}
                if not isinstance(assessments, dict) or set(assessments) - set(ids):
                    raise SelectionError("ASSESSMENTS_INVALID", "持久化的选图分析无效")
                if assessments and (job.get("visionModel") != vision_model()
                                    or job.get("selectionPromptVersion") != PROMPT_VERSION):
                    raise SelectionError("ANALYSIS_VERSION_CHANGED", "分析模型或提示词版本已改变")
                job["status"] = "analyzing"
                job["visionModel"] = vision_model()
                job["selectionPromptVersion"] = PROMPT_VERSION
                self._save(job)
                for source in inputs:
                    pid = source["photoId"]
                    content = self.sources.read_input(job, pid)
                    if pid in assessments:
                        previous = assessments[pid]
                        validate_assessment({key: value for key, value in previous.items()
                                             if key not in {"inputSha256", "requestReceipt"}}, pid)
                        if previous.get("inputSha256") != source["sha256"]:
                            raise SelectionError("ASSESSMENTS_INVALID", "分析结果与冻结输入不匹配")
                        continue
                    started = time.monotonic()
                    raw = analyzer(content, pid)
                    provider = raw.get("_providerReceipt") if isinstance(raw, dict) else None
                    verdict = validate_assessment({key: value for key, value in raw.items()
                                                   if key != "_providerReceipt"} if isinstance(raw, dict)
                                                  else raw, pid)
                    receipt = {"id": str(uuid.uuid4()), "inputSha256": source["sha256"],
                               "configuredModel": job["visionModel"], "promptVersion": PROMPT_VERSION,
                               "elapsedMs": round((time.monotonic() - started) * 1000),
                               "kind": "provider_response" if provider else "local_analyzer",
                               "provider": provider if provider else None}
                    assessments[pid] = {**verdict, "inputSha256": source["sha256"],
                                        "requestReceipt": receipt}
                    job["selectionAssessments"] = assessments
                    self._save(job)
                ranked = sorted((assessments[pid] for pid in ids),
                                key=lambda item: (not item["suitable"], -item["score"],
                                                  ids.index(item["photoId"])))
                suitable = next((item for item in ranked if item["suitable"]), None)
                job["selection"] = {"schemaVersion": 1, "promptVersion": PROMPT_VERSION,
                                    "configuredModel": job["visionModel"],
                                    "observedModels": sorted({item["requestReceipt"]["provider"]["modelObserved"]
                                                              for item in ranked if item.get("requestReceipt")
                                                              and item["requestReceipt"]["provider"]
                                                              and item["requestReceipt"]["provider"]["modelObserved"]}),
                                    "ranking": ranked,
                                    "selectedPhotoId": suitable["photoId"] if suitable else None,
                                    "reason": suitable["reason"] if suitable else "全部候选均不适合动态化",
                                    "motionPrompt": suitable["motionPrompt"] if suitable else None}
                job["status"] = "selected" if suitable else "skipped"
                job["error"] = None
                self._save(job)
                return job
            except (SelectionError, ContractError) as exc:
                job["status"] = "failed"
                job["error"] = {"code": exc.code, "message": str(exc)}
                self._save(job)
                return job
            except Exception as exc:
                job["status"] = "failed"
                job["error"] = {"code": "VISION_UNEXPECTED", "message": type(exc).__name__}
                self._save(job)
                return job
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    async def run_managed(self, job_id: str, analyzer=None) -> dict:
        analyzer = analyze_image if analyzer is None else analyzer
        existing = self.sources.get(job_id)
        if not existing:
            raise ContractError("JOB_NOT_FOUND", "动态照片任务不存在", 404)
        if existing["status"] in {"selected", "skipped", "failed"}:
            return existing
        if self.controller is None or not getattr(self.controller, "enabled", True):
            return await asyncio.to_thread(self.run, job_id, analyzer)
        try:
            async with self.controller.use("chat") as spec:
                managed_analyzer = (lambda image, photo_id: analyze_image(
                    image, photo_id, base_url=spec.url.rstrip("/") + "/v1")) if analyzer is analyze_image else analyzer
                return await asyncio.to_thread(self.run, job_id, managed_analyzer)
        except Exception as exc:
            return await asyncio.to_thread(self._fail_unavailable, job_id, type(exc).__name__)

    def _fail_unavailable(self, job_id: str, error_type: str) -> dict:
        job = self.sources.get(job_id)
        if not job:
            raise ContractError("JOB_NOT_FOUND", "动态照片任务不存在", 404)
        with (self.sources.root / f"{job_id}.selection.lock").open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            job = self.sources.get(job_id)
            if job["status"] not in {"selected", "skipped", "failed"}:
                job["status"] = "failed"
                job["error"] = {"code": "VISION_UNAVAILABLE", "message": error_type}
                self._save(job)
            return job
