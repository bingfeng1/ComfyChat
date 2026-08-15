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
    WorkspacePreviewItem,
    WorkspaceUpdateIn,
)

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


PREVIEW_LIMIT = 4


def _repo(session: Session = Depends(get_db_session)) -> WorkspaceRepository:
    return WorkspaceRepository(session)


def _out_with_preview(ws, repo: WorkspaceRepository) -> WorkspaceOut:
    count = repo.generation_count(ws.id)
    preview = [
        WorkspacePreviewItem(**item)
        for item in repo.preview_for_workspace(ws.id, limit=PREVIEW_LIMIT)
    ]
    return WorkspaceOut.from_model(ws, generation_count=count, preview=preview)


@router.get("", response_model=WorkspaceListOut)
def list_workspaces(repo: WorkspaceRepository = Depends(_repo)) -> WorkspaceListOut:
    items = [_out_with_preview(w, repo) for w in repo.list_all()]
    return WorkspaceListOut(items=items)


@router.get("/{workspace_id}", response_model=WorkspaceOut)
def get_workspace(
    workspace_id: str,
    repo: WorkspaceRepository = Depends(_repo),
) -> WorkspaceOut:
    ws = repo.get(workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return _out_with_preview(ws, repo)


@router.post("", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED)
def create_workspace(
    payload: WorkspaceCreateIn,
    repo: WorkspaceRepository = Depends(_repo),
) -> WorkspaceOut:
    try:
        ws = repo.create(payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _out_with_preview(ws, repo)


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
    return _out_with_preview(ws, repo)


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
    """返回 workspace 当前关联的 generation 数量 — 供管理页删除前提示用。

    注意: 同名信息已包含在 WorkspaceOut.generation_count 中;此端点仅为
    兼容旧前端/外部调用保留。
    """
    ws = repo.get(workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return {"count": repo.generation_count(workspace_id)}


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