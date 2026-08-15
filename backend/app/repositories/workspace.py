from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Iterable, Sequence

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.generation import Generation
from app.models.workspace import GenerationWorkspaceLink, Workspace


VIDEO_EXT = (".mp4", ".webm", ".mov", ".m4v", ".avi", ".mkv")


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

    def generation_count(self, workspace_id: str) -> int:
        stmt = select(func.count()).select_from(GenerationWorkspaceLink).where(
            GenerationWorkspaceLink.workspace_id == workspace_id
        )
        return int(self.session.scalar(stmt) or 0)

    def bulk_generation_counts(self, workspace_ids: Iterable[str]) -> dict[str, int]:
        ids = list(workspace_ids)
        if not ids:
            return {}
        stmt = select(
            GenerationWorkspaceLink.workspace_id,
            func.count(GenerationWorkspaceLink.generation_id),
        ).where(
            GenerationWorkspaceLink.workspace_id.in_(ids)
        ).group_by(GenerationWorkspaceLink.workspace_id)
        return {ws_id: int(c) for ws_id, c in self.session.execute(stmt).all()}

    @staticmethod
    def _media_type(filename: str) -> str:
        lower = filename.lower()
        return "video" if lower.endswith(VIDEO_EXT) else "image"

    def preview_for_workspace(self, workspace_id: str, limit: int = 4) -> list[dict]:
        """返回该工作区最近 N 个 generation 的首个 output 文件名。

        顺序: 按 generation.created_at desc 排序。
        每个 output 由 (generation_id, filename, media_type) 描述;空 outputs 跳过。
        """
        if limit <= 0:
            return []
        gen_stmt = (
            select(Generation)
            .join(GenerationWorkspaceLink, GenerationWorkspaceLink.generation_id == Generation.id)
            .where(GenerationWorkspaceLink.workspace_id == workspace_id)
            .order_by(Generation.created_at.desc())
            .limit(limit * 3)  # 取多些再过滤空 outputs
        )
        results: list[dict] = []
        for gen in self.session.scalars(gen_stmt).all():
            try:
                outputs = json.loads(gen.outputs_json or "[]")
            except (TypeError, ValueError):
                outputs = []
            if not outputs:
                continue
            first = outputs[0]
            results.append({
                "generation_id": gen.id,
                "filename": str(first),
                "media_type": self._media_type(str(first)),
            })
            if len(results) >= limit:
                break
        return results
