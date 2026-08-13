from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.lora import Lora, LoraModelLink


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class LoraRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_lora(
        self,
        name: str,
        base_family: Optional[str] = None,
        source_url: Optional[str] = None,
        trigger_words: Optional[str] = None,
    ) -> None:
        lora = self.session.get(Lora, name)
        if lora is None:
            lora = Lora(name=name)
            self.session.add(lora)
        if base_family is not None:
            lora.base_family = base_family
        if source_url is not None:
            lora.source_url = source_url
        if trigger_words is not None:
            lora.trigger_words = trigger_words
        lora.updated_at = _utcnow()
        self.session.commit()

    def replace_links(self, lora_name: str, models: list[str], source: str) -> None:
        self.session.execute(
            sa_delete(LoraModelLink).where(
                LoraModelLink.lora_name == lora_name,
                LoraModelLink.source == source,
            )
        )
        for model in models:
            link = self.session.get(LoraModelLink, (lora_name, model))
            if link is None:
                self.session.add(
                    LoraModelLink(lora_name=lora_name, model_name=model, source=source)
                )
            else:
                link.source = source
        self.session.commit()

    def list_all(self) -> list[tuple[Lora, list[str]]]:
        rows = self.session.execute(
            select(Lora, LoraModelLink.model_name)
            .outerjoin(LoraModelLink, LoraModelLink.lora_name == Lora.name)
            .order_by(Lora.deleted_from_comfyui.asc(), Lora.name.asc())
        ).all()
        grouped: dict[str, tuple[Lora, list[str]]] = {}
        for lora, model_name in rows:
            if lora.name not in grouped:
                grouped[lora.name] = (lora, [])
            if model_name is not None:
                grouped[lora.name][1].append(model_name)
        return list(grouped.values())

    def mark_present(self, name: str) -> None:
        lora = self.session.get(Lora, name)
        if lora is None:
            return
        if lora.deleted_from_comfyui:
            lora.deleted_from_comfyui = False
            lora.updated_at = _utcnow()
            self.session.commit()

    def mark_deleted(self, name: str) -> None:
        lora = self.session.get(Lora, name)
        if lora is None:
            return
        if not lora.deleted_from_comfyui:
            lora.deleted_from_comfyui = True
            lora.updated_at = _utcnow()
            self.session.commit()

    def mark_missing(self, known_names: set[str]) -> None:
        stmt = select(Lora).where(Lora.name.notin_(known_names))
        for lora in self.session.scalars(stmt).all():
            if not lora.deleted_from_comfyui:
                lora.deleted_from_comfyui = True
                lora.updated_at = _utcnow()
        self.session.commit()

    def names(self) -> set[str]:
        stmt = select(Lora.name)
        return {n for (n,) in self.session.execute(stmt).all()}

    def update_nsfw(self, name: str, is_nsfw: bool) -> None:
        lora = self.session.get(Lora, name)
        if lora is None:
            return
        lora.is_nsfw = is_nsfw
        lora.updated_at = _utcnow()
        self.session.commit()

    def update_trigger_words(self, name: str, trigger_words: Optional[str]) -> None:
        lora = self.session.get(Lora, name)
        if lora is None:
            return
        lora.trigger_words = (trigger_words or "").strip() or None
        lora.updated_at = _utcnow()
        self.session.commit()

    def get_trigger_words(self, name: str) -> Optional[str]:
        """返回指定 LoRA 的 trigger_words(无记录或为空返回 None)。"""
        lora = self.session.get(Lora, name)
        if lora is None:
            return None
        return lora.trigger_words or None
