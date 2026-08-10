from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_services, get_settings
from app.core.config import Settings
from app.models.lora import Lora
from app.repositories.lora import LoraRepository
from app.repositories.workflow import WorkflowRepository
from app.schemas.lora import LoraListOut, LoraOut
from app.services.lora import LoraService

router = APIRouter(prefix="/lora", tags=["lora"])


def _service(
    session: Session = Depends(get_db_session),
    services: dict = Depends(get_services),
    settings: Settings = Depends(get_settings),
) -> LoraService:
    return LoraService(
        LoraRepository(session),
        WorkflowRepository(session),
        services["comfyui"],
        settings,
    )


def _out(session: Session, is_new: set[str] | None = None) -> LoraListOut:
    repo = LoraRepository(session)
    is_new = is_new or set()
    items = []
    for lora, models in repo.list_all():
        items.append(LoraOut(
            name=lora.name,
            base_family=lora.base_family,
            source_url=lora.source_url,
            trigger_words=lora.trigger_words,
            models=models,
            deleted_from_comfyui=lora.deleted_from_comfyui,
            is_new=lora.name in is_new and not models,
        ))
    return LoraListOut(items=items)


@router.get("", response_model=LoraListOut)
def list_lora(service: LoraService = Depends(_service)) -> LoraListOut:
    result = service.sync()
    if "error" in result:
        raise HTTPException(status_code=503, detail=result["error"])
    return _out(service.repo.session, set(result.get("is_new", [])))


@router.post("/sync", response_model=LoraListOut)
def sync_lora(service: LoraService = Depends(_service)) -> LoraListOut:
    result = service.sync()
    if "error" in result:
        raise HTTPException(status_code=503, detail=result["error"])
    return _out(service.repo.session, set(result.get("is_new", [])))
