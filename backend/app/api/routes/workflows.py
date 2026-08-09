from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_services
from app.integrations.comfyui.client import ComfyUIClient
from app.repositories.workflow import WorkflowRepository
from app.schemas.workflow import ConflictOut, SyncResultOut, WorkflowListOut, WorkflowOut
from app.services.workflow import WorkflowService

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


def _repo(session: Session = Depends(get_db_session)) -> WorkflowRepository:
    return WorkflowRepository(session)


def _service(
    session: Session = Depends(get_db_session),
    services: dict = Depends(get_services),
) -> WorkflowService:
    return WorkflowService(WorkflowRepository(session), services["comfyui"])


@router.get("", response_model=WorkflowListOut)
def list_workflows(
    repo: WorkflowRepository = Depends(_repo),
    source: str | None = Query(default=None),
    q: str | None = Query(default=None),
) -> dict:
    items = repo.list(source=source, q=q)
    return {"items": [WorkflowOut.model_validate(w) for w in items]}


@router.get("/{workflow_id}", response_model=WorkflowOut)
def get_workflow(
    workflow_id: str,
    repo: WorkflowRepository = Depends(_repo),
) -> WorkflowOut:
    wf = repo.get(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return WorkflowOut.model_validate(wf)


@router.get("/{workflow_id}/body")
def get_workflow_body(
    workflow_id: str,
    repo: WorkflowRepository = Depends(_repo),
) -> Response:
    wf = repo.get(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return Response(content=wf.body, media_type="application/json")


@router.get("/{workflow_id}/export")
def export_workflow(
    workflow_id: str,
    repo: WorkflowRepository = Depends(_repo),
) -> Response:
    wf = repo.get(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    filename = wf.name if wf.name.endswith(".json") else f"{wf.name}.json"
    return Response(
        content=wf.body,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workflow(
    workflow_id: str,
    repo: WorkflowRepository = Depends(_repo),
) -> Response:
    ok = repo.delete(workflow_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return Response(status_code=204)


@router.post("/import", status_code=status.HTTP_201_CREATED)
def import_workflow(
    service: WorkflowService = Depends(_service),
    file: UploadFile = File(...),
    overwrite: bool = Query(default=False),
    name: str | None = Query(default=None),
) -> Response:
    filename = file.filename or ""
    if not filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="Only .json files are supported")
    body_bytes = file.file.read()
    try:
        json.loads(body_bytes)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="File is not valid JSON")
    body = body_bytes.decode("utf-8")

    result_status, wf = service.import_workflow(
        filename, body, overwrite=overwrite, new_name=name
    )
    if result_status == "conflict":
        existing = service.repo.get_by_source_key("import", filename)
        payload = ConflictOut(
            filename=filename,
            existing=WorkflowOut.model_validate(existing),
        ).model_dump()
        return Response(content=json.dumps(payload), status_code=409, media_type="application/json")
    payload = WorkflowOut.model_validate(wf).model_dump()
    payload["body"] = wf.body
    if result_status == "replaced":
        return Response(
            content=json.dumps(payload),
            status_code=200,
            media_type="application/json",
        )
    return Response(
        content=json.dumps(payload),
        status_code=201,
        media_type="application/json",
    )


@router.post("/sync", response_model=SyncResultOut)
def sync_workflows(service: WorkflowService = Depends(_service)) -> dict:
    return service.sync()
