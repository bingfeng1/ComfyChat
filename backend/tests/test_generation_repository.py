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
