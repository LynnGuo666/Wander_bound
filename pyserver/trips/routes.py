"""Trip history, detail, and associated photos."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from . import TripStore, public_trip
from ..media import MediaStore

def router_for(trips: TripStore, media: MediaStore) -> APIRouter:
    router = APIRouter()
    @router.get("/api/trips")
    async def list_trips():
        return {"trips": trips.list()}

    @router.get("/api/trips/{trip_id}")
    async def get_trip(trip_id: str):
        trip = trips.get(trip_id)
        if not trip:
            raise HTTPException(404, "行程不存在")
        return {**public_trip(trip, detail=True), "photos": media.list(trip_id)}

    @router.get("/api/trips/{trip_id}/photos/{photo_id}")
    async def trip_photo(trip_id: str, photo_id: str, variant: str = "original"):
        photo = media.get(photo_id)
        if not trips.get(trip_id) or not photo or photo["tripId"] != trip_id:
            raise HTTPException(404, "照片不存在")
        data = media.bytes(photo_id, variant)
        if not data:
            raise HTTPException(404, "照片版本不存在")
        return Response(data, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})

    return router
