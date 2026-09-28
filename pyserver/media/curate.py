"""L0 选优编排：给一个行程的照片打质量分、连拍去重、产出排序后的入选清单。

只做可计算指标（锐度/曝光/ISO 噪声/视觉去重），不调 VLM；“相关性/审美/故事”留待 VLM 到位后叠加。
"""
from __future__ import annotations

from .quality import quality, hamming

# 256 位 dHash 下 <=12 视为同组近重复（同一构图连拍/微改），只留最清晰的一张。
DUP_THRESHOLD = 12


def curate_trip(media, trip_id: str, target: int | None = None) -> dict:
    scored = []
    for photo in media.list(trip_id):
        data = media.bytes(photo["id"])
        if not data:
            continue
        iso = (photo.get("exif") or {}).get("iso")
        full = quality(data, iso=iso)
        digest = full["dhashBits"]
        stored = {key: value for key, value in full.items() if key != "dhashBits"}
        stored["dhashHex"] = format(digest, "064x")
        media.set_quality(photo["id"], stored)
        scored.append((photo, stored, digest))

    scored.sort(key=lambda item: (-item[1]["sharpness"], item[1]["blur"], item[0].get("createdAt", "")))
    kept_hashes: list[int] = []
    verdicts: dict[str, str] = {}
    keep: list[str] = []
    for photo, stored, digest in scored:
        pid = photo["id"]
        if stored["reject"]:
            verdicts[pid] = "drop"
        elif any(hamming(digest, seen) <= DUP_THRESHOLD for seen in kept_hashes):
            verdicts[pid] = "dup"
        else:
            kept_hashes.append(digest)
            verdicts[pid] = "keep"
            keep.append(pid)

    if target is not None and len(keep) > target:
        for pid in keep[target:]:
            verdicts[pid] = "overflow"
        keep = keep[:target]

    counts = {"total": len(scored)}
    for label in ("keep", "dup", "drop", "overflow"):
        counts[label] = sum(1 for value in verdicts.values() if value == label)
    return {"tripId": trip_id, "counts": counts, "verdicts": verdicts, "keep": keep}
