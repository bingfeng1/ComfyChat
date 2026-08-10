from app.models.lora import Lora
from app.repositories.lora import LoraRepository


def _repo(session):
    return LoraRepository(session)


def test_upsert_and_list(session):
    repo = _repo(session)
    repo.upsert_lora("mumu_20.safetensors", base_family="Z-Image", source_url="https://x")
    repo.upsert_lora("coser-z_20.safetensors")
    items = repo.list_all()
    assert {name for name, _ in items} == {"mumu_20.safetensors", "coser-z_20.safetensors"}
    by_name = dict(items)
    assert by_name["mumu_20.safetensors"] == []
    lora = session.get(Lora, "mumu_20.safetensors")
    assert lora.base_family == "Z-Image"
    assert lora.source_url == "https://x"


def test_replace_links(session):
    repo = _repo(session)
    repo.upsert_lora("mumu_20.safetensors")
    repo.replace_links("mumu_20.safetensors", ["a.safetensors", "b.safetensors"], "workflow")
    items = dict(repo.list_all())
    assert sorted(items["mumu_20.safetensors"]) == ["a.safetensors", "b.safetensors"]
    # 二次替换应覆盖同源链接
    repo.replace_links("mumu_20.safetensors", ["c.safetensors"], "workflow")
    items = dict(repo.list_all())
    assert items["mumu_20.safetensors"] == ["c.safetensors"]


def test_replace_links_preserves_other_source(session):
    repo = _repo(session)
    repo.upsert_lora("mumu_20.safetensors")
    # manual 先写
    repo.replace_links("mumu_20.safetensors", ["manual_model.safetensors"], "manual")
    # workflow 后写,只该覆盖 workflow 源,manual 的链接保留
    repo.replace_links("mumu_20.safetensors", ["wf_model.safetensors"], "workflow")
    items = dict(repo.list_all())
    assert sorted(items["mumu_20.safetensors"]) == [
        "manual_model.safetensors",
        "wf_model.safetensors",
    ]
    # 再跑一次 workflow 覆盖,manual 仍保留
    repo.replace_links("mumu_20.safetensors", ["wf2.safetensors"], "workflow")
    items = dict(repo.list_all())
    assert sorted(items["mumu_20.safetensors"]) == ["manual_model.safetensors", "wf2.safetensors"]


def test_replace_links_same_model_updates_source(session):
    repo = _repo(session)
    repo.upsert_lora("mumu_20.safetensors")
    # 同一 (lora, model) 先以 workflow 写入
    repo.replace_links("mumu_20.safetensors", ["z_image_turbo_int8_convrot.safetensors"], "workflow")
    # 再以 manual 写同一 model → 不应 UNIQUE 冲突,应更新 source
    repo.replace_links("mumu_20.safetensors", ["z_image_turbo_int8_convrot.safetensors"], "manual")
    items = dict(repo.list_all())
    assert items["mumu_20.safetensors"] == ["z_image_turbo_int8_convrot.safetensors"]


def test_clear_stale(session):
    repo = _repo(session)
    repo.upsert_lora("keep.safetensors")
    repo.upsert_lora("drop.safetensors")
    repo.clear_stale({"keep.safetensors"})
    names = {n for n, _ in repo.list_all()}
    assert names == {"keep.safetensors"}


def test_list_all_dedupes_same_model_from_multiple_sources(session):
    repo = _repo(session)
    repo.upsert_lora("mumu_20.safetensors")
    repo.replace_links("mumu_20.safetensors", ["z_image_turbo_int8_convrot.safetensors"], "workflow")
    repo.replace_links("mumu_20.safetensors", ["z_image_turbo_int8_convrot.safetensors"], "manual")
    items = dict(repo.list_all())
    assert items["mumu_20.safetensors"] == ["z_image_turbo_int8_convrot.safetensors"]
