from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.workflow import Workflow


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkflowRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(
        self,
        source: str,
        source_key: str,
        name: str,
        original_name: str,
        body: str,
        size_bytes: int,
    ) -> Workflow:
        existing = self.get_by_source_key(source, source_key)
        if existing is not None:
            existing.body = body
            existing.size_bytes = size_bytes
            existing.original_name = original_name
            existing.updated_at = _utcnow()
            wf = existing
        else:
            wf = Workflow(
                name=name,
                source=source,
                source_key=source_key,
                original_name=original_name,
                body=body,
                size_bytes=size_bytes,
            )
            self.session.add(wf)
        self.session.commit()
        self.session.refresh(wf)
        return wf

    def list(self, source: Optional[str] = None, q: Optional[str] = None) -> Sequence[Workflow]:
        stmt = select(Workflow)
        if source:
            stmt = stmt.where(Workflow.source == source)
        if q:
            like = f"%{q}%"
            stmt = stmt.where(
                (Workflow.name.ilike(like)) | (Workflow.original_name.ilike(like))
            )
        stmt = stmt.order_by(Workflow.updated_at.desc())
        return self.session.scalars(stmt).all()

    def get(self, workflow_id: str) -> Optional[Workflow]:
        return self.session.get(Workflow, workflow_id)

    def get_by_source_key(self, source: str, source_key: str) -> Optional[Workflow]:
        stmt = select(Workflow).where(
            Workflow.source == source, Workflow.source_key == source_key
        )
        return self.session.scalar(stmt)

    def delete(self, workflow_id: str) -> bool:
        wf = self.get(workflow_id)
        if wf is None:
            return False
        self.session.delete(wf)
        self.session.commit()
        return True
