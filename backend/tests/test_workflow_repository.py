from app.models.workflow import Base, Workflow
from app.repositories.workflow import WorkflowRepository


def _create_tables(engine):
    Base.metadata.create_all(engine)


def test_upsert_inserts_new(engine, session):
    _create_tables(engine)
    repo = WorkflowRepository(session)
    wf = repo.upsert(
        source="browse", source_key="a.json", name="a",
        original_name="a.json", body='{"nodes":[]}', size_bytes=13,
    )
    assert wf.id
    assert wf.source == "browse"
    assert wf.source_key == "a.json"
    assert wf.name == "a"


def test_upsert_updates_existing(engine, session):
    _create_tables(engine)
    repo = WorkflowRepository(session)
    wf = repo.upsert(source="browse", source_key="a.json", name="a",
                     original_name="a.json", body="{}", size_bytes=2)
    first_id = wf.id
    wf2 = repo.upsert(source="browse", source_key="a.json", name="a",
                      original_name="a.json", body='{"nodes":[1]}', size_bytes=15)
    assert wf2.id == first_id
    assert wf2.size_bytes == 15


def test_list_filters_by_source_and_search(engine, session):
    _create_tables(engine)
    repo = WorkflowRepository(session)
    repo.upsert("browse", "aa.json", "aa", "aa.json", "{}", 2)
    repo.upsert("browse", "bb.json", "bb", "bb.json", "{}", 2)
    repo.upsert("import", "cc.json", "cc", "cc.json", "{}", 2)
    assert len(repo.list(source="browse")) == 2
    assert len(repo.list(q="aa")) == 1
    assert len(repo.list(source="browse", q="bb")) == 1
    assert repo.list(q="zz") == []


def test_get_and_delete(engine, session):
    _create_tables(engine)
    repo = WorkflowRepository(session)
    wf = repo.upsert("import", "x.json", "x", "x.json", "{}", 2)
    assert repo.get(wf.id) is not None
    assert repo.delete(wf.id) is True
    assert repo.get(wf.id) is None
    assert repo.delete(wf.id) is False


from app.models.workflow import WorkflowVersion


def test_archive_version_and_list(engine, session):
    _create_tables(engine)
    repo = WorkflowRepository(session)
    wf = repo.upsert("browse", "a.json", "a", "a.json", "{}", 2)
    v1 = repo.archive_version(wf.id, "a", 2, "{}")
    v2 = repo.archive_version(wf.id, "a", 10, '{"x":1}')
    assert v1.version == 1
    assert v2.version == 2
    versions = repo.list_versions(wf.id)
    assert [v.version for v in versions] == [1, 2]
    assert repo.max_version(wf.id) == 2
    assert repo.has_history(wf.id) is True


def test_get_and_delete_version(engine, session):
    _create_tables(engine)
    repo = WorkflowRepository(session)
    wf = repo.upsert("browse", "b.json", "b", "b.json", "{}", 2)
    repo.archive_version(wf.id, "b", 2, "{}")
    v1 = repo.get_version(wf.id, 1)
    assert v1 is not None
    assert v1.version == 1
    assert repo.delete_version(wf.id, 1) is True
    assert repo.get_version(wf.id, 1) is None
    assert repo.delete_version(wf.id, 1) is False


def test_has_history_false_when_none(engine, session):
    _create_tables(engine)
    repo = WorkflowRepository(session)
    wf = repo.upsert("import", "c.json", "c", "c.json", "{}", 2)
    assert repo.has_history(wf.id) is False
    assert repo.max_version(wf.id) == 0


def test_delete_workflow_removes_its_versions(engine, session):
    _create_tables(engine)
    repo = WorkflowRepository(session)
    wf = repo.upsert("browse", "d.json", "d", "d.json", "{}", 2)
    repo.archive_version(wf.id, "d", 2, "{}")
    assert repo.has_history(wf.id) is True
    assert repo.delete(wf.id) is True
    assert repo.list_versions(wf.id) == []
