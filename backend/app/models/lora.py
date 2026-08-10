from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class Lora(Base):
    __tablename__ = "loras"

    name: Mapped[str] = mapped_column(String(255), primary_key=True)
    base_family: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    trigger_words: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_utcnow)


class LoraModelLink(Base):
    __tablename__ = "lora_model_links"
    __table_args__ = (
        UniqueConstraint("lora_name", "model_name", name="uq_lora_model_link"),
    )

    lora_name: Mapped[str] = mapped_column(
        String(255), ForeignKey("loras.name", ondelete="CASCADE"), primary_key=True
    )
    model_name: Mapped[str] = mapped_column(String(255), primary_key=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_utcnow)
