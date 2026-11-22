import io
import zipfile

import pytest

from studio.scripts_tr import render
from tests.conftest import wait_job

SPEC = {"age": 24, "selections": {"gender": {"values": ["woman"]}}}


@pytest.fixture
def character(client):
    job = wait_job(client, client.post("/api/builder/generate", json={"spec": SPEC, "count": 1}).json())
    return client.post("/api/characters", json={"name": "Nil", "spec": SPEC, "image_id": job["outputs"][0]["id"]}).json()


def wait_batch(client, character, timeout=90):
    import time

    deadline = time.monotonic() + timeout
    while True:
        (batch,) = client.get(f"/api/characters/{character['id']}/batches").json()
        if batch["finished"]:
            return batch
        assert time.monotonic() < deadline, batch
        time.sleep(0.1)


def test_templates_render_turkish_scripts():
    text = render("product", {"urun": "yeni serumu", "ozellik": "hafif dokusu", "fiyat": "₺499,90"})
    assert text.startswith("Merhaba arkadaşlar! Bugün size yeni serumu") and "₺499,90" in text
    with pytest.raises(ValueError, match="Fiyat"):
        render("product", {"urun": "x", "ozellik": "y"})


def test_pack_runs_posts_talks_and_exports(client, fake_comfy, character):
    templates = client.get("/api/scripts").json()
    assert {t["id"] for t in templates} >= {"product", "discount", "vlog"}
    body = {
        "posts": [{"preset_id": "coffee", "count": 2}, {"preset_id": "gym", "count": 1}],
        "talks": [
            {"template_id": "discount", "values": {"marka": "Lumi", "indirim": "%30", "tarih": "Pazar"}},
            {"text": "Günaydın! Bugün yeni bir rutin deniyorum."},
        ],
        "export": True,
    }
    created = client.post(f"/api/characters/{character['id']}/batches", json=body).json()
    assert [j["role"] for j in created["jobs"]] == ["post", "post", "talk", "talk"] and not created["finished"]
    batch = wait_batch(client, character)
    roles = [j["role"] for j in batch["jobs"]]
    assert roles.count("export") == 2 and all(j["job"]["status"] == "done" for j in batch["jobs"])
    exports = [j["job"]["outputs"][0] for j in batch["jobs"] if j["role"] == "export"]
    assert all(e["kind"] == "export" and (e["width"], e["height"]) == (1080, 1920) for e in exports)
    talk_prompt = next(g for g in fake_comfy.prompts if any(n["class_type"] == "WanInfiniteTalkToVideo" for n in g.values()))
    text = next(n["inputs"]["text"] for n in talk_prompt.values() if n["class_type"] == "CLIPTextEncode")
    assert "Enthusiastic, pointing at the camera" in text  # the template's expression prompt

    r = client.get(f"/api/batches/{batch['id']}.zip")
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert sum(n.endswith(".png") for n in names) == 3 and sum(n.endswith(".mp4") for n in names) == 4


def test_pack_is_validated_before_anything_is_queued(client, character):
    url = f"/api/characters/{character['id']}/batches"
    before = len(client.get("/api/jobs?limit=100").json())
    bad = {"posts": [{"preset_id": "coffee"}], "talks": [{"template_id": "product", "values": {"urun": "x"}}]}
    r = client.post(url, json=bad)
    assert r.status_code == 422 and "Ürün" not in r.json()["detail"] and "fill in" in r.json()["detail"]
    assert len(client.get("/api/jobs?limit=100").json()) == before
    assert client.post(url, json={"posts": [], "talks": []}).status_code == 422
    assert client.post("/api/characters/nope/batches", json={"posts": [{"preset_id": "gym"}]}).status_code == 404
