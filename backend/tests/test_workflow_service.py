from pathlib import Path

import pytest

from app.core.config import Settings
from app.integrations.comfyui.client import ComfyUIClient, ComfyUIError
from app.models.base import Base
from app.repositories.workflow import WorkflowRepository
from app.services.workflow import WorkflowService


class FakeBrowseClient:
    def __init__(self, listing, body="{}"):
        self.listing = listing
        self.body = body

    def list_browse(self):
        return self.listing

    def read_userdata_json(self, filename):
        if filename in {e["name"] for e in self.listing}:
            return self.body
        return None


def _repo(engine):
    Base.metadata.create_all(engine)
    from sqlalchemy.orm import sessionmaker
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return WorkflowRepository(Session())


def test_sync_adds_and_counts(engine):
    repo = _repo(engine)
    service = WorkflowService(repo, FakeBrowseClient([
        {"name": "a.json", "path": "workflows/a.json", "type": "file", "size": 2},
        {"name": "b.json", "path": "workflows/b.json", "type": "file", "size": 2},
    ]))
    result = service.sync()
    assert result["browse"]["added"] == 2
    assert result["browse"]["skipped"] == 0
    assert len(repo.list()) == 2


def test_sync_skips_unchanged(engine):
    repo = _repo(engine)
    service = WorkflowService(repo, FakeBrowseClient([{"name": "a.json", "path": "workflows/a.json", "type": "file", "size": 2}]))
    service.sync()
    service2 = WorkflowService(repo, FakeBrowseClient([{"name": "a.json", "path": "workflows/a.json", "type": "file", "size": 2}]))
    result = service2.sync()
    assert result["browse"]["skipped"] == 1
    assert result["browse"]["added"] == 0


def test_sync_updates_when_size_changes(engine):
    repo = _repo(engine)
    service = WorkflowService(repo, FakeBrowseClient([{"name": "a.json", "path": "workflows/a.json", "type": "file", "size": 2}], body="{}"))
    service.sync()
    service2 = WorkflowService(repo, FakeBrowseClient([{"name": "a.json", "path": "workflows/a.json", "type": "file", "size": 99}], body='{"n":2}'))
    result = service2.sync()
    assert result["browse"]["updated"] == 1
    row = repo.get_by_source_key("browse", "a.json")
    assert row.size_bytes == 99


def test_sync_does_not_delete_stale(engine):
    repo = _repo(engine)
    service = WorkflowService(repo, FakeBrowseClient([{"name": "a.json", "path": "workflows/a.json", "type": "file", "size": 2}]))
    service.sync()
    service2 = WorkflowService(repo, FakeBrowseClient([]))
    service2.sync()
    assert len(repo.list()) == 1  # a.json 残留，不删


def test_sync_returns_error_on_comfy_failure(engine):
    repo = _repo(engine)

    class BoomClient:
        def list_browse(self):
            raise ComfyUIError("boom")

    service = WorkflowService(repo, BoomClient())
    result = service.sync()
    assert result["browse"]["error"] is not None
    assert result["browse"]["added"] == 0


def test_import_creates(engine):
    repo = _repo(engine)
    service = WorkflowService(repo, object())
    status, wf = service.import_workflow("a.json", '{"x":1}')
    assert status == "created"
    assert wf.source_key == "a.json"


def test_import_conflict(engine):
    repo = _repo(engine)
    service = WorkflowService(repo, object())
    service.import_workflow("a.json", '{"x":1}')
    status, wf = service.import_workflow("a.json", '{"x":2}')
    assert status == "conflict"
    assert wf is None


def test_import_overwrite(engine):
    repo = _repo(engine)
    service = WorkflowService(repo, object())
    service.import_workflow("a.json", '{"x":1}')
    status, wf = service.import_workflow("a.json", '{"x":2}', overwrite=True)
    assert status == "replaced"
    assert wf.body == '{"x":2}'
    assert wf.id is not None


def test_import_rename(engine):
    repo = _repo(engine)
    service = WorkflowService(repo, object())
    service.import_workflow("a.json", '{"x":1}')
    status, wf = service.import_workflow("a.json", '{"x":2}', new_name="b")
    assert status == "created"
    assert wf.source_key == "b.json"
    assert wf.name == "b"
    assert len(repo.list()) == 2
