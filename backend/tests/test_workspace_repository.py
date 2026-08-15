import pytest

from app.repositories.workspace import WorkspaceRepository


def _repo(session):
    return WorkspaceRepository(session)


def test_create_and_list(session):
    repo = _repo(session)
    a = repo.create("alpha")
    b = repo.create("beta")
    items = repo.list_all()
    assert [w.name for w in items] == ["alpha", "beta"]
    assert items[0].id == a.id
    assert items[1].id == b.id


def test_create_trims_whitespace(session):
    repo = _repo(session)
    ws = repo.create("  spaced  ")
    assert ws.name == "spaced"


def test_create_duplicate_raises(session):
    repo = _repo(session)
    repo.create("dup")
    with pytest.raises(ValueError, match="already exists"):
        repo.create("dup")
    with pytest.raises(ValueError, match="already exists"):
        repo.create("  dup  ")  # trim 后仍然冲突


def test_get_by_name_and_id(session):
    repo = _repo(session)
    ws = repo.create("lookup")
    assert repo.get_by_name("lookup").id == ws.id
    assert repo.get(ws.id).name == "lookup"
    assert repo.get("nonexistent") is None
    assert repo.get_by_name("nope") is None


def test_update_rename(session):
    repo = _repo(session)
    ws = repo.create("old")
    updated = repo.update(ws.id, "new")
    assert updated.name == "new"
    # 旧名应不再查得
    assert repo.get_by_name("old") is None
    assert repo.get_by_name("new").id == ws.id


def test_update_duplicate_raises_and_keeps_original(session):
    repo = _repo(session)
    repo.create("a")
    b = repo.create("b")
    with pytest.raises(ValueError, match="already exists"):
        repo.update(b.id, "a")
    # b 名字未变
    assert repo.get(b.id).name == "b"


def test_update_missing_returns_none(session):
    repo = _repo(session)
    assert repo.update("nonexistent", "x") is None


def test_delete_unbinds_links(session):
    repo = _repo(session)
    ws = repo.create("w1")
    gen_id = "fake-gen-1"
    repo.assign_workspaces(gen_id, [ws.id])
    assert repo.list_workspaces_for_generation(gen_id) == [ws.id]

    assert repo.delete(ws.id) is True
    assert repo.get(ws.id) is None
    # generation 上的 link 解除,但 generation_id 本体不在 workspace repo 管辖范围,
    # 我们只断言 link 行被清空
    assert repo.list_workspaces_for_generation(gen_id) == []
    # 不存在的 workspace 删除返回 False
    assert repo.delete(ws.id) is False


def test_assign_workspaces_full_replace(session):
    repo = _repo(session)
    w1 = repo.create("w1")
    w2 = repo.create("w2")
    w3 = repo.create("w3")
    gen = "gen-x"

    repo.assign_workspaces(gen, [w1.id, w2.id])
    assert sorted(repo.list_workspaces_for_generation(gen)) == sorted([w1.id, w2.id])

    # 替换为 [w2, w3]: 移除 w1, 添加 w3
    repo.assign_workspaces(gen, [w2.id, w3.id])
    assert sorted(repo.list_workspaces_for_generation(gen)) == sorted([w2.id, w3.id])

    # 空数组 = 清空
    repo.assign_workspaces(gen, [])
    assert repo.list_workspaces_for_generation(gen) == []


def test_assign_workspaces_idempotent(session):
    repo = _repo(session)
    ws = repo.create("idem")
    repo.assign_workspaces("gen-y", [ws.id])
    repo.assign_workspaces("gen-y", [ws.id])
    assert repo.list_workspaces_for_generation("gen-y") == [ws.id]


def test_remove_workspace_from_generation(session):
    repo = _repo(session)
    w1 = repo.create("w1")
    w2 = repo.create("w2")
    repo.assign_workspaces("gen-z", [w1.id, w2.id])

    assert repo.remove_workspace_from_generation("gen-z", w1.id) is True
    assert repo.list_workspaces_for_generation("gen-z") == [w2.id]
    # 二次移除返回 False
    assert repo.remove_workspace_from_generation("gen-z", w1.id) is False
    # 不存在的 generation 也不抛
    assert repo.remove_workspace_from_generation("missing", w2.id) is False


def test_bulk_workspace_ids_for_generations(session):
    repo = _repo(session)
    w1 = repo.create("w1")
    w2 = repo.create("w2")
    repo.assign_workspaces("g1", [w1.id])
    repo.assign_workspaces("g2", [w1.id, w2.id])
    repo.assign_workspaces("g3", [])  # 0 关联

    mapping = repo.bulk_workspace_ids_for_generations(["g1", "g2", "g3", "g4"])
    assert sorted(mapping["g1"]) == [w1.id]
    assert sorted(mapping["g2"]) == sorted([w1.id, w2.id])
    # g3 / g4 没有关联 → 不出现在 mapping(调用方用 mapping.get(id, []) 兜底)
    assert "g3" not in mapping
    assert "g4" not in mapping


def test_bulk_empty_input(session):
    repo = _repo(session)
    assert repo.bulk_workspace_ids_for_generations([]) == {}


def test_generation_ids_in_workspace(session):
    repo = _repo(session)
    w = repo.create("shared")
    repo.assign_workspaces("ga", [w.id])
    repo.assign_workspaces("gb", [w.id])
    repo.assign_workspaces("gc", ["some-other-ws"])  # not in workspace repo; just creates link to non-existent workspace is impossible

    # Add gc to same workspace
    repo.assign_workspaces("gc", [w.id])
    ids = repo.generation_ids_in_workspace(w.id)
    assert sorted(ids) == ["ga", "gb", "gc"]
