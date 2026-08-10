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
    # 二次替换应覆盖
    repo.replace_links("mumu_20.safetensors", ["c.safetensors"], "workflow")
    items = dict(repo.list_all())
    assert items["mumu_20.safetensors"] == ["c.safetensors"]


def test_clear_stale(session):
    repo = _repo(session)
    repo.upsert_lora("keep.safetensors")
    repo.upsert_lora("drop.safetensors")
    repo.clear_stale({"keep.safetensors"})
    names = {n for n, _ in repo.list_all()}
    assert names == {"keep.safetensors"}
