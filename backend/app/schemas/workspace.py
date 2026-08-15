from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.models.workspace import Workspace


class WorkspaceCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class WorkspaceUpdateIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class WorkspacePreviewItem(BaseModel):
    generation_id: str
    filename: str
    media_type: str  # "image" | "video" — derived from filename extension server-side


class WorkspaceOut(BaseModel):
    id: str
    name: str
    created_at: str
    updated_at: str
    generation_count: int = 0
    preview: list[WorkspacePreviewItem] = Field(default_factory=list)

    @classmethod
    def from_model(
        cls,
        ws: Workspace,
        *,
        generation_count: int = 0,
        preview: Optional[list[WorkspacePreviewItem]] = None,
    ) -> "WorkspaceOut":
        return cls(
            id=ws.id,
            name=ws.name,
            created_at=ws.created_at,
            updated_at=ws.updated_at,
            generation_count=generation_count,
            preview=list(preview or []),
        )


class WorkspaceListOut(BaseModel):
    items: list[WorkspaceOut]