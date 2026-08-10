from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.generation import Generation, WorkflowGenerationConfig
from app.models.workflow import Workflow


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

    def list(
        self,
        status: Optional[str] = None,
        *,
        page: int = 1,
        page_size: int = 15,
    ) -> Sequence[Generation]:
        if page < 1:
            page = 1
        if page_size < 1:
            page_size = 15
        elif page_size > 100:
            page_size = 100
        stmt = select(Generation)
        if status:
            stmt = stmt.where(Generation.status == status)
        stmt = stmt.order_by(Generation.created_at.desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        return self.session.scalars(stmt).all()

    def count(self, status: Optional[str] = None) -> int:
        stmt = select(func.count()).select_from(Generation)
        if status:
            stmt = stmt.where(Generation.status == status)
        return int(self.session.scalar(stmt) or 0)

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


class WorkflowGenerationConfigRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_workflow(self, workflow_id: str) -> Optional[WorkflowGenerationConfig]:
        stmt = select(WorkflowGenerationConfig).where(
            WorkflowGenerationConfig.workflow_id == workflow_id
        )
        return self.session.scalar(stmt)

    def upsert(
        self,
        workflow_id: str,
        api_template: dict,
        fields: list[dict],
    ) -> WorkflowGenerationConfig:
        cfg = self.get_by_workflow(workflow_id)
        if cfg is None:
            cfg = WorkflowGenerationConfig(
                workflow_id=workflow_id,
                api_template=json.dumps(api_template, ensure_ascii=False),
                fields_json=json.dumps(fields, ensure_ascii=False),
            )
            self.session.add(cfg)
        else:
            cfg.api_template = json.dumps(api_template, ensure_ascii=False)
            cfg.fields_json = json.dumps(fields, ensure_ascii=False)
            cfg.updated_at = _utcnow()
        self.session.commit()
        self.session.refresh(cfg)
        return cfg

    def list_configured(self) -> list[tuple[WorkflowGenerationConfig, str]]:
        stmt = (
            select(WorkflowGenerationConfig, Workflow.name)
            .join(Workflow, Workflow.id == WorkflowGenerationConfig.workflow_id)
            .order_by(Workflow.name.asc())
        )
        return list(self.session.execute(stmt).all())
