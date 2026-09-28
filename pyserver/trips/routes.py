"""Trip history, detail, and associated photos."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from . import TripStore, public_trip
from .notes import NoteStore
from ..media import MediaStore
from ..media.auth import require_media_auth

def router_for(trips: TripStore, media: MediaStore) -> APIRouter:
    router = APIRouter()
    notes = NoteStore(trips.root / "notes")
    @router.get("/api/trips")
    async def list_trips():
        return {"trips": trips.list()}

    @router.get("/api/trips/{trip_id}")
    async def get_trip(trip_id: str, request: Request):
        trip = trips.get(trip_id)
        if not trip:
            raise HTTPException(404, "行程不存在")
        result = public_trip(trip, detail=True)
        if request.headers.get("Authorization"):
            require_media_auth(request)
            result["photos"] = [media.public_photo(photo) for photo in media.list(trip_id)]
        else:
            result["photos"] = []
        return result

    @router.get("/api/trips/{trip_id}/photos/{photo_id}")
    async def trip_photo(trip_id: str, photo_id: str, request: Request, variant: str = "original"):
        require_media_auth(request)
        photo = media.get(photo_id)
        if not trips.get(trip_id) or not photo or photo["tripId"] != trip_id:
            raise HTTPException(404, "照片不存在")
        data = media.bytes(photo_id, variant)
        if not data:
            raise HTTPException(404, "照片版本不存在")
        return Response(data, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})

    @router.get("/api/trips/{trip_id}/note")
    async def get_note(trip_id: str, request: Request):
        require_media_auth(request)
        if not trips.get(trip_id):
            raise HTTPException(404, "行程不存在")
        return notes.get(trip_id)

    @router.put("/api/trips/{trip_id}/note")
    async def put_note(trip_id: str, request: Request, payload: dict):
        require_media_auth(request)
        if not trips.get(trip_id):
            raise HTTPException(404, "行程不存在")
        text, version = payload.get("text"), payload.get("version")
        if not isinstance(text, str) or len(text) > 20000 or type(version) is not int or version < 0:
            raise HTTPException(400, "日记内容或版本无效")
        result = notes.put(trip_id, text, version)
        if result is None:
            raise HTTPException(409, "日记已在另一端更新，请重新读取")
        return result

    return router
