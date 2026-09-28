"""L0 选优编排：给一个行程的照片打质量分、连拍去重、产出排序后的入选清单。

只做可计算指标（锐度/曝光/ISO 噪声/视觉去重），不调 VLM；“相关性/审美/故事”留待 VLM 到位后叠加。
"""
from __future__ import annotations

from .quality import quality, hamming

# 256 位 dHash 下 <=12 视为同组近重复（同一构图连拍/微改），只留最清晰的一张。
DUP_THRESHOLD = 12


def curate_trip(media, trip_id: str, target: int | None = None) -> dict:
    """给一个行程跑 L0 选优：逐张打质量分，连拍去重只留最清晰的一张，按清晰度排序，
    传了 target 就截到目标张数。全程只算可测量指标，不调 VLM；语义筛选和审美留给
    VLM 到位后叠加。返回 counts 概览、每张的 verdict（keep/drop/dup/overflow）和
    入选照片 id 列表。
    """
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


def commit_selection(media, trip_id: str, photo_ids, *, batch_id: str, source: str = "photo-selection") -> dict:
    """把精选出的 photo_ids 提交给下游精修（整份替换，见 docs/photo-curation）。

    底层调 media.set_selected(...)，该契约由共享 store 提供（在下游分支）；本函数只做
    "选优产出 → 下游契约"的翻译，不碰存储实现，两条分支合并后即通，合并前用 stub 测试。
    这是显式的一步，不并进 curate_trip 自动跑：精修要求"优选必须明确提交 id 清单"，
    且整份替换语义下，跑到一半的 curate 不该覆盖下游已有清单。
    photo_ids 应已属于该 trip 且无重复，取值校验交给 set_selected。
    """
    payload = {"batchId": batch_id, "source": source, "photoIds": list(photo_ids)}
    return media.set_selected(trip_id, payload)


def build_reel_assets(media, trip_id: str) -> dict:
    """汇总"被选照片的提取信息"交给③剪辑/回忆编排（见 docs/photo-curation 预留接口）。

    以 selected-photos 清单为"被选"基准（和精修共用同一份，避免用到没选的照片，media.selected
    是下游共享 store 的鸭子接口）。每张被选照片聚合 exif + quality（L0）+ tags（VLM）成素材卡，
    按 capturedDay（GPS）排序对应回忆视频的时间线，highlight=true 的单列方便挑高光镜头。
    VLM 还没部署时照片没有 tags，该字段留空，剪辑可先用 exif/quality。
    """
    selection = media.selected(trip_id) or {}
    cards = []
    for pid in selection.get("photoIds", []):
        photo = media.get(pid)
        if not photo or photo.get("tripId") != trip_id:
            continue
        cards.append({
            "photoId": pid,
            "capturedDay": photo.get("capturedDay"),
            "exif": photo.get("exif") or {},
            "quality": photo.get("quality") or {},
            "tags": photo.get("tags") or {},
        })
    cards.sort(key=lambda card: (card["capturedDay"] or "", card["photoId"]))
    highlights = [card["photoId"] for card in cards
                  if (card["tags"].get("quality") or {}).get("highlight")]
    return {"tripId": trip_id, "batchId": selection.get("batchId"),
            "source": selection.get("source"), "assets": cards, "highlights": highlights}
