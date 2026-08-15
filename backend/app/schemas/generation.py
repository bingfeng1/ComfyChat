from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from app.models.generation import Generation, WorkflowGenerationConfig


class GenerationField(BaseModel):
    key: str
    label: str
    type: str = Field(pattern="^(text|seed|number|select)$")
    node_id: str
    input_name: str
    default: Any = None
    required: bool = False
    min: float | None = None
    max: float | None = None
    step: float | None = None
    options: list[str] | None = None
    is_array: bool = False


class GenerationConfigIn(BaseModel):
    api_template: dict
    fields: list[GenerationField]


class GenerationConfigOut(BaseModel):
    workflow_id: str
    api_template: dict
    fields: list[GenerationField]
    updated_at: str
    main_model: str | None = None

    @classmethod
    def from_model(cls, cfg: WorkflowGenerationConfig) -> "GenerationConfigOut":
        return cls(
            workflow_id=cfg.workflow_id,
            api_template=json.loads(cfg.api_template),
            fields=[GenerationField(**f) for f in json.loads(cfg.fields_json)],
            updated_at=cfg.updated_at,
        )


class GenerationDiscoverOut(BaseModel):
    api_template: dict
    fields: list[GenerationField]


class GenerationConfigSummaryOut(BaseModel):
    workflow_id: str
    workflow_name: str
    fields: list[GenerationField]
    api_template: dict | None = None
    main_model: str | None = None


class GenerationConfigListOut(BaseModel):
    items: list[GenerationConfigSummaryOut]


class GenerationCreateIn(BaseModel):
    workflow_id: str
    parameters: dict
    workspace_ids: list[str] = Field(default_factory=list)


class GenerationOut(BaseModel):
    id: str
    workflow_id: str
    workflow_name: str
    parameters: dict
    status: str
    prompt_id: str
    error: str | None = None
    outputs: list[str] = Field(default_factory=list)
    workspace_ids: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str

    @classmethod
    def from_model(
        cls,
        gen: Generation,
        workspace_ids: list[str] | None = None,
    ) -> "GenerationOut":
        return cls(
            id=gen.id,
            workflow_id=gen.workflow_id,
            workflow_name=gen.workflow_name,
            parameters=json.loads(gen.parameters_json),
            status=gen.status,
            prompt_id=gen.prompt_id,
            error=gen.error,
            outputs=json.loads(gen.outputs_json or "[]"),
            workspace_ids=list(workspace_ids or []),
            created_at=gen.created_at,
            updated_at=gen.updated_at,
        )


class GenerationWorkspacesIn(BaseModel):
    workspace_ids: list[str] = Field(default_factory=list)


class GenerationListOut(BaseModel):
    items: list[GenerationOut]
    total: int
    page: int
    page_size: int
