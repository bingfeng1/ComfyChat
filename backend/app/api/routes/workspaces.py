from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.models.generation import Generation
from app.repositories.workspace import WorkspaceRepository
from app.schemas.workspace import (
    WorkspaceCreateIn,
    WorkspaceListOut,
    WorkspaceOut,
    WorkspaceUpdateIn,
)

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


def _repo(session: Session = Depends(get_db_session)) -> WorkspaceRepository:
    return WorkspaceRepository(session)


@router.get("", response_model=WorkspaceListOut)
def list_workspaces(repo: WorkspaceRepository = Depends(_repo)) -> WorkspaceListOut:
    items = [WorkspaceOut.from_model(w) for w in repo.list_all()]
    return WorkspaceListOut(items=items)


@router.post("", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED)
def create_workspace(
    payload: WorkspaceCreateIn,
    repo: WorkspaceRepository = Depends(_repo),
) -> WorkspaceOut:
    try:
        ws = repo.create(payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return WorkspaceOut.from_model(ws)


@router.patch("/{workspace_id}", response_model=WorkspaceOut)
def update_workspace(
    workspace_id: str,
    payload: WorkspaceUpdateIn,
    repo: WorkspaceRepository = Depends(_repo),
) -> WorkspaceOut:
    try:
        ws = repo.update(workspace_id, payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return WorkspaceOut.from_model(ws)


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workspace(
    workspace_id: str,
    repo: WorkspaceRepository = Depends(_repo),
) -> Response:
    deleted = repo.delete(workspace_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return Response(status_code=204)


@router.get("/{workspace_id}/generation-count")
def get_workspace_generation_count(
    workspace_id: str,
    repo: WorkspaceRepository = Depends(_repo),
) -> dict[str, int]:
    """返回 workspace 当前关联的 generation 数量 — 供管理页删除前提示用。"""
    ws = repo.get(workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    ids = repo.generation_ids_in_workspace(workspace_id)
    return {"count": len(ids)}


@router.post("/{workspace_id}/assign/{generation_id}", status_code=status.HTTP_204_NO_CONTENT)
def assign_single_generation(
    workspace_id: str,
    generation_id: str,
    session: Session = Depends(get_db_session),
    repo: WorkspaceRepository = Depends(_repo),
) -> Response:
    """便捷接口: 把单条 generation 加入 workspace(幂等)。"""
    ws = repo.get(workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    gen = session.get(Generation, generation_id)
    if gen is None:
        raise HTTPException(status_code=404, detail="Generation not found")
    current = set(repo.list_workspaces_for_generation(generation_id))
    if workspace_id not in current:
        repo.assign_workspaces(generation_id, current | {workspace_id})
    return Response(status_code=204)
