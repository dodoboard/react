import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from studio.api import create_app
from studio.comfy import ComfyClient
from studio.settings import Settings
from studio.voice import TTSClient
from tests.conftest import wait_job

SPEC = {"age": 28, "selections": {"gender": {"values": ["woman"]}}}

# Stands in for ai-toolkit's run.py: tqdm-style progress on \r, then the LoRA file.
FAKE_RUN = r'''
import sys, re, pathlib
config = open(sys.argv[1], encoding="utf-8").read()
name = re.search(r"name: (\S+)", config).group(1)
steps = int(re.search(r"steps: (\d+)", config).group(1))
out = pathlib.Path(re.search(r"training_folder: (\S+)", config).group(1)) / name
dataset = pathlib.Path(re.search(r"folder_path: (\S+)", config).group(1))
if len(list(dataset.glob("*.png"))) < 10 or "FAIL" in config:
    print("Error: dataset too small"); sys.exit(3)
for s in range(0, steps + 1, steps // 4):
    sys.stdout.write(f"\r{name}: {100 * s // steps}%|##| {s}/{steps} [00:01<00:02, loss: 3.1e-01]"); sys.stdout.flush()
out.mkdir(parents=True, exist_ok=True)
(out / f"{name}.safetensors").write_bytes(b"lora")
print("\nDone")
'''


@pytest.fixture
def setup(fake_comfy, fake_tts, tmp_path):
    aitk = tmp_path / "ai-toolkit"
    aitk.mkdir()
    (aitk / "run.py").write_text(FAKE_RUN)
    comfy_dir = tmp_path / "ComfyUI"
    (comfy_dir / "models" / "loras").mkdir(parents=True)
    settings = Settings(comfy_url=fake_comfy.url, data_dir=tmp_path / "data", frontend_dist=tmp_path / "none",
                        tts_url=fake_tts.url, aitk_dir=aitk, aitk_python=sys.executable, comfy_dir=str(comfy_dir))
    with TestClient(create_app(settings, ComfyClient(fake_comfy.url), TTSClient(fake_tts.url))) as client:
        yield client, comfy_dir, fake_comfy


def make_character(client, images):
    job = wait_job(client, client.post("/api/builder/generate", json={"spec": SPEC, "count": 1}).json())
    character = client.post("/api/characters", json={"name": "Ada Nur", "spec": SPEC, "image_id": job["outputs"][0]["id"]}).json()
    while len(client.get(f"/api/characters/{character['id']}").json()["images"]) < images:
        wait_job(client, client.post(f"/api/characters/{character['id']}/content",
                                     json={"preset_id": "coffee", "count": 4}).json())
    return character


def test_status_explains_what_is_missing(setup, tmp_path):
    client, _, _ = setup
    character = make_character(client, 2)
    status = client.get(f"/api/characters/{character['id']}/lora").json()
    assert not status["ready"] and status["trigger"] == "zz_ada_nur"
    assert any("identity pack" in p for p in status["problems"])
    assert client.post(f"/api/characters/{character['id']}/lora").status_code == 422
    assert client.get("/api/characters/nope/lora").status_code == 404


def test_training_reports_progress_and_assigns_the_lora(setup):
    client, comfy_dir, fake_comfy = setup
    character = make_character(client, 10)
    assert client.get(f"/api/characters/{character['id']}/lora").json()["ready"]
    frees = fake_comfy.app.state.frees
    job = wait_job(client, client.post(f"/api/characters/{character['id']}/lora?steps=400").json(), timeout=60)
    assert job["status"] == "done", job
    assert (comfy_dir / "models" / "loras" / "zz_ada_nur.safetensors").read_bytes() == b"lora"
    updated = client.get(f"/api/characters/{character['id']}").json()
    assert updated["lora"] == "zz_ada_nur.safetensors" and updated["lora_strength"] == 0.9
    assert fake_comfy.app.state.frees == frees + 1  # ComfyUI unloaded for the training run


def test_training_failure_shows_the_log(setup):
    client, _, _ = setup
    character = make_character(client, 10)
    import studio.lora as lora_module

    original = lora_module.aitk_config
    lora_module.aitk_config = lambda *a, **k: original(*a, **k) + "\n# FAIL\n"
    try:
        job = wait_job(client, client.post(f"/api/characters/{character['id']}/lora?steps=400").json(), timeout=60)
    finally:
        lora_module.aitk_config = original
    assert job["status"] == "error" and "exited with code 3" in job["error"] and "dataset too small" in job["error"]
