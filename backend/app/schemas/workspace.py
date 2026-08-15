from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.workspace import Workspace


class WorkspaceCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class WorkspaceUpdateIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class WorkspaceOut(BaseModel):
    id: str
    name: str
    created_at: str
    updated_at: str

    @classmethod
    def from_model(cls, ws: Workspace) -> "WorkspaceOut":
        return cls(
            id=ws.id,
            name=ws.name,
            created_at=ws.created_at,
            updated_at=ws.updated_at,
        )


class WorkspaceListOut(BaseModel):
    items: list[WorkspaceOut]
