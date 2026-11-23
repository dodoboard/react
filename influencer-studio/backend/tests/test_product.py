import io

import pytest
from PIL import Image

from tests.conftest import wait_job

SPEC = {"age": 30, "selections": {"gender": {"values": ["man"]}}}


@pytest.fixture
def character(client):
    job = wait_job(client, client.post("/api/builder/generate", json={"spec": SPEC, "count": 1}).json())
    return client.post("/api/characters", json={"name": "Can", "spec": SPEC, "image_id": job["outputs"][0]["id"]}).json()


def product_upload(client):
    buf = io.BytesIO()
    Image.new("RGB", (400, 600), (20, 120, 220)).save(buf, format="PNG")
    return client.post("/api/uploads", files={"file": ("serum.png", buf.getvalue(), "image/png")}).json()


def load_images(graph):
    return [n["inputs"]["image"] for n in graph.values() if n["class_type"] == "LoadImage"]


def test_product_takes_the_last_reference_slot(client, fake_comfy, character):
    product = product_upload(client)
    # fill the character's references up to FLUX.2's limit
    pack = wait_job(client, client.post(f"/api/characters/{character['id']}/identity-pack",
                                        json={"angles": ["front", "smile", "profile"]}).json())
    refs = [character["portrait_id"], *[i["id"] for i in pack["outputs"]]]
    client.patch(f"/api/characters/{character['id']}", json={"reference_ids": refs})
    job = wait_job(client, client.post(f"/api/characters/{character['id']}/content", json={
        "preset_id": "product", "count": 1, "product_image_id": product["id"]}).json())
    assert job["status"] == "done", job
    graph = fake_comfy.prompts[-1]
    images = load_images(graph)
    assert len(images) == 4 and images[-1] == f"studio_{product['id']}.png"  # 3 character refs + product
    prompt = next(n["inputs"]["text"] for n in graph.values() if n["class_type"] == "CLIPTextEncode")
    assert "exact shape, colors, label and logo" in prompt


def test_product_must_be_an_upload(client, character):
    url = f"/api/characters/{character['id']}/content"
    assert client.post(url, json={"preset_id": "product", "product_image_id": character["portrait_id"]}).status_code == 422
    assert client.post(url, json={"preset_id": "product", "product_image_id": "nope"}).status_code == 404
