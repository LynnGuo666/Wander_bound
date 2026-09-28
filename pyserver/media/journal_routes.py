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

TEMPLATES = Path(__file__).resolve().parents[2] / "workflows/journal-templates.json"


def catalog() -> list[dict]:
    return json.loads(TEMPLATES.read_text())


def router_for(config: ConfigStore, trips: TripStore, media: MediaStore,
               jobs: JobStore, stickers: StickerStore) -> APIRouter:
    router = APIRouter()

    def trip_or_404(trip_id: str) -> dict:
        trip = trips.get(trip_id)
        if not trip:
            raise HTTPException(404, "行程不存在")
        return trip

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
        input_data = {"city": plan.get("destination") or trip.get("title"), "stops": stops,
                      "photoCount": len(media.list(trip_id)), "videoCount": video_count,
                      "templates": [{"id": item["id"], "description": item["description"],
                                     "slots": [slot["kind"] for slot in item["slots"]]} for item in templates]}
        messages = [
            {"role": "system", "content": "你是旅行手账设计师。根据城市和行程地点，为左页和右页各挑一个不同的模板，并构思 4 到 6 枚不同主题的旅途贴纸（食物、建筑、风景、交通等）和一枚微型邮票图案。只返回 JSON 对象，格式为 {\"templates\":[\"左页模板id\",\"右页模板id\"],\"stickerMotifs\":[\"具体图案1\",\"具体图案2\",\"具体图案3\",\"具体图案4\"],\"stampMotif\":\"具体城市邮票图案\"}。只使用给定的模板 id；每个图案不超过 60 字，必须结合城市或行程地点，不写文字、品牌或排版指令。照片内容没有提供，不要编造照片事实。"},
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
            if (not isinstance(selected, list) or len(selected) != 2 or selected[0] == selected[1]
                    or any(item not in ids for item in selected)
                    or not isinstance(motifs, list) or not 4 <= len(motifs) <= 6
                    or any(not isinstance(item, str) or not 2 <= len(item.strip()) <= 60
                           or any(ord(char) < 32 for char in item) for item in motifs)
                    or not isinstance(stamp, str) or not 2 <= len(stamp.strip()) <= 60
                    or any(ord(char) < 32 for char in stamp)):
                raise ValueError("StepFun 返回了无效的模板或贴纸主题")
            return {"templates": selected, "stickerMotifs": [item.strip() for item in motifs],
                    "stampMotif": stamp.strip(), "source": step.MODEL}
        except Exception as exc:
            raise HTTPException(502, f"StepFun 手账排版失败：{str(exc)[:100]}") from exc

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
        if not item:
            raise HTTPException(404, "贴纸不存在")
        path = stickers.root / f"{sticker_id}.png"
        if item.get("status") != "succeeded" or not path.is_file():
            raise HTTPException(409, "贴纸仍在绘制")
        return FileResponse(path, media_type="image/png", filename=f"{sticker_id}.png")

    return router
