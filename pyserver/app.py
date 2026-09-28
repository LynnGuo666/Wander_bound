"""FastAPI composition root. Feature routers own all HTTP behavior."""
from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI
from .api import core, planning, web
from .trips import routes as trip_routes
from .settings import routes as settings_routes
from .media import MediaStore, JobStore, ComfyClient, configured_clients
from .media import routes as media_routes
from .media import journal_routes
from .media.stickers import StickerStore
from .inference import ModelController
from .inference import routes as inference_routes
from .settings import ConfigStore
from .trips import TripStore
from .media.storyboards import Storyboards
from .media import storyboard_routes
from pathlib import Path
import os

def create_app(*, config: ConfigStore | None = None, trips: TripStore | None = None, media: MediaStore | None = None) -> FastAPI:
    config = config or ConfigStore()
    trips = trips or TripStore()
    media = media or MediaStore()
    image_client, video_client = configured_clients()
    controller = ModelController()
    jobs = JobStore(media, image_client, video_client, controller)
    boards = Storyboards(jobs, config)
    sticker_workflow = Path(os.environ.get("SPARK_QWEN_STICKER_WORKFLOW_FILE", "workflows/qwen-image-2.1-sticker-api.json"))
    sticker_client = ComfyClient(image_client.base_url, sticker_workflow, "image") if image_client else None
    stickers = StickerStore(media.root / "stickers", sticker_client, controller)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        controller.start()
        await jobs.resume()
        await boards.resume()
        await stickers.resume()
        if controller.primary_chat and not jobs.pending():
            controller.begin_warm("chat")
        yield
        await boards.close()
        await stickers.close()
        await jobs.close()
        await controller.close()

    app = FastAPI(title="行驿 Travel Agent", version="2.0.0", lifespan=lifespan)
    app.include_router(core.router_for(config))
    app.include_router(settings_routes.router_for(config))
    app.include_router(planning.router_for(config, trips))
    app.include_router(trip_routes.router_for(trips, media))
    app.include_router(media_routes.router_for(trips, media, jobs, image_client, video_client, controller))
    app.include_router(journal_routes.router_for(config, trips, media, jobs, stickers))
    app.include_router(inference_routes.router_for(controller, jobs))
    app.include_router(storyboard_routes.router_for(trips, boards))
    app.include_router(web.router_for())
    return app

app = create_app()
