from __future__ import annotations

from typing import Optional

from fastapi import FastAPI

from app.api.routes import generations, health, lora, workflows
from app.core import database
from app.core.config import Settings
from app.integrations.comfyui.client import ComfyUIClient
from app.models.base import Base


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or Settings()
    database.configure(settings)
    Base.metadata.create_all(database.get_engine())

    app = FastAPI(title="ComfyChat API", version="0.1.0")
    app.state.settings = settings
    app.state.services = {
        "database": database,
        "comfyui": ComfyUIClient(settings),
    }

    app.include_router(health.router)
    app.include_router(workflows.router)
    app.include_router(generations.router)
    app.include_router(lora.router)
    return app


app = create_app()
