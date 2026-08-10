from app.models.lora import Lora
from app.repositories.lora import LoraRepository


def _repo(session):
    return LoraRepository(session)


def _by_name(items):
    return {lora.name: models for lora, models in items}


def test_upsert_and_list(session):
    repo = _repo(session)
    repo.upsert_lora("mumu_20.safetensors", base_family="Z-Image", source_url="https://x")
    repo.upsert_lora("coser-z_20.safetensors")
    items = repo.list_all()
    by_name = _by_name(items)
    assert set(by_name) == {"mumu_20.safetensors", "coser-z_20.safetensors"}
    assert by_name["mumu_20.safetensors"] == []
    lora = session.get(Lora, "mumu_20.safetensors")
    assert lora.base_family == "Z-Image"
    assert lora.source_url == "https://x"


def test_replace_links(session):
    repo = _repo(session)
    repo.upsert_lora("mumu_20.safetensors")
    repo.replace_links("mumu_20.safetensors", ["a.safetensors", "b.safetensors"], "workflow")
    items = _by_name(repo.list_all())
    assert sorted(items["mumu_20.safetensors"]) == ["a.safetensors", "b.safetensors"]
    # 二次替换应覆盖同源链接
    repo.replace_links("mumu_20.safetensors", ["c.safetensors"], "workflow")
    items = _by_name(repo.list_all())
    assert items["mumu_20.safetensors"] == ["c.safetensors"]


def test_replace_links_preserves_other_source(session):
    repo = _repo(session)
    repo.upsert_lora("mumu_20.safetensors")
    # manual 先写
    repo.replace_links("mumu_20.safetensors", ["manual_model.safetensors"], "manual")
    # workflow 后写,只该覆盖 workflow 源,manual 的链接保留
    repo.replace_links("mumu_20.safetensors", ["wf_model.safetensors"], "workflow")
    items = _by_name(repo.list_all())
    assert sorted(items["mumu_20.safetensors"]) == [
        "manual_model.safetensors",
        "wf_model.safetensors",
    ]
    # 再跑一次 workflow 覆盖,manual 仍保留
    repo.replace_links("mumu_20.safetensors", ["wf2.safetensors"], "workflow")
    items = _by_name(repo.list_all())
    assert sorted(items["mumu_20.safetensors"]) == ["manual_model.safetensors", "wf2.safetensors"]


def test_replace_links_same_model_updates_source(session):
    repo = _repo(session)
    repo.upsert_lora("mumu_20.safetensors")
    # 同一 (lora, model) 先以 workflow 写入
    repo.replace_links("mumu_20.safetensors", ["z_image_turbo_int8_convrot.safetensors"], "workflow")
    # 再以 manual 写同一 model → 不应 UNIQUE 冲突,应更新 source
    repo.replace_links("mumu_20.safetensors", ["z_image_turbo_int8_convrot.safetensors"], "manual")
    items = _by_name(repo.list_all())
    assert items["mumu_20.safetensors"] == ["z_image_turbo_int8_convrot.safetensors"]


def test_mark_deleted_preserves_record_and_links(session):
    repo = _repo(session)
    repo.upsert_lora("gone.safetensors")
    repo.replace_links("gone.safetensors", ["m.safetensors"], "manual")
    repo.mark_deleted("gone.safetensors")
    lora = session.get(Lora, "gone.safetensors")
    assert lora.deleted_from_comfyui is True
    # 绑定保留
    items = _by_name(repo.list_all())
    assert items["gone.safetensors"] == ["m.safetensors"]


def test_mark_present_recovers_deleted(session):
    repo = _repo(session)
    repo.upsert_lora("back.safetensors")
    repo.mark_deleted("back.safetensors")
    assert session.get(Lora, "back.safetensors").deleted_from_comfyui is True
    repo.mark_present("back.safetensors")
    assert session.get(Lora, "back.safetensors").deleted_from_comfyui is False


def test_mark_missing_marks_not_in_known(session):
    repo = _repo(session)
    repo.upsert_lora("keep.safetensors")
    repo.upsert_lora("drop.safetensors")
    repo.mark_missing({"keep.safetensors"})
    assert session.get(Lora, "keep.safetensors").deleted_from_comfyui is False
    assert session.get(Lora, "drop.safetensors").deleted_from_comfyui is True


def test_list_all_sorts_deleted_last(session):
    repo = _repo(session)
    repo.upsert_lora("b.safetensors")
    repo.upsert_lora("a.safetensors")
    repo.upsert_lora("z.safetensors")
    repo.mark_deleted("z.safetensors")
    names = [lora.name for lora, _ in repo.list_all()]
    assert names == ["a.safetensors", "b.safetensors", "z.safetensors"]


def test_names(session):
    repo = _repo(session)
    repo.upsert_lora("a.safetensors")
    repo.upsert_lora("b.safetensors")
    assert repo.names() == {"a.safetensors", "b.safetensors"}
