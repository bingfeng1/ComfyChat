from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_services, get_settings
from app.core.config import Settings
from app.integrations.comfyui.client import ComfyUIError
from app.repositories.generation import GenerationRepository, WorkflowGenerationConfigRepository
from app.schemas.generation import GenerationCreateIn, GenerationListOut, GenerationOut
from app.services.generation import GenerationService

router = APIRouter(prefix="/generations", tags=["generations"])


def _service(
    session: Session = Depends(get_db_session),
    services: dict = Depends(get_services),
    settings: Settings = Depends(get_settings),
) -> GenerationService:
    return GenerationService(
        GenerationRepository(session),
        WorkflowGenerationConfigRepository(session),
        services["comfyui"],
        settings,
        db=services["database"],
    )


@router.post("", response_model=GenerationOut, status_code=status.HTTP_201_CREATED)
def create_generation(
    payload: GenerationCreateIn,
    background: BackgroundTasks,
    service: GenerationService = Depends(_service),
) -> GenerationOut:
    try:
        gen = service.create(payload.workflow_id, payload.parameters)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ComfyUIError as exc:
        raise HTTPException(status_code=503, detail=f"ComfyUI 不可用: {exc}")
    background.add_task(service.poll_until_done, gen.id)
    return GenerationOut.from_model(gen)


@router.get("", response_model=GenerationListOut)
def list_generations(
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(15, ge=1, le=100),
    service: GenerationService = Depends(_service),
) -> GenerationListOut:
    service.reconcile()
    items = service.gen_repo.list(
        status=status, page=page, page_size=page_size
    )
    total = service.gen_repo.count(status=status)
    return GenerationListOut(
        items=[GenerationOut.from_model(g) for g in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{generation_id}", response_model=GenerationOut)
def get_generation(
    generation_id: str,
    service: GenerationService = Depends(_service),
) -> GenerationOut:
    gen = service.gen_repo.get(generation_id)
    if gen is None:
        raise HTTPException(status_code=404, detail="Generation not found")
    return GenerationOut.from_model(gen)


@router.post("/{generation_id}/cancel", response_model=GenerationOut)
def cancel_generation(
    generation_id: str,
    service: GenerationService = Depends(_service),
) -> GenerationOut:
    try:
        gen = service.cancel(generation_id)
    except ValueError as exc:
        msg = str(exc)
        raise HTTPException(
            status_code=404 if "not found" in msg else 409,
            detail=msg,
        )
    except ComfyUIError as exc:
        raise HTTPException(status_code=503, detail=f"ComfyUI 不可用: {exc}")
    return GenerationOut.from_model(gen)


@router.get("/{generation_id}/images/{filename}")
def get_generation_image(
    generation_id: str,
    filename: str,
    service: GenerationService = Depends(_service),
) -> FileResponse:
    gen = service.gen_repo.get(generation_id)
    if gen is None:
        raise HTTPException(status_code=404, detail="Generation not found")
    out_dir = service.outputs_dir(gen)
    safe = Path(filename).name
    path = (out_dir / safe).resolve()
    if path.parent != out_dir.resolve() or not path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(path)


@router.delete("/{generation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_generation(
    generation_id: str,
    service: GenerationService = Depends(_service),
) -> Response:
    gen = service.gen_repo.get(generation_id)
    if gen is None:
        raise HTTPException(status_code=404, detail="Generation not found")
    out_dir = service.outputs_dir(gen)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    service.gen_repo.delete(generation_id)
    return Response(status_code=204)
