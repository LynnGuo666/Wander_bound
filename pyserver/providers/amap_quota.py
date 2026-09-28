"""高德月配额保护。

个人非商业免费配额（https://lbs.amap.com/upgrade#price）：
POI 搜索 5,000 次/月、基础 LBS（路径规划/地理编码）150,000 次/月。
本项目把实际用量上限压到免费配额的 30%：POI 1,500 次/月、基础 LBS 45,000 次/月。
触顶后调用方收到明确错误（按查询失败降级），而不是继续消耗配额或产生超额计费。

计数器按自然月滚动，持久化在单个 JSON 文件（默认 data/amap-quota.json，
可用 TRAVEL_AMAP_QUOTA_FILE 覆盖），写入为临时文件加原子替换。
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

QUOTA_FRACTION = 0.3
FREE_MONTHLY = {"poi": 5000, "lbs": 150000}
LIMITS = {bucket: int(free * QUOTA_FRACTION) for bucket, free in FREE_MONTHLY.items()}
LABELS = {"poi": "POI 搜索", "lbs": "基础 LBS（路径规划/地理编码）"}
_LOCK = asyncio.Lock()


def _quota_path() -> Path:
    return Path(os.getenv("TRAVEL_AMAP_QUOTA_FILE") or Path("data") / "amap-quota.json")


def _month(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m")


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) and isinstance(data.get("usage"), dict) else {}


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    os.chmod(path, 0o600)


async def consume(bucket: str, cost: int = 1, *, now: datetime | None = None,
                  path: Path | None = None) -> dict:
    """为一次高德调用记账。超出当月上限时抛 RuntimeError，消息里带用量与上限。"""
    if bucket not in LIMITS:
        raise ValueError(f"未知配额桶：{bucket}")
    target = Path(path or _quota_path())
    month = _month(now)
    async with _LOCK:
        data = _read(target)
        usage = data.get("usage") if data.get("month") == month else {}
        used = int(usage.get(bucket) or 0)
        limit = LIMITS[bucket]
        if used + cost > limit:
            raise RuntimeError(f"高德{LABELS[bucket]}本月配额保护已触发：已用 {used}/{limit}"
                               f"（免费配额 {FREE_MONTHLY[bucket]} 次/月的 30%）")
        usage = {**usage, bucket: used + cost}
        _write(target, {"month": month, "usage": usage})
        return {"bucket": bucket, "used": used + cost, "limit": limit, "month": month}


async def snapshot(*, now: datetime | None = None, path: Path | None = None) -> dict:
    """返回当月用量与上限，供健康检查展示；文件缺失或跨月时用量为零。"""
    target = Path(path or _quota_path())
    month = _month(now)
    data = _read(target)
    usage = data.get("usage") if data.get("month") == month else {}
    return {bucket: {"used": int(usage.get(bucket) or 0), "limit": LIMITS[bucket],
                     "freeMonthly": FREE_MONTHLY[bucket]} for bucket in LIMITS}
