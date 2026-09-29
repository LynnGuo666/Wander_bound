"""Immutable, JSON-serializable ComfyUI API workflow snapshots."""
from __future__ import annotations

import copy
import hashlib
import io
import json
from pathlib import Path

from PIL import Image, ImageOps

SCHEMA_VERSION = 1
MANIFEST = Path(__file__).resolve().parents[2] / "workflows" / "model-manifest.json"


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def _spec(kind: str) -> dict:
    if kind not in {"image", "video", "dynamic_video"}:
        raise ValueError("未知工作流类型")
    return json.loads(MANIFEST.read_text())[kind]


def freeze_workflow(path: Path, kind: str) -> dict:
    graph = json.loads(path.read_text())
    if not isinstance(graph, dict) or not graph:
        raise ValueError("工作流 API 图无效")
    spec = _spec(kind)
    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "workflow_id": spec["workflow_id"],
        "workflow_version": spec["workflow_version"],
        "workflow_hash": _digest(graph),
        "api_graph": copy.deepcopy(graph),
        "engine": copy.deepcopy(spec["engine"]),
        "custom_nodes": copy.deepcopy(spec.get("custom_nodes", {})),
        "model_nodes": copy.deepcopy(spec["model_nodes"]),
        "parameter_schema": copy.deepcopy(spec["parameter_schema"]),
        "input_policy": copy.deepcopy(spec["input_policy"]),
    }
    snapshot["snapshot_hash"] = _digest(snapshot)
    return snapshot


def validate_snapshot(snapshot: dict, kind: str) -> dict:
    if not isinstance(snapshot, dict) or snapshot.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("工作流快照 schema 不受支持")
    if snapshot.get("kind") != kind or not isinstance(snapshot.get("api_graph"), dict):
        raise ValueError("工作流快照类型不匹配")
    if snapshot.get("workflow_hash") != _digest(snapshot["api_graph"]):
        raise ValueError("工作流图哈希不匹配")
    body = {key: value for key, value in snapshot.items() if key != "snapshot_hash"}
    if snapshot.get("snapshot_hash") != _digest(body):
        raise ValueError("工作流快照哈希不匹配")
    return copy.deepcopy(snapshot)


def validate_parameters(snapshot: dict, parameters: dict | None, seed: int | None) -> tuple[dict, int]:
    if snapshot["schema_version"] != 1:
        raise ValueError("工作流参数 schema 不受支持")
    if parameters is None:
        parameters = {}
    if not isinstance(parameters, dict):
        raise ValueError("parameters 必须是对象")
    schema = snapshot["parameter_schema"]
    if not isinstance(schema, dict) or "seed" not in schema:
        raise ValueError("工作流参数 schema 无效")
    unknown = set(parameters) - (set(schema) - {"seed"})
    if unknown:
        raise ValueError(f"不支持的工作流参数：{', '.join(sorted(map(str, unknown)))}")
    def checked(name: str, value: object, rule: dict):
        if rule.get("type") == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{name} 必须是整数")
            minimum, maximum = rule.get("minimum"), rule.get("maximum")
            if minimum is not None and value < minimum or maximum is not None and value > maximum:
                raise ValueError(f"{name} 超出工作流范围")
            if "step" in rule and (value - (minimum or 0)) % rule["step"]:
                raise ValueError(f"{name} 不符合工作流步长")
        elif rule.get("type") == "string":
            if not isinstance(value, str):
                raise ValueError(f"{name} 必须是字符串")
        else:
            raise ValueError(f"{name} schema 类型不受支持")
        if "enum" in rule and value not in rule["enum"] or "const" in rule and value != rule["const"]:
            raise ValueError(f"{name} 不受工作流支持")
        return value

    result = {}
    for name, rule in schema.items():
        if name == "seed":
            continue
        value = parameters.get(name, rule.get("default", rule.get("const")))
        result[name] = checked(name, value, rule)
    seed_rule = schema["seed"]
    seed = checked("seed", seed_rule.get("default", 0) if seed is None else seed, seed_rule)
    return result, seed


def prepare_image(image: bytes, ratio: str, policy: str, fit_mode: str | None = None) -> bytes:
    if policy == "contain-white-v1":
        if fit_mode is not None:
            raise ValueError("旧工作流不支持 fit_mode")
        if ratio == "source":
            return image
    elif policy == "contain-or-cover-v2":
        if ratio != "16:9" or fit_mode not in {"contain", "cover"}:
            raise ValueError("视频输入画布策略或 fit_mode 不受支持")
    else:
        raise ValueError("工作流输入画布策略不受支持")
    target = (1536, 1024) if ratio == "3:2" else (1024, 576)
    with Image.open(io.BytesIO(image)) as source:
        source = ImageOps.exif_transpose(source).convert("RGB")
        if policy == "contain-or-cover-v2" and fit_mode == "cover":
            canvas = ImageOps.fit(source, target, method=Image.Resampling.LANCZOS,
                                  centering=(0.5, 0.5))
        else:
            fitted = ImageOps.contain(source, target, method=Image.Resampling.LANCZOS)
            canvas = Image.new("RGB", target, "white")
            canvas.paste(fitted, ((target[0] - fitted.width) // 2,
                                  (target[1] - fitted.height) // 2))
        output = io.BytesIO()
        canvas.save(output, format="JPEG", quality=92)
        return output.getvalue()


def prepare_dynamic_image(image: bytes, width: int, height: int) -> bytes:
    """Resize without crop or stretch; small alignment bands preserve every source pixel."""
    if (type(width) is not int or type(height) is not int or width % 32 or height % 32
            or width < 256 or height < 256 or width > 1344 or height > 1344
            or width * height > 768 * 1344):
        raise ValueError("动态照片画布不符合 H3 约束")
    with Image.open(io.BytesIO(image)) as source:
        source = ImageOps.exif_transpose(source).convert("RGB")
        fitted = ImageOps.contain(source, (width, height), method=Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (width, height), (12, 12, 12))
        canvas.paste(fitted, ((width - fitted.width) // 2, (height - fitted.height) // 2))
        output = io.BytesIO()
        canvas.save(output, format="JPEG", quality=94)
        return output.getvalue()
