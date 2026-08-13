import json

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


def test_update_poll_miss_count(session):
    repo = _mk_repo(session)
    gen = repo.create(
        workflow_id="wf1",
        workflow_name="z-image",
        parameters={},
        status="running",
        prompt_id="p-1",
    )
    assert gen.poll_miss_count == 0

    repo.update_poll_miss_count(gen.id, 1)
    session.expire_all()
    assert repo.get(gen.id).poll_miss_count == 1

    repo.update_poll_miss_count(gen.id, 0)
    session.expire_all()
    assert repo.get(gen.id).poll_miss_count == 0


def test_update_poll_miss_count_noop_when_missing(session):
    repo = _mk_repo(session)
    repo.update_poll_miss_count("nonexistent", 5)


def _seed_nsfw_lora(session, name, is_nsfw=True):
    from app.models.lora import Lora
    session.add(Lora(name=name, is_nsfw=is_nsfw))
    session.commit()


def test_exclude_nsfw_handles_scalar_lora_name(session):
    """老 generation 的 parameters_json.lora_name 是字符串 → json_each 不能直接用,需 CASE 守卫。"""
    repo = _mk_repo(session)
    _seed_nsfw_lora(session, "nsfw_a.safetensors", is_nsfw=True)
    _seed_nsfw_lora(session, "safe_a.safetensors", is_nsfw=False)
    # scalar lora_name → 整条记录应被排除
    repo.create("wf1", "z", {"lora_name": "nsfw_a.safetensors", "strength_model": 0.8}, "success", "p1")
    repo.create("wf1", "z", {"lora_name": "safe_a.safetensors", "strength_model": 0.8}, "success", "p2")
    items = repo.list(exclude_nsfw=True)
    assert len(items) == 1
    assert json.loads(items[0].parameters_json)["lora_name"] == "safe_a.safetensors"


def test_exclude_nsfw_handles_array_lora_name(session):
    """新 generation 的 parameters_json.lora_name 是 array of dicts → json_each 走 array 路径。"""
    import json as _json
    repo = _mk_repo(session)
    _seed_nsfw_lora(session, "nsfw_b.safetensors", is_nsfw=True)
    _seed_nsfw_lora(session, "safe_b.safetensors", is_nsfw=False)
    # array lora_name + 包含 nsfw → 整条排除
    repo.create("wf1", "z", {
        "lora_name": [
            {"lora_name": "safe_b.safetensors", "strength_model": 1.0},
            {"lora_name": "nsfw_b.safetensors", "strength_model": 0.5},
        ],
    }, "success", "p3")
    # array 全是 safe → 保留
    repo.create("wf1", "z", {
        "lora_name": [
            {"lora_name": "safe_b.safetensors", "strength_model": 1.0},
        ],
    }, "success", "p4")
    items = repo.list(exclude_nsfw=True)
    assert len(items) == 1
    assert _json.loads(items[0].parameters_json)["lora_name"][0]["lora_name"] == "safe_b.safetensors"


def test_exclude_nsfw_handles_missing_lora_name(session):
    """$.lora_name 字段缺失(json_each 会抛 malformed JSON)→ CASE 守卫让 query 不出错。"""
    repo = _mk_repo(session)
    _seed_nsfw_lora(session, "nsfw_c.safetensors", is_nsfw=True)
    # 没有任何 lora 字段
    repo.create("wf1", "z", {"seed": 1, "width": 512, "height": 512}, "success", "p5")
    repo.create("wf1", "z", {"lora_name": "nsfw_c.safetensors", "strength_model": 0.5}, "success", "p6")
    items = repo.list(exclude_nsfw=True)
    # 第二条 (scalar nsfw) 应被排除,第一条 (无 lora) 保留
    assert len(items) == 1
    assert "lora_name" not in json.loads(items[0].parameters_json)


def test_exclude_nsfw_skips_zero_strength(session):
    """strength_model=0 视为未应用,不触发 NSFW 排除。"""
    repo = _mk_repo(session)
    _seed_nsfw_lora(session, "nsfw_d.safetensors", is_nsfw=True)
    repo.create("wf1", "z", {"lora_name": "nsfw_d.safetensors", "strength_model": 0}, "success", "p7")
    items = repo.list(exclude_nsfw=True)
    assert len(items) == 1


def test_exclude_nsfw_array_zero_strength_entry(session):
    """array 中 strength_model=0 的 NSFW entry 不应触发整条排除。"""
    import json as _json
    repo = _mk_repo(session)
    _seed_nsfw_lora(session, "nsfw_e.safetensors", is_nsfw=True)
    _seed_nsfw_lora(session, "safe_e.safetensors", is_nsfw=False)
    repo.create("wf1", "z", {
        "lora_name": [
            {"lora_name": "safe_e.safetensors", "strength_model": 1.0},
            {"lora_name": "nsfw_e.safetensors", "strength_model": 0},
        ],
    }, "success", "p8")
    items = repo.list(exclude_nsfw=True)
    # nsfw_e strength=0 → 不排除 → 记录保留
    assert len(items) == 1


def test_exclude_nsfw_count_matches_list(session):
    """count 和 list 的过滤条件应一致。"""
    repo = _mk_repo(session)
    _seed_nsfw_lora(session, "nsfw_f.safetensors", is_nsfw=True)
    _seed_nsfw_lora(session, "safe_f.safetensors", is_nsfw=False)
    repo.create("wf1", "z", {"lora_name": "nsfw_f.safetensors", "strength_model": 0.5}, "success", "pA")
    repo.create("wf1", "z", {"lora_name": "safe_f.safetensors", "strength_model": 0.5}, "success", "pB")
    repo.create("wf1", "z", {"seed": 1}, "success", "pC")
    listed = repo.list(exclude_nsfw=True)
    counted = repo.count(exclude_nsfw=True)
    assert len(listed) == counted == 2
