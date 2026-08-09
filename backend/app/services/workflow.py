from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Union

from app.integrations.comfyui.client import ComfyUIClient, ComfyUIError
from app.models.workflow import Workflow
from app.repositories.workflow import WorkflowRepository

SyncResult = dict
ImportResult = tuple[str, Optional[Workflow]]


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkflowService:
    def __init__(self, repo: WorkflowRepository, comfyui: ComfyUIClient) -> None:
        self.repo = repo
        self.comfyui = comfyui

    def sync(self) -> dict:
        summary = {"added": 0, "updated": 0, "skipped": 0, "error": None}
        try:
            listing = self.comfyui.list_browse()
        except ComfyUIError as exc:
            summary["error"] = str(exc)
            return {"synced_at": _utcnow(), "browse": summary}

        for entry in listing:
            name = entry.get("name", "")
            if not name or not name.endswith(".json"):
                continue
            size = int(entry.get("size", 0) or 0)
            body = self.comfyui.read_userdata_json(name)
            if body is None:
                continue
            existing = self.repo.get_by_source_key("browse", name)
            if existing is not None and existing.size_bytes == size:
                summary["skipped"] += 1
                continue
            display = name[:-5] if name.endswith(".json") else name
            self.repo.upsert(
                source="browse", source_key=name, name=display,
                original_name=name, body=body, size_bytes=size,
            )
            if existing is not None:
                summary["updated"] += 1
            else:
                summary["added"] += 1

        return {"synced_at": _utcnow(), "browse": summary}

    def import_workflow(
        self,
        filename: str,
        body: str,
        overwrite: bool = False,
        new_name: Optional[str] = None,
    ) -> ImportResult:
        display = filename[:-5] if filename.endswith(".json") else filename
        existing = self.repo.get_by_source_key("import", filename)

        if new_name:
            new_filename = new_name if new_name.endswith(".json") else f"{new_name}.json"
            wf = self.repo.upsert(
                source="import", source_key=new_filename, name=new_name,
                original_name=new_filename, body=body, size_bytes=len(body.encode("utf-8")),
            )
            return "created", wf

        if existing is not None:
            if overwrite:
                existing.body = body
                existing.size_bytes = len(body.encode("utf-8"))
                existing.updated_at = _utcnow()
                self.repo.session.commit()
                self.repo.session.refresh(existing)
                return "replaced", existing
            return "conflict", None

        wf = self.repo.upsert(
            source="import", source_key=filename, name=display,
            original_name=filename, body=body, size_bytes=len(body.encode("utf-8")),
        )
        return "created", wf
