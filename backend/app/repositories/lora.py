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

    def list_all(self) -> list[tuple[str, list[str]]]:
        rows = self.session.execute(
            select(Lora, LoraModelLink.model_name)
            .outerjoin(LoraModelLink, LoraModelLink.lora_name == Lora.name)
            .order_by(Lora.name.asc())
        ).all()
        grouped: dict[str, tuple[str, list[str]]] = {}
        for lora, model_name in rows:
            if lora.name not in grouped:
                grouped[lora.name] = (lora.name, [])
            if model_name is not None:
                grouped[lora.name][1].append(model_name)
        return list(grouped.values())

    def clear_stale(self, known_names: set[str]) -> None:
        stmt = select(Lora.name).where(Lora.name.notin_(known_names))
        stale = [n for (n,) in self.session.execute(stmt).all()]
        if not stale:
            return
        self.session.execute(
            sa_delete(LoraModelLink).where(LoraModelLink.lora_name.in_(stale))
        )
        self.session.execute(sa_delete(Lora).where(Lora.name.in_(stale)))
        self.session.commit()
