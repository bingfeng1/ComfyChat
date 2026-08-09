from __future__ import annotations

from fastapi import APIRouter, Depends, Request

router = APIRouter()


@router.get("/")
def read_root() -> dict:
    return {"name": "ComfyChat API", "version": "0.1.0"}


@router.get("/health")
def health(request: Request) -> dict:
    services = request.app.state.services
    database_status = "ok" if services["database"].check_database() else "error"
    comfyui_status = services["comfyui"].ping()
    overall = "ok" if database_status == "ok" and comfyui_status in {"ok", "unknown"} else "error"
    return {
        "status": overall,
        "database": database_status,
        "comfyui": comfyui_status,
    }