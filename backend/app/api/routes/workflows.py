from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_services
from app.integrations.comfyui.client import ComfyUIClient
from app.repositories.generation import WorkflowGenerationConfigRepository
from app.repositories.workflow import WorkflowRepository
from app.schemas.generation import (
    GenerationConfigIn,
    GenerationConfigListOut,
    GenerationConfigOut,
    GenerationConfigSummaryOut,
    GenerationDiscoverOut,
)
from app.schemas.workflow import (
    ConflictOut,
    SyncResultOut,
    WorkflowListOut,
    WorkflowOut,
    WorkflowVersionListOut,
    WorkflowVersionOut,
)
from app.services.generation import discover_fields, workflow_to_api_template
from app.services.lora import main_model_from_template
from app.services.workflow import WorkflowService

router = APIRouter(prefix="/workflows", tags=["workflows"])


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
    out = []
    for w in items:
        item = WorkflowOut.model_validate(w).model_copy(update={"has_history": repo.has_history(w.id)})
        out.append(item)
    return {"items": out}


def _config_repo(session: Session = Depends(get_db_session)) -> WorkflowGenerationConfigRepository:
    return WorkflowGenerationConfigRepository(session)


@router.get("/generation-configs", response_model=GenerationConfigListOut)
def list_generation_configs(
    config_repo: WorkflowGenerationConfigRepository = Depends(_config_repo),
) -> dict:
    items = []
    for cfg, name in config_repo.list_configured():
        items.append(GenerationConfigSummaryOut(
            workflow_id=cfg.workflow_id,
            workflow_name=name,
            fields=[f for f in json.loads(cfg.fields_json)],
            main_model=main_model_from_template(json.loads(cfg.api_template)),
        ))
    return {"items": items}


@router.put("/{workflow_id}/generation-config", response_model=GenerationConfigOut)
def save_generation_config(
    workflow_id: str,
    payload: GenerationConfigIn,
    repo: WorkflowRepository = Depends(_repo),
    config_repo: WorkflowGenerationConfigRepository = Depends(_config_repo),
) -> GenerationConfigOut:
    if repo.get(workflow_id) is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    cfg = config_repo.upsert(workflow_id, payload.api_template, [f.model_dump() for f in payload.fields])
    return GenerationConfigOut.from_model(cfg)


@router.get("/{workflow_id}/generation-config", response_model=GenerationConfigOut)
def get_generation_config(
    workflow_id: str,
    config_repo: WorkflowGenerationConfigRepository = Depends(_config_repo),
) -> GenerationConfigOut:
    cfg = config_repo.get_by_workflow(workflow_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="Generation config not found")
    out = GenerationConfigOut.from_model(cfg)
    out.main_model = main_model_from_template(json.loads(cfg.api_template))
    return out


@router.get("/{workflow_id}/generation-config/discover", response_model=GenerationDiscoverOut)
def discover_generation_config(
    workflow_id: str,
    repo: WorkflowRepository = Depends(_repo),
    services: dict = Depends(get_services),
) -> GenerationDiscoverOut:
    wf = repo.get(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    body_json = json.loads(wf.body)
    node_types = sorted({str(n.get("type", "")) for n in body_json.get("nodes", []) if n.get("type")})
    object_info = None
    if node_types:
        try:
            object_info = services["comfyui"].get_object_info(node_types)
        except Exception:
            object_info = None
    api_template = workflow_to_api_template(body_json, object_info)
    fields = discover_fields(body_json, object_info)
    seen: set[str] = set()
    for f in fields:
        base = f["key"]
        key = base
        n = 1
        while key in seen:
            key = f"{base}_{n}"
            n += 1
        seen.add(key)
        f["key"] = key
    return GenerationDiscoverOut(api_template=api_template, fields=fields)


@router.get("/{workflow_id}", response_model=WorkflowOut)
def get_workflow(
    workflow_id: str,
    repo: WorkflowRepository = Depends(_repo),
) -> WorkflowOut:
    wf = repo.get(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return WorkflowOut.model_validate(wf).model_copy(update={"has_history": repo.has_history(wf.id)})


@router.get("/{workflow_id}/body")
def get_workflow_body(
    workflow_id: str,
    repo: WorkflowRepository = Depends(_repo),
) -> Response:
    wf = repo.get(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return Response(content=wf.body, media_type="application/json")


@router.get("/{workflow_id}/versions", response_model=WorkflowVersionListOut)
def list_versions(
    workflow_id: str,
    repo: WorkflowRepository = Depends(_repo),
) -> dict:
    if repo.get(workflow_id) is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    versions = repo.list_versions(workflow_id)
    return {"items": [WorkflowVersionOut.model_validate(v) for v in versions]}


@router.get("/{workflow_id}/versions/{version}")
def get_version_body(
    workflow_id: str,
    version: int,
    repo: WorkflowRepository = Depends(_repo),
) -> Response:
    if repo.get(workflow_id) is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    v = repo.get_version(workflow_id, version)
    if v is None:
        raise HTTPException(status_code=404, detail="Version not found")
    return Response(content=v.body, media_type="application/json")


@router.delete("/{workflow_id}/versions/{version}", status_code=status.HTTP_204_NO_CONTENT)
def delete_version(
    workflow_id: str,
    version: int,
    repo: WorkflowRepository = Depends(_repo),
) -> Response:
    if repo.get(workflow_id) is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    ok = repo.delete_version(workflow_id, version)
    if not ok:
        raise HTTPException(status_code=404, detail="Version not found")
    return Response(status_code=204)


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

    result_status, wf, collided_key = service.import_workflow(
        filename, body, overwrite=overwrite, new_name=name
    )
    if result_status == "conflict":
        existing = service.repo.get_by_source_key("import", collided_key)
        payload = ConflictOut(
            filename=collided_key,
            existing=WorkflowOut.model_validate(existing),
        ).model_dump()
        return Response(content=json.dumps(payload), status_code=409, media_type="application/json")
    payload = WorkflowOut.model_validate(wf).model_copy(update={"has_history": False}).model_dump()
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
