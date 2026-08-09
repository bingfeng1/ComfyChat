from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.generation import Generation


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class GenerationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        workflow_id: str,
        workflow_name: str,
        parameters: dict,
        status: str,
        prompt_id: str,
    ) -> Generation:
        gen = Generation(
            workflow_id=workflow_id,
            workflow_name=workflow_name,
            parameters_json=json.dumps(parameters, ensure_ascii=False),
            status=status,
            prompt_id=prompt_id,
        )
        self.session.add(gen)
        self.session.commit()
        self.session.refresh(gen)
        return gen

    def list(self, status: Optional[str] = None) -> Sequence[Generation]:
        stmt = select(Generation)
        if status:
            stmt = stmt.where(Generation.status == status)
        stmt = stmt.order_by(Generation.created_at.desc())
        return self.session.scalars(stmt).all()

    def get(self, generation_id: str) -> Optional[Generation]:
        return self.session.get(Generation, generation_id)

    def list_pending(self) -> Sequence[Generation]:
        stmt = select(Generation).where(Generation.status.in_(["queued", "running"]))
        return self.session.scalars(stmt).all()

    def update_status(self, generation_id: str, status: str) -> None:
        gen = self.get(generation_id)
        if gen is None:
            return
        gen.status = status
        gen.updated_at = _utcnow()
        self.session.commit()

    def mark_failed(self, generation_id: str, error: str) -> None:
        gen = self.get(generation_id)
        if gen is None:
            return
        gen.status = "failed"
        gen.error = error
        gen.updated_at = _utcnow()
        self.session.commit()

    def update_success(self, generation_id: str, outputs: list[str]) -> None:
        gen = self.get(generation_id)
        if gen is None:
            return
        gen.status = "success"
        gen.outputs_json = json.dumps(outputs, ensure_ascii=False)
        gen.error = None
        gen.updated_at = _utcnow()
        self.session.commit()

    def delete(self, generation_id: str) -> bool:
        gen = self.get(generation_id)
        if gen is None:
            return False
        self.session.delete(gen)
        self.session.commit()
        return True
