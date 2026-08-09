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

    model_config = {"from_attributes": True}


class WorkflowListOut(BaseModel):
    items: list[WorkflowOut]


class SyncResultOut(BaseModel):
    synced_at: str
    browse: dict


class ConflictOut(BaseModel):
    filename: str
    existing: WorkflowOut
