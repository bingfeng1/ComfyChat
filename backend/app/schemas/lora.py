from __future__ import annotations

from pydantic import BaseModel, Field


class LoraOut(BaseModel):
    name: str
    base_family: str | None = None
    source_url: str | None = None
    trigger_words: str | None = None
    models: list[str] = Field(default_factory=list)


class LoraListOut(BaseModel):
    items: list[LoraOut]
