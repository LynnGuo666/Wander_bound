"""FastAPI composition root. Feature routers own all HTTP behavior."""
from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI
from .api import core, planning, web
from .trips import routes as trip_routes
from .settings import routes as settings_routes
from .media import MediaStore, JobStore, configured_clients
from .media import routes as media_routes
from .settings import ConfigStore
from .trips import TripStore

def create_app(*, config: ConfigStore | None = None, trips: TripStore | None = None, media: MediaStore | None = None) -> FastAPI:
    config = config or ConfigStore()
    trips = trips or TripStore()
    media = media or MediaStore()
    image_client, video_client = configured_clients()
    jobs = JobStore(media, image_client, video_client)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await jobs.resume()
        yield

    app = FastAPI(title="行驿 Travel Agent", version="2.0.0", lifespan=lifespan)
    app.include_router(core.router_for(config))
    app.include_router(settings_routes.router_for(config))
    app.include_router(planning.router_for(config, trips))
    app.include_router(trip_routes.router_for(trips, media))
    app.include_router(media_routes.router_for(trips, media, jobs, image_client, video_client))
    app.include_router(web.router_for())
    return app

app = create_app()
