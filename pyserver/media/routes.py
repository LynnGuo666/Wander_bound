"""Compose media feature routers."""
from __future__ import annotations

from fastapi import APIRouter
from ..trips import TripStore
from .store import MediaStore
from .jobs import JobStore
from .comfy import ComfyClient
from ..inference.controller import ModelController
from . import photo_routes, job_routes, dynamic_routes
from .dynamic_sources import DynamicPhotoSources

def router_for(trips: TripStore, media: MediaStore, jobs: JobStore, image_client: ComfyClient | None,
               video_client: ComfyClient | None, controller: ModelController) -> APIRouter:
    router = APIRouter()
    router.include_router(photo_routes.router_for(trips, media, image_client, video_client, controller))
    router.include_router(job_routes.router_for(trips, media, jobs))
    router.include_router(dynamic_routes.router_for(trips, jobs.dynamic_sources, jobs))
    return router
