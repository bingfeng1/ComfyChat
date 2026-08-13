from __future__ import annotations

import json as _json
import time
import uuid
from typing import Optional

import httpx
from websockets.sync.client import connect as _ws_connect

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
        data = response.json()
        prompt_id = data.get("prompt_id")
        if not prompt_id:
            raise ComfyUIError(f"ComfyUI /prompt returned no prompt_id: {data}")
        return prompt_id

    def _ws_base(self) -> str:
        """Convert HTTP base_url to ws:// or wss:// for /ws endpoint."""
        if not self._base_url:
            raise ComfyUIError("ComfyUI not configured")
        if self._base_url.startswith("https://"):
            return "wss://" + self._base_url[len("https://"):]
        if self._base_url.startswith("http://"):
            return "ws://" + self._base_url[len("http://"):]
        return self._base_url

    def wait_for_history(
        self,
        prompt_id: str,
        *,
        timeout: float = 1800.0,
    ) -> dict:
        """Block until ComfyUI signals completion of prompt_id via WebSocket.

        Returns the history entry dict (caller checks status.status_str).
        Raises ComfyUIError on timeout, WS connect failure, or disconnect.

        Strategy:
        1. If /history already has an entry (prompt completed before we
           connected, or this is a reconnect attempt), return it.
        2. Connect to /ws?clientId=<uuid>, listen for events filtered by
           prompt_id. On executing{node:null} or execution_error, fetch
           /history and return.
        """
        if not self._base_url:
            raise ComfyUIError("ComfyUI not configured")

        history = self.get_history(prompt_id)
        entry = history.get(prompt_id)
        if entry is not None:
            return entry

        ws_url = f"{self._ws_base()}/ws?clientId={uuid.uuid4().hex}"
        deadline = time.monotonic() + timeout
        try:
            with _ws_connect(ws_url, open_timeout=min(10.0, max(1.0, timeout))) as ws:
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise ComfyUIError(f"timed out waiting for {prompt_id}")
                    raw = ws.recv(timeout=remaining)
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8", errors="replace")
                    try:
                        event = _json.loads(raw)
                    except _json.JSONDecodeError:
                        continue
                    data = event.get("data") or {}
                    if data.get("prompt_id") != prompt_id:
                        continue
                    etype = event.get("type")
                    if etype == "executing" and data.get("node") is None:
                        history = self.get_history(prompt_id)
                        return history.get(prompt_id) or {}
                    if etype == "execution_error":
                        history = self.get_history(prompt_id)
                        return history.get(prompt_id) or {}
        except ComfyUIError:
            raise
        except TimeoutError as exc:
            raise ComfyUIError(f"timed out waiting for {prompt_id}") from exc
        except Exception as exc:
            raise ComfyUIError(f"WS wait failed for {prompt_id}: {exc}") from exc

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

    def interrupt(self) -> None:
        """POST /interrupt — 中止当前正在运行的 job(无 request body)。"""
        self._request("post", "/interrupt", json=None)

    def delete_queued(self, prompt_id: str) -> None:
        """POST /queue body {"delete":[prompt_id]} — 从队列删除 pending job。"""
        self._request("post", "/queue", json={"delete": [prompt_id]})

    def get_object_info(self, node_types: list[str] | None = None) -> dict:
        """拉取节点 schema。node_types 为 None 时返回全部。

        单个节点拉取路径: /object_info/{node_type}。若 ComfyUI 不可达,抛 ComfyUIError。
        """
        if node_types:
            result: dict = {}
            for nt in node_types:
                try:
                    data = self._request("get", f"/object_info/{nt}").json()
                except ComfyUIError:
                    continue
                if nt in data:
                    result[nt] = data[nt]
            return result
        response = self._request("get", "/object_info")
        return response.json()
