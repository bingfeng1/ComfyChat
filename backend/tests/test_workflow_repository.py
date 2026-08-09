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
