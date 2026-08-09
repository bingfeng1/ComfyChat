from __future__ import annotations

from pydantic import BaseModel


class WorkflowOut(BaseModel):
    id: str
    name: str
    source: str
    source_key: str
    original_name: str
    size_bytes: int
    created_at: str
    updated_at: str
    has_history: bool = False

    model_config = {"from_attributes": True}


class WorkflowVersionOut(BaseModel):
    id: str
    workflow_id: str
    version: int
    name: str
    size_bytes: int
    captured_at: str

    model_config = {"from_attributes": True}


class WorkflowVersionListOut(BaseModel):
    items: list[WorkflowVersionOut]


class WorkflowListOut(BaseModel):
    items: list[WorkflowOut]


class SyncResultOut(BaseModel):
    synced_at: str
    browse: dict


class ConflictOut(BaseModel):
    filename: str
    existing: WorkflowOut
