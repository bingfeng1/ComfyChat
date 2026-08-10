from __future__ import annotations

from fastapi import APIRouter, Depends
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


def _out(session: Session) -> LoraListOut:
    repo = LoraRepository(session)
    items = []
    for name, models in repo.list_all():
        lora = session.get(Lora, name)
        items.append(LoraOut(
            name=name,
            base_family=lora.base_family if lora else None,
            source_url=lora.source_url if lora else None,
            trigger_words=lora.trigger_words if lora else None,
            models=models,
        ))
    return LoraListOut(items=items)


@router.get("", response_model=LoraListOut)
def list_lora(service: LoraService = Depends(_service)) -> LoraListOut:
    service.sync()
    return _out(service.repo.session)


@router.post("/sync", response_model=LoraListOut)
def sync_lora(service: LoraService = Depends(_service)) -> LoraListOut:
    service.sync()
    return _out(service.repo.session)
