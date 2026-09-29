"""StepFun template selection and private Qwen sticker endpoints."""
from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from ..agent import step
from ..settings import ConfigStore
from ..trips import TripStore
from .auth import require_media_auth
from .jobs import JobStore
from .store import MediaStore
from .stickers import StickerStore
from .journal_store import JournalConflict, JournalStore

TEMPLATES = Path(__file__).resolve().parents[2] / "workflows/journal-templates.json"


def catalog() -> list[dict]:
    return json.loads(TEMPLATES.read_text())


def photo_context(media: MediaStore, trip_id: str) -> list[dict]:
    """Only selected photos' text tags go to StepFun; image bytes and private EXIF stay local."""
    result = []
    for photo in media.selected(trip_id)["photos"][:12]:
        tags = photo.get("tags") or {}
        result.append({"photoId": photo["id"], "capturedDay": photo.get("capturedDay"),
                       "scene": str(tags.get("scene") or "")[:100],
                       "activity": str(tags.get("activity") or "")[:40],
                       "objects": [str(item)[:40] for item in (tags.get("objects") or [])[:5] if isinstance(item, str)],
                       "locationClue": str(tags.get("location_clue") or "")[:80],
                       "mood": str(tags.get("mood") or "")[:40],
                       "highlight": (tags.get("quality") or {}).get("highlight") is True})
    return result


def router_for(config: ConfigStore, trips: TripStore, media: MediaStore,
               jobs: JobStore, stickers: StickerStore, journal: JournalStore | None = None) -> APIRouter:
    router = APIRouter()
    journal = journal or JournalStore(media.root / "journals", catalog())

    def trip_or_404(trip_id: str) -> dict:
        trip = trips.get(trip_id)
        if not trip:
            raise HTTPException(404, "行程不存在")
        return trip

    def validate_references(trip_id: str, pages: list[dict], *, ai: bool = False) -> None:
        allowed_photos = (set(media.selected(trip_id)["photoIds"]) if ai else
                          {photo["id"] for photo in media.list(trip_id)})
        for page in pages:
            if not isinstance(page, dict) or not isinstance(page.get("items"), list):
                continue
            for item in page["items"]:
                if not isinstance(item, dict):
                    continue
                if item.get("photoId") and item["photoId"] not in allowed_photos:
                    raise HTTPException(400, "页面引用了未授权的旅途照片")
                if item.get("videoId"):
                    video = jobs.get(item["videoId"])
                    if not video or video.get("tripId") != trip_id or video.get("kind") != "memory":
                        raise HTTPException(400, "页面引用了其他行程的旅途短片")
                for name in ("stickerId", "stampId", "assetId"):
                    if item.get(name):
                        job = stickers.get(item[name])
                        if not job or job.get("tripId") != trip_id:
                            raise HTTPException(400, "页面引用了其他行程的 AI 素材")

    @router.post("/api/media/trips/{trip_id}/journal/compose")
    async def compose(trip_id: str, request: Request):
        require_media_auth(request)
        trip = trip_or_404(trip_id)
        key = config.credentials().get("stepfun")
        if not key:
            raise HTTPException(503, "StepFun 尚未配置，仍可手动选择模板")
        templates = catalog()
        plan = trip.get("plan") or {}
        stops = [stop.get("name") for day in plan.get("itinerary") or []
                 for stop in day.get("stops") or [] if isinstance(stop, dict) and stop.get("name")][:12]
        video_count = sum(item["kind"] == "memory" and item["status"] == "succeeded"
                          for item in jobs.list_for_trip(trip_id))
        recognized = photo_context(media, trip_id)
        input_data = {"city": plan.get("destination") or trip.get("title"), "stops": stops,
                      "photoCount": len(recognized), "photos": recognized, "videoCount": video_count,
                      "protectedPages": [index for index, page in enumerate(journal.get(trip)["pages"])
                                         if page["protected"]],
                      "templates": [{"id": item["id"], "description": item["description"],
                                     "slots": [slot["kind"] for slot in item["slots"]]} for item in templates]}
        messages = [
            {"role": "system", "content": "你是旅行手账设计师。根据城市、行程地点以及已精选照片的识别标签，为左右页各挑一个不同的模板，并构思 6 到 8 枚互不重复的贴纸、一枚邮票、一张风景插图和一张明信片图案。贴纸应覆盖照片中真实识别到的食物、建筑、风景或活动，以及行程中确有的地点；没有标签时只依据行程，不得编造照片事实。插画与明信片图案只描述地点、建筑、风景或食物静物，不安排人物、游客或旅伴。还要写简短手账日记和明信片留言，不能把未识别的细节写成真实经历。用户保护的页面不能由你改动，这由服务端执行。只返回 JSON：{\"templates\":[\"左页模板id\",\"右页模板id\"],\"photoOrder\":[\"精选照片id\"],\"stickerMotifs\":[\"具体图案1\",\"具体图案2\",\"具体图案3\",\"具体图案4\",\"具体图案5\",\"具体图案6\"],\"stampMotif\":\"城市邮票图案\",\"postcardMotif\":\"明信片风景图案\",\"illustrationMotif\":\"页面插图图案\",\"diaryText\":\"不超过45字、只写可核实场景的手账短句\",\"postcardText\":\"不超过28字的明信片短句\"}。只使用给定的模板和照片 id。图案不超过 60 字，不含文字、品牌或排版指令。只用照片的文字标签，不请求原图。"},
            {"role": "user", "content": json.dumps(input_data, ensure_ascii=False)},
        ]
        try:
            content = ""
            async for event in step.complete(messages, [], key):
                if event["type"] == "completion":
                    content = event["message"].get("content") or ""
            if len(content) > 5000:
                raise ValueError("StepFun 返回过长")
            choice = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip()))
            ids = [item["id"] for item in templates]
            selected = choice.get("templates")
            motifs = choice.get("stickerMotifs")
            stamp = choice.get("stampMotif")
            photo_order = choice.get("photoOrder", [])
            available_photos = {item["photoId"] for item in recognized}
            if not isinstance(photo_order, list) or len(photo_order) != len(set(photo_order)) or any(
                    not isinstance(item, str) or item not in available_photos for item in photo_order):
                raise ValueError("StepFun 返回了不属于精选清单的照片")
            if (not isinstance(selected, list) or len(selected) != 2 or selected[0] == selected[1]
                    or any(item not in ids for item in selected)
                    or not isinstance(motifs, list) or not 4 <= len(motifs) <= 8
                    or any(not isinstance(item, str) or not 2 <= len(item.strip()) <= 60
                           or any(ord(char) < 32 for char in item) for item in motifs)
                    or len({item.strip() for item in motifs}) < 4
                    or not isinstance(stamp, str) or not 2 <= len(stamp.strip()) <= 60
                    or any(ord(char) < 32 for char in stamp)):
                raise ValueError("StepFun 返回了无效的模板或贴纸主题")
            diary = choice.get("diaryText")
            postcard_text = choice.get("postcardText")
            if (diary is not None and (not isinstance(diary, str) or len(diary) > 120)) or (
                    postcard_text is not None and (not isinstance(postcard_text, str) or len(postcard_text) > 80)):
                raise ValueError("StepFun 返回的手账文字过长")
            return {"templates": selected, "stickerMotifs": list(dict.fromkeys(item.strip() for item in motifs)),
                    "stampMotif": stamp.strip(), "postcardMotif": str(choice.get("postcardMotif") or stamp).strip()[:60],
                    "illustrationMotif": str(choice.get("illustrationMotif") or motifs[0]).strip()[:60],
                    "photoOrder": photo_order or [item["photoId"] for item in recognized],
                    "diaryText": (diary or "")[:45], "postcardText": (postcard_text or "")[:28],
                    "source": step.MODEL}
        except Exception as exc:
            raise HTTPException(502, f"StepFun 手账排版失败：{str(exc)[:100]}") from exc

    @router.get("/api/media/trips/{trip_id}/journal")
    async def get_journal(trip_id: str, request: Request):
        require_media_auth(request)
        return journal.get(trip_or_404(trip_id))

    @router.put("/api/media/trips/{trip_id}/journal/pages/{page_index}")
    async def edit_page(trip_id: str, page_index: int, request: Request, payload: dict):
        require_media_auth(request)
        trip = trip_or_404(trip_id)
        validate_references(trip_id, [payload.get("page")])
        try:
            if type(payload.get("expectedVersion")) is not int:
                raise ValueError("缺少手账版本号")
            return journal.edit_page(trip, page_index, payload.get("page"), payload["expectedVersion"])
        except JournalConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.post("/api/media/trips/{trip_id}/journal/spreads")
    async def append_spread(trip_id: str, request: Request, payload: dict):
        require_media_auth(request)
        trip = trip_or_404(trip_id)
        try:
            if type(payload.get("expectedVersion")) is not int:
                raise ValueError("缺少手账版本号")
            return journal.append_spread(trip, payload["expectedVersion"])
        except JournalConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.post("/api/media/trips/{trip_id}/journal/apply-ai")
    async def apply_ai(trip_id: str, request: Request, payload: dict):
        require_media_auth(request)
        trip = trip_or_404(trip_id)
        validate_references(trip_id, payload.get("pages") if isinstance(payload.get("pages"), list) else [], ai=True)
        try:
            return journal.apply_ai(trip, payload.get("pages"))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.get("/api/media/trips/{trip_id}/stickers")
    async def list_stickers(trip_id: str, request: Request):
        require_media_auth(request)
        trip_or_404(trip_id)
        return {"stickers": stickers.list_for_trip(trip_id)}

    @router.post("/api/media/trips/{trip_id}/stickers")
    async def create_sticker(trip_id: str, request: Request, payload: dict):
        require_media_auth(request)
        trip = trip_or_404(trip_id)
        if set(payload) not in ({"motif"}, {"motif", "kind"}):
            raise HTTPException(400, "只接受 motif 和 kind 字段")
        try:
            city = (trip.get("plan") or {}).get("destination") or trip.get("title") or "旅行"
            item = stickers.submit(trip_id, str(city), payload["motif"], payload.get("kind", "sticker"))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return JSONResponse(item, status_code=202)

    @router.get("/api/media/stickers/{sticker_id}/image")
    async def sticker_image(sticker_id: str, request: Request):
        require_media_auth(request)
        item = stickers.get(sticker_id)
        if not item or not trips.get(item.get("tripId", "")):
            raise HTTPException(404, "贴纸不存在")
        path = stickers.root / f"{sticker_id}.png"
        if item.get("status") != "succeeded" or not path.is_file():
            raise HTTPException(409, "贴纸仍在绘制")
        return FileResponse(path, media_type="image/png", filename=f"{sticker_id}.png")

    return router
