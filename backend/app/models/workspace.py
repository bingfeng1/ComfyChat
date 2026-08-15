from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: uuid.uuid4().hex)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_utcnow)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_utcnow, onupdate=_utcnow)


class GenerationWorkspaceLink(Base):
    __tablename__ = "generation_workspace_links"
    __table_args__ = (
        UniqueConstraint("generation_id", "workspace_id", name="uq_gen_workspace_link"),
    )

    generation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("generations.id", ondelete="CASCADE"), primary_key=True
    )
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_utcnow)
