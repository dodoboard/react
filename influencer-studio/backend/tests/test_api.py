import io
import zipfile

from PIL import Image

from tests.conftest import wait_job

SPEC = {
    "age": 27,
    "selections": {
        "gender": {"values": ["woman"]},
        "origin": {"values": ["turkish"]},
        "hair_style": {"values": ["long_wavy"]},
        "hair_color": {"values": ["auburn"], "level": "notable"},
    },
}


def png_bytes(size=(64, 80)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (200, 150, 120)).save(buf, format="JPEG")
    return buf.getvalue()


def class_types(graph: dict) -> list[str]:
    return [n["class_type"] for n in graph.values()]


def create_character(client) -> dict:
    job = wait_job(client, client.post("/api/builder/generate", json={"spec": SPEC, "count": 2}).json())
    assert job["status"] == "done", job
    return client.post("/api/characters", json={"name": "Elif Nova", "spec": SPEC, "image_id": job["outputs"][0]["id"]}).json()


def test_schema_and_health(client, fake_comfy):
    schema = client.get("/api/schema").json()
    assert len(schema["attributes"]) == 18 and schema["max_refs"] == 4
    health = client.get("/api/health").json()
    assert health["comfy"] and health["missing_models"] == [] and health["gpu"] == "Fake GPU"
    fake_comfy.app.state.models = {}
    assert len(client.get("/api/health").json()["missing_models"]) == 3


def test_builder_with_face_requires_consent(client, fake_comfy):
    face = client.post("/api/uploads", files={"file": ("me.jpg", png_bytes(), "image/jpeg")}).json()
    assert face["kind"] == "upload"
    body = {"spec": SPEC, "face_image_id": face["id"], "count": 1}
    assert client.post("/api/builder/generate", json=body).status_code == 422

    job = wait_job(client, client.post("/api/builder/generate", json=body | {"consent": True}).json())
    assert job["status"] == "done" and job["progress"] == 1.0
    graph = fake_comfy.prompts[-1]
    assert class_types(graph).count("LoadImage") == 1

    # A generated candidate can be reused as the face reference without consent.
    again = client.post("/api/builder/generate", json={"spec": SPEC, "face_image_id": job["outputs"][0]["id"], "count": 1})
    assert wait_job(client, again.json())["status"] == "done"
    assert "Keep the facial identity" in next(n["inputs"]["text"] for n in graph.values() if n["class_type"] == "CLIPTextEncode")
    img = client.get(job["outputs"][0]["url"])
    assert img.headers["content-type"] == "image/png" and Image.open(io.BytesIO(img.content)).size == (1024, 1024)


def test_upload_rejects_non_images(client):
    assert client.post("/api/uploads", files={"file": ("x.txt", b"hello", "text/plain")}).status_code == 422


def test_character_lifecycle(client, fake_comfy):
    character = create_character(client)
    assert character["reference_ids"] == [character["portrait_id"]]
    cid = character["id"]

    pack = wait_job(client, client.post(f"/api/characters/{cid}/identity-pack", json={"angles": ["profile", "smile"]}).json())
    assert pack["status"] == "done" and len(pack["outputs"]) == 2
    assert all(i["kind"] == "reference" and i["character_id"] == cid for i in pack["outputs"])

    refs = [character["portrait_id"], pack["outputs"][0]["id"]]
    updated = client.patch(f"/api/characters/{cid}", json={"reference_ids": refs, "lora": "zz_demo_lora.safetensors", "lora_strength": 0.7}).json()
    assert updated["reference_ids"] == refs and updated["lora_strength"] == 0.7
    assert client.patch(f"/api/characters/{cid}", json={"reference_ids": ["foreign"]}).status_code == 422

    job = wait_job(client, client.post(f"/api/characters/{cid}/content",
                                       json={"preset_id": "coffee", "prompt": "beige trench coat", "count": 3, "aspect": "9:16"}).json())
    assert job["status"] == "done" and len(job["outputs"]) == 3
    graph = fake_comfy.prompts[-1]
    types = class_types(graph)
    assert types.count("LoadImage") == 2 and types.count("ReferenceLatent") == 4 and "LoraLoaderModelOnly" in types
    assert job["outputs"][0]["width"] == 768 and job["outputs"][0]["caption"].endswith("beige trench coat")

    detail = client.get(f"/api/characters/{cid}").json()
    assert len(detail["images"]) == 1 + 2 + 3
    assert client.get("/api/characters").json()[0]["image_count"] == 6

    z = zipfile.ZipFile(io.BytesIO(client.get(f"/api/characters/{cid}/dataset.zip").content))
    names = z.namelist()
    assert "train_flux2_klein_4b.yaml" in names and sum(n.endswith(".png") for n in names) == 6
    assert z.read("dataset/001.txt").decode().startswith("zz_elif_nova, ")
    assert "arch: flux2_klein_4b" in z.read("train_flux2_klein_4b.yaml").decode()

    assert client.delete(f"/api/images/{character['portrait_id']}").status_code == 422
    assert client.delete(f"/api/images/{refs[1]}").status_code == 204
    assert client.get(f"/api/characters/{cid}").json()["reference_ids"] == [character["portrait_id"]]

    assert client.delete(f"/api/characters/{cid}").status_code == 204
    assert client.get(f"/api/characters/{cid}").status_code == 404


def test_comfy_validation_error_surfaces_on_job(client, fake_comfy):
    fake_comfy.app.state.models = {}
    job = wait_job(client, client.post("/api/builder/generate", json={"spec": SPEC, "count": 1}).json())
    assert job["status"] == "error" and "UNETLoader" in job["error"] and "Value not in list" in job["error"]


def test_content_validation(client):
    character = create_character(client)
    url = f"/api/characters/{character['id']}/content"
    assert client.post(url, json={"prompt": ""}).status_code == 422
    assert client.post(url, json={"preset_id": "nope"}).status_code == 422
    assert client.post(url, json={"prompt": "x", "aspect": "2:1"}).status_code == 422
    assert client.post("/api/characters/missing/content", json={"prompt": "x"}).status_code == 404


def test_concurrent_image_requests(client):
    from concurrent.futures import ThreadPoolExecutor

    job = wait_job(client, client.post("/api/builder/generate", json={"spec": SPEC, "count": 4}).json())
    urls = [i["url"] for i in job["outputs"]] * 25
    with ThreadPoolExecutor(16) as pool:
        statuses = list(pool.map(lambda u: client.get(u).status_code, urls))
    assert statuses == [200] * len(urls)
