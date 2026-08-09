from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    comfyui_base_url: Optional[str] = Field(default=None)
    comfyui_api_key: Optional[str] = Field(default=None)
    database_url: str = Field(default="sqlite:///./storage/data/comfychat.db")
    storage_root: Path = Field(default=Path("./storage"))
