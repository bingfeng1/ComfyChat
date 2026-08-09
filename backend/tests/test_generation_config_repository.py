from sqlalchemy.orm import Session

from app.models.workflow import Workflow
from app.repositories.generation import WorkflowGenerationConfigRepository


def _seed_workflow(session: Session, name: str = "z-image") -> str:
    wf = Workflow(
        name=name, source="import", source_key=f"{name}.json",
        original_name=f"{name}.json", size_bytes=1, body="{}",
    )
    session.add(wf)
    session.commit()
    session.refresh(wf)
    return wf.id


def test_upsert_create_and_update(session):
    repo = WorkflowGenerationConfigRepository(session)
    wid = _seed_workflow(session)
    cfg = repo.upsert(wid, {"3": {"inputs": {"seed": 1}}}, [
        {"key": "seed", "label": "种子", "type": "seed", "node_id": "3", "input_name": "seed", "default": 0, "required": True},
    ])
    assert repo.get_by_workflow(wid) is not None
    cfg2 = repo.upsert(wid, {"3": {"inputs": {"seed": 2}}}, [])
    assert cfg2.id == cfg.id


def test_get_missing_returns_none(session):
    repo = WorkflowGenerationConfigRepository(session)
    assert repo.get_by_workflow("nope") is None


def test_list_configured_with_name(session):
    repo = WorkflowGenerationConfigRepository(session)
    wid = _seed_workflow(session, "z-image")
    repo.upsert(wid, "{}", [])
    items = repo.list_configured()
    assert len(items) == 1
    cfg, name = items[0]
    assert name == "z-image"
    assert cfg.workflow_id == wid
