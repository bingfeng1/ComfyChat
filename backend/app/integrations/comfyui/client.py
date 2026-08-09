from __future__ import annotations

from typing import Optional

import httpx

from app.core.config import Settings


class ComfyUIError(Exception):
    """Raised when a ComfyUI API call fails."""


class ComfyUIClient:
    def __init__(self, settings: Settings, timeout: float = 2.0) -> None:
        self._base_url: Optional[str] = settings.comfyui_base_url.rstrip("/") if settings.comfyui_base_url else None
        self._api_key: Optional[str] = settings.comfyui_api_key
        self._timeout = timeout
        self._userdata_dir = settings.comfyui_userdata_dir

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

    def list_browse(self) -> dict:
        if not self._base_url:
            raise ComfyUIError("ComfyUI not configured")
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else None
        try:
            with httpx.Client(timeout=self._timeout, headers=headers) as client:
                response = client.get(f"{self._base_url}/v2/userdata?path=workflows")
                response.raise_for_status()
                return response.json()
        except Exception as exc:
            raise ComfyUIError(f"Failed to list workflows: {exc}") from exc

    def read_userdata_json(self, filename: str) -> str | None:
        root = self._userdata_dir
        if root is None:
            return None
        workflows_dir = root / "workflows"
        candidate = (workflows_dir / filename).resolve()
        if candidate.parent != workflows_dir.resolve():
            return None
        if not candidate.is_file():
            return None
        try:
            return candidate.read_text(encoding="utf-8")
        except OSError:
            return None

    def _request(self, method: str, path: str, timeout: float | None = None, **kwargs):
        if not self._base_url:
            raise ComfyUIError("ComfyUI not configured")
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else None
        try:
            with httpx.Client(timeout=timeout or self._timeout, headers=headers) as client:
                response = getattr(client, method)(f"{self._base_url}{path}", **kwargs)
                response.raise_for_status()
                return response
        except ComfyUIError:
            raise
        except Exception as exc:
            raise ComfyUIError(f"ComfyUI request failed ({method} {path}): {exc}") from exc

    def submit_prompt(self, prompt: dict) -> str:
        response = self._request("post", "/prompt", json={"prompt": prompt})
        return response.json()["prompt_id"]

    def get_history(self, prompt_id: str) -> dict:
        response = self._request("get", f"/history/{prompt_id}")
        return response.json()

    def get_image(self, filename: str, subfolder: str = "", image_type: str = "output") -> bytes:
        response = self._request(
            "get", "/view", timeout=30.0,
            params={"filename": filename, "subfolder": subfolder, "type": image_type},
        )
        return response.content

    def get_queue(self) -> dict:
        response = self._request("get", "/queue")
        return response.json()
