import pytest

from app.repositories.generation import GenerationRepository


def _mk_repo(session):
    return GenerationRepository(session)


def test_create_and_get(session):
    repo = _mk_repo(session)
    gen = repo.create(
        workflow_id="wf1", workflow_name="z-image",
        parameters={"positive_prompt": "cat", "seed": 1, "seed_random": False},
        status="queued", prompt_id="p1",
    )
    assert gen.id
    assert repo.get(gen.id) is not None
    assert repo.get("nope") is None


def test_list_ordered_and_filtered(session):
    repo = _mk_repo(session)
    a = repo.create("wf1", "z-image", {"positive_prompt": "a"}, "success", "p1")
    b = repo.create("wf1", "z-image", {"positive_prompt": "b"}, "queued", "p2")
    items = repo.list()
    assert [i.id for i in items] == [b.id, a.id]
    only_q = repo.list(status="queued")
    assert [i.id for i in only_q] == [b.id]


def test_pending_and_status_updates(session):
    repo = _mk_repo(session)
    g = repo.create("wf1", "z-image", {}, "queued", "p1")
    repo.create("wf1", "z-image", {}, "success", "p2")
    assert [i.id for i in repo.list_pending()] == [g.id]

    repo.update_status(g.id, "running")
    assert repo.get(g.id).status == "running"

    repo.mark_failed(g.id, "boom")
    assert repo.get(g.id).status == "failed"
    assert repo.get(g.id).error == "boom"

    repo.update_success(g.id, ["a.png"])
    got = repo.get(g.id)
    assert got.status == "success"
    assert got.outputs_json == '["a.png"]'


def test_delete(session):
    repo = _mk_repo(session)
    g = repo.create("wf1", "z-image", {}, "queued", "p1")
    assert repo.delete(g.id) is True
    assert repo.get(g.id) is None
    assert repo.delete(g.id) is False


def test_list_paginates_correctly(session):
    repo = _mk_repo(session)
    for i in range(20):
        repo.create("wf1", "z-image", {"i": i}, "success", f"p{i}")
    # 排序按 created_at 倒序,后插入的在前
    all_ids = [g.id for g in repo.list(page_size=100)]
    assert len(all_ids) == 20

    page1 = repo.list(page=1, page_size=15)
    page2 = repo.list(page=2, page_size=15)
    page3 = repo.list(page=3, page_size=15)
    assert [g.id for g in page1] == all_ids[:15]
    assert [g.id for g in page2] == all_ids[15:20]
    assert [g.id for g in page3] == []


def test_count_ignores_pagination(session):
    repo = _mk_repo(session)
    for i in range(20):
        repo.create("wf1", "z-image", {"i": i}, "success", f"p{i}")
    assert repo.count() == 20
    # count() takes only `status`; passing page/page_size would raise TypeError,
    # which is the contract — see test_count_signature_rejects_pagination below.


def test_count_with_status_filter(session):
    repo = _mk_repo(session)
    for i in range(7):
        repo.create("wf1", "z-image", {"i": i}, "success", f"p{i}")
    for i in range(4):
        repo.create("wf1", "z-image", {"i": i}, "queued", f"q{i}")
    assert repo.count() == 11
    assert repo.count(status="success") == 7
    assert repo.count(status="queued") == 4
    assert repo.count(status="failed") == 0


def test_count_signature_rejects_pagination(session):
    repo = _mk_repo(session)
    with pytest.raises(TypeError):
        repo.count(page=1, page_size=5)


def test_list_with_status_filter_paginates(session):
    repo = _mk_repo(session)
    for i in range(10):
        repo.create("wf1", "z-image", {"i": i}, "success", f"p{i}")
    for i in range(10):
        repo.create("wf1", "z-image", {"i": i}, "queued", f"q{i}")

    success_all = repo.list(status="success")
    assert len(success_all) == 10
    success_page1 = repo.list(status="success", page=1, page_size=5)
    success_page2 = repo.list(status="success", page=2, page_size=5)
    assert len(success_page1) == 5
    assert len(success_page2) == 5
    assert {g.id for g in success_page1}.isdisjoint({g.id for g in success_page2})


def test_list_empty_page_returns_empty(session):
    repo = _mk_repo(session)
    for i in range(3):
        repo.create("wf1", "z-image", {"i": i}, "success", f"p{i}")
    assert repo.list(page=999, page_size=15) == []
