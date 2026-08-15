from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Iterable, Sequence

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.workspace import GenerationWorkspaceLink, Workspace


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkspaceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_all(self) -> Sequence[Workspace]:
        stmt = select(Workspace).order_by(Workspace.created_at.asc())
        return list(self.session.scalars(stmt).all())

    def get(self, workspace_id: str) -> Workspace | None:
        return self.session.get(Workspace, workspace_id)

    def get_by_name(self, name: str) -> Workspace | None:
        stmt = select(Workspace).where(Workspace.name == name)
        return self.session.scalar(stmt)

    def create(self, name: str) -> Workspace:
        ws = Workspace(name=name.strip())
        self.session.add(ws)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise ValueError(f"workspace name '{name}' already exists") from exc
        self.session.refresh(ws)
        return ws

    def update(self, workspace_id: str, name: str) -> Workspace | None:
        ws = self.get(workspace_id)
        if ws is None:
            return None
        ws.name = name.strip()
        ws.updated_at = _utcnow()
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise ValueError(f"workspace name '{name}' already exists") from exc
        self.session.refresh(ws)
        return ws

    def delete(self, workspace_id: str) -> bool:
        ws = self.get(workspace_id)
        if ws is None:
            return False
        # 显式解绑后再删 workspace 行,避免依赖 FK CASCADE
        self.session.execute(
            sa_delete(GenerationWorkspaceLink).where(
                GenerationWorkspaceLink.workspace_id == workspace_id
            )
        )
        self.session.delete(ws)
        self.session.commit()
        return True

    def assign_workspaces(self, generation_id: str, workspace_ids: Iterable[str]) -> None:
        """Diff 全量替换 generation 的 workspace 归属。"""
        desired = set(workspace_ids)
        existing_stmt = select(GenerationWorkspaceLink.workspace_id).where(
            GenerationWorkspaceLink.generation_id == generation_id
        )
        existing = set(self.session.scalars(existing_stmt).all())
        to_remove = existing - desired
        to_add = desired - existing
        if to_remove:
            self.session.execute(
                sa_delete(GenerationWorkspaceLink).where(
                    GenerationWorkspaceLink.generation_id == generation_id,
                    GenerationWorkspaceLink.workspace_id.in_(to_remove),
                )
            )
        for ws_id in to_add:
            self.session.add(GenerationWorkspaceLink(generation_id=generation_id, workspace_id=ws_id))
        self.session.commit()

    def remove_workspace_from_generation(self, generation_id: str, workspace_id: str) -> bool:
        stmt = sa_delete(GenerationWorkspaceLink).where(
            GenerationWorkspaceLink.generation_id == generation_id,
            GenerationWorkspaceLink.workspace_id == workspace_id,
        )
        result = self.session.execute(stmt)
        self.session.commit()
        return (result.rowcount or 0) > 0

    def list_workspaces_for_generation(self, generation_id: str) -> list[str]:
        stmt = select(GenerationWorkspaceLink.workspace_id).where(
            GenerationWorkspaceLink.generation_id == generation_id
        )
        return list(self.session.scalars(stmt).all())

    def bulk_workspace_ids_for_generations(self, generation_ids: Iterable[str]) -> dict[str, list[str]]:
        ids = list(generation_ids)
        if not ids:
            return {}
        stmt = select(GenerationWorkspaceLink).where(
            GenerationWorkspaceLink.generation_id.in_(ids)
        )
        grouped: dict[str, list[str]] = defaultdict(list)
        for link in self.session.scalars(stmt).all():
            grouped[link.generation_id].append(link.workspace_id)
        return dict(grouped)

    def generation_ids_in_workspace(self, workspace_id: str) -> list[str]:
        stmt = select(GenerationWorkspaceLink.generation_id).where(
            GenerationWorkspaceLink.workspace_id == workspace_id
        )
        return list(self.session.scalars(stmt).all())
