from __future__ import annotations

from pydantic import BaseModel, Field


class LoraOut(BaseModel):
    name: str
    base_family: str | None = None
    source_url: str | None = None
    trigger_words: str | None = None
    models: list[str] = Field(default_factory=list)
    deleted_from_comfyui: bool = False
    is_new: bool = False
    is_nsfw: bool = False


class LoraListOut(BaseModel):
    items: list[LoraOut]
