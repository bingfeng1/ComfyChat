from __future__ import annotations

from typing import Optional

import httpx

from app.core.config import Settings


class ComfyUIClient:
    def __init__(self, settings: Settings, timeout: float = 2.0) -> None:
        self._base_url: Optional[str] = settings.comfyui_base_url.rstrip("/") if settings.comfyui_base_url else None
        self._api_key: Optional[str] = settings.comfyui_api_key
        self._timeout = timeout

    def ping(self) -> str:
        if not self._base_url:
            return "unknown"
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else None
        try:
            with httpx.Client(timeout=self._timeout, headers=headers) as client:
                response = client.get(f"{self._base_url}/system_stats")
                response.raise_for_status()
                return "ok"
        except Exception:
            return "error"
