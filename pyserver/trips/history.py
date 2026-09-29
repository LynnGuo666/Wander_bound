"""Evidence-based past journeys and private conversational corrections."""
from __future__ import annotations

import copy
import json
import os
import uuid
from collections import defaultdict

import httpx
from fastapi import APIRouter, HTTPException, Request

from . import TripStore, now
from ..media import MediaStore
from ..media.auth import require_media_auth
from ..inference import ModelController


def reconstruct(photos: list[dict], previous: dict | None = None) -> dict:
    confirmed = {item["id"]: item for day in (previous or {}).get("days") or []
                 for item in day.get("events") or [] if item.get("source") == "user_confirmed"}
    by_day = defaultdict(list)
    context_count = 0
    unresolved_count = 0
    for photo in photos:
        tags = photo.get("tags") or {}
        scene = str(tags.get("scene") or "")
        event_id = f"photo-{photo['id']}"
        if event_id not in confirmed and any(term in scene for term in ("截图", "屏幕", "界面", "二维码", "支付")):
            context_count += 1
            continue
        if event_id not in confirmed and not photo.get("gps") and not (scene or tags.get("location_clue")):
            unresolved_count += 1
            continue
        by_day[photo.get("capturedDay") or "日期未知"].append(photo)
    days = []
    for date, group in sorted(by_day.items()):
        events = []
        for photo in sorted(group, key=lambda item: item.get("capturedAt") or ""):
            tags = photo.get("tags") or {}
            gps = photo.get("gps")
            clue = tags.get("location_clue")
            scene = tags.get("scene")
            ocr = tags.get("ocr") or []
            label = scene or clue or "照片中的活动待确认"
            event_id = f"photo-{photo['id']}"
            event = {"id": event_id, "label": label, "date": date,
                     "observedAt": photo.get("capturedAt"), "coordinate": gps,
                     "photoIds": [photo["id"]], "evidence": {"gps": bool(gps), "visualClue": clue,
                     "ocr": ocr[:5], "time": bool(photo.get("capturedAt")),
                     "dateConflict": bool(photo.get("capturedAt") and photo.get("capturedDay") and
                                          str(photo["capturedAt"])[:10] != photo["capturedDay"])},
                     "source": "photo_evidence" if gps or scene or clue else "inference_pending",
                     "confidence": "medium" if gps and (scene or clue) else "low",
                     "note": "拍摄时间仅是观测时间，不能当作实际停留起止"}
            events.append({**event, **confirmed.get(event_id, {})})
        days.append({"date": date, "events": events})
    for day in days:
        day["events"] = [event for event in day["events"] if event["date"] == day["date"]]
    moved = [event for event in confirmed.values() if event.get("date") not in by_day or
             event.get("date") != next((photo.get("capturedDay") or "日期未知" for photo in photos
                                        if f"photo-{photo['id']}" == event["id"]), None)]
    for event in moved:
        target = next((day for day in days if day["date"] == event["date"]), None)
        if target is None:
            target = {"date": event["date"], "events": []}
            days.append(target)
        if not any(item["id"] == event["id"] for item in target["events"]):
            target["events"].append(event)
    days.sort(key=lambda day: day["date"])
    return {"days": days, "status": "draft", "updatedAt": now(),
            "contextPhotoCount": context_count, "unresolvedPhotoCount": unresolved_count,
            "notice": "照片间的空白、住宿与交通保持未知；地图连线只表示照片顺序"}


def router_for(trips: TripStore, media: MediaStore, controller: ModelController) -> APIRouter:
    router = APIRouter()

    async def infer_journey(photos: list[dict], home_city: str = "") -> dict | None:
        ordered = sorted(photos, key=lambda photo: photo.get("capturedAt") or "")
        selected = ordered if len(ordered) <= 80 else [ordered[index * (len(ordered) - 1) // 79] for index in range(80)]
        evidence = [{"id": photo["id"], "observedAt": photo.get("capturedAt"),
                     "scene": (photo.get("tags") or {}).get("scene"),
                     "locationClue": (photo.get("tags") or {}).get("location_clue"),
                     "ocr": ((photo.get("tags") or {}).get("ocr") or [])[:3], "gps": photo.get("gps"),
                     "camera": (photo.get("exif") or {}).get("cameraModel")}
                    for photo in selected if photo.get("gps") or photo.get("tags")]
        if not evidence:
            return None
        prompt = ("根据照片观测点推断可能的跨城行程，只返回 JSON："
                  "{\"summary\":\"一句谨慎的中文概述\",\"status\":\"plausible_trip 或 insufficient_evidence\","
                  "\"cities\":[{\"name\":\"城市\",\"role\":\"出发地/途经/到达地/未知\",\"reason\":\"照片证据\"}],"
                  "\"legs\":[{\"date\":\"YYYY-MM-DD\",\"from\":\"城市或站点\",\"to\":\"城市或站点\","
                  "\"mode\":\"已见证据支持的交通方式或未知\",\"evidencePhotoIds\":[\"照片ID\"],\"confidence\":\"low/medium/high\"}],"
                  "\"unknowns\":[\"仍不知道的关键环节\"]}。"
                  "照片时间只是观测时间；截图中的目的地不等于实际到达。"
                  "邮票、明信片、海报、纪念品或截图上的地名只是物品内容，不能据此写成到访景点。"
                  "只有实地照片和相符 GPS 才能写成游览；summary 必须用'照片可能记录'等谨慎措辞，不断言相册持有人本人到访。"
                  "列车显示屏的始发站和终点站是车次全程，不一定是乘客上下车站；优先用本人行程票据与实拍时间核对。"
                  "用户提供的常居住地只是筛选旅行的背景，不代表照片证明从那里出发或返回；"
                  "若孤立异地照片与连续照片的拍摄设备不同，把它列为待核实，不能据此断定到访；"
                  "视觉地点与 GPS 或连续照片冲突时标记待核实；交通方式要由票据、站台实拍或其他直接线索支持。"
                  "若出现多个城市，必须保留多个城市，不能强选一个。"
                  "没有照片证据的航班、酒店、景点、精确出发到达时间不能补造。"
                  f"\n用户确认的常居住地：{home_city or '未提供'}。"
                  f"\n线索：{json.dumps(evidence, ensure_ascii=False)}")
        try:
            async with controller.use("chat") as spec:
                async with httpx.AsyncClient(timeout=180) as client:
                    response = await client.post(spec.url.rstrip("/") + "/v1/chat/completions", json={
                        "model": os.getenv("SPARK_QWEN38_MODEL", "qwen38-27b"),
                        "messages": [{"role": "user", "content": prompt}], "temperature": 0, "max_tokens": 1100,
                        "response_format": {"type": "json_object"}, "stream": False,
                        "chat_template_kwargs": {"enable_thinking": False}})
                response.raise_for_status()
                result = json.loads((response.json().get("choices") or [{}])[0].get("message", {}).get("content") or "{}")
            if not isinstance(result, dict):
                return None
            cities = []
            roles = {"出发地": "出发地", "始发地": "出发地", "起点": "出发地",
                     "途经": "途经", "途经地": "途经", "中转地": "途经",
                     "到达地": "到达地", "目的地": "到达地", "终点": "到达地"}
            for item in (result.get("cities") or [])[:8]:
                if isinstance(item, dict) and isinstance(item.get("name"), str) and item["name"].strip():
                    cities.append({"name": item["name"].strip()[:40], "role": roles.get(item.get("role"), "未知"),
                                   "reason": str(item.get("reason") or "")[:160]})
            valid_ids = {photo["id"] for photo in selected}
            legs = []
            for item in (result.get("legs") or [])[:12]:
                if not isinstance(item, dict):
                    continue
                ids = [value for value in (item.get("evidencePhotoIds") or []) if value in valid_ids]
                if not ids:
                    continue
                legs.append({"date": str(item.get("date") or "")[:10], "from": str(item.get("from") or "未知")[:80],
                             "to": str(item.get("to") or "未知")[:80], "mode": str(item.get("mode") or "未知")[:30],
                             "evidencePhotoIds": ids[:10],
                             "confidence": item.get("confidence") if item.get("confidence") in {"low", "medium", "high"} else "low"})
            for city in cities:
                if city["role"] != "未知":
                    continue
                for leg in legs:
                    if leg["from"].startswith(city["name"]):
                        city["role"] = "出发地"
                        break
                    if leg["to"].startswith(city["name"]):
                        city["role"] = "到达地"
                        break
            return {"summary": str(result.get("summary") or "")[:300],
                    "status": result.get("status") if result.get("status") in {"plausible_trip", "insufficient_evidence"} else "insufficient_evidence",
                    "cities": cities, "legs": legs, "unknowns": [str(value)[:120] for value in (result.get("unknowns") or [])[:8]],
                    "source": "private_ai_inference", "evidencePhotoCount": len(evidence), "totalPhotoCount": len(photos)}
        except (RuntimeError, httpx.HTTPError, ValueError, json.JSONDecodeError):
            return None

    def history_trip(trip_id: str) -> dict:
        trip = trips.get(trip_id)
        if not trip or trip.get("kind") != "history":
            raise HTTPException(404, "历史旅行不存在")
        return trip

    @router.post("/api/history/trips")
    async def create(request: Request, payload: dict):
        require_media_auth(request)
        title = str(payload.get("title") or "过往旅行")[:80]
        home_city = str(payload.get("homeCity") or "").strip()[:40]
        trip = trips.create({"query": title})
        trip.update(kind="history", phase="draft", title=title, homeCity=home_city,
                    history={"days": [], "status": "draft"}, historyVersions=[])
        trips.save(trip)
        return {"id": trip["id"], "title": title}

    @router.get("/api/history/trips/{trip_id}")
    async def read(trip_id: str, request: Request):
        require_media_auth(request)
        trip = history_trip(trip_id)
        return {"id": trip_id, "title": trip["title"], "history": trip.get("history"),
                "photoCount": len(media.list(trip_id)), "versions": len(trip.get("historyVersions") or [])}

    @router.post("/api/history/trips/{trip_id}/reconstruct")
    async def rebuild(trip_id: str, request: Request):
        require_media_auth(request)
        trip = history_trip(trip_id)
        photos = media.list(trip_id)
        if not photos:
            raise HTTPException(400, "请先上传该旅行的照片")
        old = copy.deepcopy(trip.get("history"))
        if old and old.get("days"):
            trip.setdefault("historyVersions", []).append(old)
        trip["history"] = reconstruct(photos, old)
        hypothesis = await infer_journey(photos, str(trip.get("homeCity") or ""))
        trip["history"]["journeyHypothesis"] = hypothesis
        if old and (old.get("possibleCity") or {}).get("source") == "user_confirmed":
            trip["history"]["possibleCity"] = old["possibleCity"]
        else:
            cities = (hypothesis or {}).get("cities") or []
            trip["history"]["possibleCity"] = ({"name": cities[0]["name"], "reason": cities[0]["reason"],
                                                 "source": "private_ai_inference"} if len(cities) == 1 else None)
        trips.save(trip)
        return trip["history"]

    @router.post("/api/history/trips/{trip_id}/chat")
    async def chat(trip_id: str, request: Request, payload: dict):
        require_media_auth(request)
        trip = history_trip(trip_id)
        message = str(payload.get("message") or "").strip()
        if not message or len(message) > 2000:
            raise HTTPException(400, "请输入不超过 2000 字的补充")
        history = trip.get("history") or {}
        events = [item for day in history.get("days") or [] for item in day.get("events") or []]
        if not events:
            raise HTTPException(409, "请先根据照片生成草稿")
        facts = [{key: item.get(key) for key in ("id", "label", "date", "observedAt", "evidence", "source")}
                 for item in events[:100]]
        prompt = ("你是私有旅行记录助手。根据用户补充，返回 JSON 对象："
                  "{\"reply\":\"简短中文回复\",\"changes\":[{\"id\":\"已有事件 ID\",\"label\":\"修改后的地点或活动\","
                  "\"date\":\"YYYY-MM-DD\",\"note\":\"用户补充\"}],"
                  "\"additions\":[{\"date\":\"YYYY-MM-DD\",\"kind\":\"stay/transport/place/note\",\"label\":\"用户明确补充的内容\"}],"
                  "\"city\":\"仅当用户明确确认城市时填写，否则空字符串\"}。"
                  "只修改用户明确说明的字段。不要编造酒店、交通或时间；不确定时 changes 为空并提问。"
                  f"\n事件：{json.dumps(facts, ensure_ascii=False)}\n用户：{message}")
        try:
            async with controller.use("chat") as spec:
                async with httpx.AsyncClient(timeout=300) as client:
                    response = await client.post(spec.url.rstrip("/") + "/v1/chat/completions", json={
                        "model": os.getenv("SPARK_QWEN38_MODEL", "qwen38-27b"),
                        "messages": [{"role": "user", "content": prompt}], "max_tokens": 900,
                        "response_format": {"type": "json_object"}, "stream": False,
                        "chat_template_kwargs": {"enable_thinking": False}})
                response.raise_for_status()
                answer = json.loads((response.json().get("choices") or [{}])[0].get("message", {}).get("content") or "{}")
        except (RuntimeError, httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(503, f"私有对话模型暂不可用：{str(exc)[:120]}") from exc
        changes = answer.get("changes") or []
        if not isinstance(changes, list):
            raise HTTPException(502, "模型修改格式无效")
        before = copy.deepcopy(history)
        by_id = {item["id"]: item for item in events}
        for change in changes[:20]:
            if not isinstance(change, dict) or change.get("id") not in by_id:
                continue
            target = by_id[change["id"]]
            for field in ("label", "date", "note"):
                value = change.get(field)
                if isinstance(value, str) and 0 < len(value) <= 300:
                    if field == "date":
                        try:
                            from datetime import date
                            date.fromisoformat(value)
                        except ValueError:
                            continue
                    target[field] = value
            target["source"] = "user_confirmed"
            target["confidence"] = "confirmed"
        additions = answer.get("additions") or []
        if isinstance(additions, list):
            from datetime import date as date_type
            for addition in additions[:20]:
                if not isinstance(addition, dict) or addition.get("kind") not in {"stay", "transport", "place", "note"}:
                    continue
                label, date_value = addition.get("label"), addition.get("date")
                if not isinstance(label, str) or not 1 <= len(label) <= 300 or not isinstance(date_value, str):
                    continue
                try:
                    date_type.fromisoformat(date_value)
                except ValueError:
                    continue
                day = next((day for day in history["days"] if day["date"] == date_value), None)
                if day is None:
                    day = {"date": date_value, "events": []}
                    history["days"].append(day)
                day["events"].append({"id": str(uuid.uuid4()), "label": label, "date": date_value,
                                      "kind": addition["kind"], "observedAt": None, "photoIds": [],
                                      "source": "user_confirmed", "confidence": "confirmed",
                                      "note": "用户对话补充"})
        city = answer.get("city")
        if isinstance(city, str) and 0 < len(city.strip()) <= 40 and city.strip().removesuffix("市") in message:
            history["possibleCity"] = {"name": city.strip(), "reason": "用户在对话中确认", "source": "user_confirmed"}
        else:
            city = None
        if changes or additions or city:
            trip.setdefault("historyVersions", []).append(before)
            grouped = defaultdict(list)
            for day in history["days"]:
                for item in day.get("events") or []:
                    grouped[item["date"]].append(item)
            history["days"] = [{"date": date, "events": grouped[date]} for date in sorted(grouped)]
        history["updatedAt"] = now()
        trip.setdefault("historyConversation", []).append({"at": now(), "user": message,
                                                             "reply": str(answer.get("reply") or "")[:1000]})
        trips.save(trip)
        return {"reply": str(answer.get("reply") or "请继续补充这段旅行。")[:1000], "history": history}

    @router.post("/api/history/trips/{trip_id}/undo")
    async def undo(trip_id: str, request: Request):
        require_media_auth(request)
        trip = history_trip(trip_id)
        versions = trip.get("historyVersions") or []
        if not versions:
            raise HTTPException(409, "没有可撤销的修订")
        trip["history"] = versions.pop()
        trips.save(trip)
        return trip["history"]

    @router.post("/api/history/trips/{trip_id}/confirm")
    async def confirm(trip_id: str, request: Request):
        require_media_auth(request)
        trip = history_trip(trip_id)
        if not (trip.get("history") or {}).get("days"):
            raise HTTPException(409, "行程草稿为空")
        trip["history"]["status"] = "confirmed"
        trip["phase"] = "ready"
        trips.save(trip)
        return trip["history"]

    return router
