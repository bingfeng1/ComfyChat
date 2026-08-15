from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_services, get_settings
from app.core.config import Settings
from app.integrations.comfyui.client import ComfyUIError
from app.models.generation import Generation
from app.repositories.generation import GenerationRepository, WorkflowGenerationConfigRepository
from app.repositories.workspace import WorkspaceRepository
from app.schemas.generation import (
    GenerationCreateIn,
    GenerationListOut,
    GenerationOut,
    GenerationWorkspacesIn,
)
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


def _ws_repo(session: Session = Depends(get_db_session)) -> WorkspaceRepository:
    return WorkspaceRepository(session)


def _attach_workspace_ids(
    items: list[Generation],
    ws_repo: WorkspaceRepository,
) -> dict[str, list[str]]:
    return ws_repo.bulk_workspace_ids_for_generations([g.id for g in items])


@router.post("", response_model=GenerationOut, status_code=status.HTTP_201_CREATED)
def create_generation(
    payload: GenerationCreateIn,
    background: BackgroundTasks,
    service: GenerationService = Depends(_service),
    ws_repo: WorkspaceRepository = Depends(_ws_repo),
) -> GenerationOut:
    try:
        gen = service.create(
            payload.workflow_id,
            payload.parameters,
            workspace_ids=payload.workspace_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ComfyUIError as exc:
        raise HTTPException(status_code=503, detail=f"ComfyUI 不可用: {exc}")
    background.add_task(service._watch_and_download, gen.id)
    ws_ids = ws_repo.list_workspaces_for_generation(gen.id)
    return GenerationOut.from_model(gen, ws_ids)


@router.get("", response_model=GenerationListOut)
def list_generations(
    status: str | None = None,
    workflow_id: str | None = None,
    workspace_id: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(15, ge=1, le=100),
    exclude_nsfw: bool = False,
    service: GenerationService = Depends(_service),
    ws_repo: WorkspaceRepository = Depends(_ws_repo),
) -> GenerationListOut:
    try:
        service.reconcile()
    except Exception:
        pass
    items = service.gen_repo.list(
        status=status, page=page, page_size=page_size,
        exclude_nsfw=exclude_nsfw, workflow_id=workflow_id,
        workspace_id=workspace_id,
    )
    total = service.gen_repo.count(
        status=status, exclude_nsfw=exclude_nsfw, workflow_id=workflow_id,
        workspace_id=workspace_id,
    )
    ws_map = _attach_workspace_ids(list(items), ws_repo)
    return GenerationListOut(
        items=[
            GenerationOut.from_model(g, ws_map.get(g.id, []))
            for g in items
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{generation_id}", response_model=GenerationOut)
def get_generation(
    generation_id: str,
    service: GenerationService = Depends(_service),
    ws_repo: WorkspaceRepository = Depends(_ws_repo),
) -> GenerationOut:
    gen = service.gen_repo.get(generation_id)
    if gen is None:
        raise HTTPException(status_code=404, detail="Generation not found")
    ws_ids = ws_repo.list_workspaces_for_generation(gen.id)
    return GenerationOut.from_model(gen, ws_ids)


@router.post("/{generation_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
def cancel_generation(
    generation_id: str,
    service: GenerationService = Depends(_service),
) -> Response:
    try:
        service.cancel(generation_id)
    except ValueError as exc:
        msg = str(exc)
        raise HTTPException(
            status_code=404 if "not found" in msg else 409,
            detail=msg,
        )
    except ComfyUIError as exc:
        raise HTTPException(status_code=503, detail=f"ComfyUI 不可用: {exc}")
    return Response(status_code=204)


@router.post("/{generation_id}/workspaces", status_code=status.HTTP_204_NO_CONTENT)
def set_generation_workspaces(
    generation_id: str,
    payload: GenerationWorkspacesIn,
    ws_repo: WorkspaceRepository = Depends(_ws_repo),
) -> Response:
    """全量替换 generation 的 workspace 归属(diff by assign_workspaces)。"""
    # 验证 generation 存在
    gen = ws_repo.session.get(Generation, generation_id)
    if gen is None:
        raise HTTPException(status_code=404, detail="Generation not found")
    valid: list[str] = []
    for ws_id in payload.workspace_ids:
        if ws_repo.get(ws_id) is not None:
            valid.append(ws_id)
    ws_repo.assign_workspaces(generation_id, valid)
    return Response(status_code=204)


@router.delete(
    "/{generation_id}/workspaces/{workspace_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_generation_workspace(
    generation_id: str,
    workspace_id: str,
    ws_repo: WorkspaceRepository = Depends(_ws_repo),
) -> Response:
    """从 generation 上解除单个 workspace(保留 generation 本体)。"""
    gen = ws_repo.session.get(Generation, generation_id)
    if gen is None:
        raise HTTPException(status_code=404, detail="Generation not found")
    ws_repo.remove_workspace_from_generation(generation_id, workspace_id)
    return Response(status_code=204)


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
    service._delete_outputs(gen)
    service.gen_repo.delete(generation_id)
    return Response(status_code=204)
