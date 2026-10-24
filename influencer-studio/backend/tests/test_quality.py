import io

import av
import pytest
from PIL import Image

from studio.face import CROP_SIZE, DENOISE, Face, crop_box, paste_back
from studio.flux2 import PROFILES, build_graph
from studio.hd import CHUNK_FRAMES, build_image_upscale_graph, build_video_upscale_graph, hd_size
from tests.conftest import wait_job
from tests.fake_comfy import IMG2IMG_COLOR

SPEC = {"age": 27, "selections": {"gender": {"values": ["woman"]}}}


@pytest.fixture
def character(client):
    job = wait_job(client, client.post("/api/builder/generate", json={"spec": SPEC, "count": 1}).json())
    return client.post("/api/characters", json={"name": "Ela", "spec": SPEC, "image_id": job["outputs"][0]["id"]}).json()


@pytest.fixture
def content(client, character):
    job = wait_job(client, client.post(f"/api/characters/{character['id']}/content",
                                       json={"preset_id": "gym", "count": 1, "aspect": "3:4"}).json())
    return job["outputs"][0]


def by_type(graph, class_type):
    return [n["inputs"] for n in graph.values() if n["class_type"] == class_type]


def pixel(client, image, xy):
    return Image.open(io.BytesIO(client.get(image["url"]).content)).convert("RGB").getpixel(xy)


# ── graphs and geometry ─────────────────────────────────────────────────────
def test_img2img_graph_keeps_four_steps_at_partial_denoise():
    g = build_graph(PROFILES["klein-4b"], prompt="face", width=1024, height=1024, seed=3,
                    references=["ref.png"], init_image="crop.png", denoise=0.4)
    (scheduler,) = by_type(g, "Flux2Scheduler")
    (split,) = by_type(g, "SplitSigmasDenoise")
    (sampler,) = by_type(g, "SamplerCustomAdvanced")
    assert scheduler["steps"] == 10 and split["denoise"] == 0.4  # round(10 × 0.4) = 4 steps run
    assert sampler["sigmas"][1] == 1  # the low-sigma tail
    assert g[sampler["latent_image"][0]]["class_type"] == "VAEEncode" and not by_type(g, "EmptyFlux2LatentImage")
    assert {i["image"] for i in by_type(g, "LoadImage")} == {"ref.png", "crop.png"}
    with pytest.raises(ValueError):
        build_graph(PROFILES["klein-4b"], prompt="x", width=64, height=64, seed=1, init_image="a.png", denoise=0)


def test_upscale_graphs():
    g = build_image_upscale_graph("in.png")
    assert by_type(g, "ImageScaleBy")[0]["scale_by"] == 0.5 and by_type(g, "UpscaleModelLoader")[0]["model_name"] == "RealESRGAN_x4plus.pth"
    v = build_video_upscale_graph("chunk.mp4", 1080, 1872)
    (create,) = by_type(v, "CreateVideo")
    assert v[create["fps"][0]]["class_type"] == "GetVideoComponents" and create["fps"][1] == 2  # source frame rate
    (scale,) = by_type(v, "ImageScale")
    assert (scale["width"], scale["height"], scale["upscale_method"]) == (1080, 1872, "lanczos")
    assert hd_size(480, 832) == (1080, 1872) and hd_size(832, 480) == (1872, 1080) and hd_size(624, 624) == (1080, 1080)


def test_crop_box_stays_square_and_inside():
    assert crop_box(Face(450, 100, 100, 120), 1000, 1500) == (392, 52, 608, 268)  # 1.8 × 120 = 216
    left, top, right, bottom = crop_box(Face(5, 5, 60, 60), 400, 600)  # near the corner: shifted in
    assert (left, top) == (0, 0) and right - left == bottom - top == 108
    assert crop_box(Face(0, 0, 900, 900), 400, 600) == (0, 200, 400, 600)  # never larger than the image


def test_paste_back_blends_inside_the_box_only():
    base = Image.new("RGB", (400, 600), (10, 20, 30))
    out = paste_back(base, Image.new("RGB", (CROP_SIZE, CROP_SIZE), (250, 250, 250)), (100, 200, 300, 400))
    assert out.size == base.size and out.getpixel((200, 300)) == (250, 250, 250)
    assert out.getpixel((101, 201)) == (10, 20, 30)  # soft ellipse: the crop corners keep the original
    assert out.getpixel((50, 50)) == (10, 20, 30)


# ── face detail ─────────────────────────────────────────────────────────────
def small_face(image):  # ~1 % of the frame, like a full-body shot
    return [Face(image.width * 0.45, image.height * 0.2, image.width * 0.1, image.width * 0.1)]


def test_face_fix_redraws_the_face_with_references(client, fake_comfy, character, content):
    client.app.state.studio.detector = small_face
    job = wait_job(client, client.post(f"/api/images/{content['id']}/face-fix").json())
    assert job["status"] == "done", job
    (fixed,) = job["outputs"]
    assert fixed["caption"].endswith("face detail") and (fixed["width"], fixed["height"]) == (content["width"], content["height"])
    cx, cy = round(content["width"] * 0.5), round(content["height"] * 0.2 + content["width"] * 0.05)
    assert pixel(client, fixed, (cx, cy)) == IMG2IMG_COLOR
    assert pixel(client, fixed, (2, content["height"] - 3)) == pixel(client, content, (2, content["height"] - 3))
    graph = fake_comfy.prompts[-1]
    assert by_type(graph, "SplitSigmasDenoise")[0]["denoise"] == DENOISE
    assert len(by_type(graph, "ReferenceLatent")) == 2 * len(character["reference_ids"])  # identity kept
    assert by_type(graph, "Flux2Scheduler")[0]["width"] == CROP_SIZE

    client.app.state.studio.detector = lambda image: []
    job = wait_job(client, client.post(f"/api/images/{content['id']}/face-fix").json())
    assert job["status"] == "error" and "no face" in job["error"]
    candidate = wait_job(client, client.post("/api/builder/generate", json={"spec": SPEC, "count": 1}).json())["outputs"][0]
    assert client.post(f"/api/images/{candidate['id']}/face-fix").status_code == 422


def test_content_face_detail_only_touches_small_faces(client, fake_comfy, character):
    url = f"/api/characters/{character['id']}/content"
    body = {"preset_id": "gym", "count": 2, "aspect": "3:4", "face_detail": True}
    client.app.state.studio.detector = small_face
    job = wait_job(client, client.post(url, json=body).json())
    assert job["status"] == "done" and len(job["outputs"]) == 2
    img = job["outputs"][0]
    assert pixel(client, img, (round(img["width"] * 0.5), round(img["height"] * 0.2 + img["width"] * 0.05))) == IMG2IMG_COLOR
    sent = len(fake_comfy.prompts)
    client.app.state.studio.detector = lambda image: [Face(0, 0, image.width * 0.5, image.width * 0.5)]  # close-up
    assert wait_job(client, client.post(url, json=body).json())["status"] == "done"
    assert len(fake_comfy.prompts) == sent + 1  # only the content render, no face pass


# ── HD ──────────────────────────────────────────────────────────────────────
def test_image_upscale_doubles_the_size(client, fake_comfy, content):
    job = wait_job(client, client.post(f"/api/images/{content['id']}/upscale").json())
    assert job["status"] == "done", job
    (hd,) = job["outputs"]
    assert (hd["width"], hd["height"]) == (2 * content["width"], 2 * content["height"]) and hd["caption"].endswith("HD")
    fake_comfy.app.state.models = {k: v for k, v in fake_comfy.app.state.models.items() if k != "upscale_models"}
    job = wait_job(client, client.post(f"/api/images/{content['id']}/upscale").json())
    assert job["status"] == "error" and "--video hd" in job["error"]


def test_video_hd_upscales_in_chunks_and_keeps_audio(client, fake_comfy, character):
    talk = wait_job(client, client.post(f"/api/characters/{character['id']}/talk", json={
        "source_image_id": character["portrait_id"], "text": "Merhaba, bu bir HD testi.", "orientation": "portrait",
    }).json())["outputs"][0]
    with av.open(io.BytesIO(client.get(talk["url"]).content)) as c:
        frames = sum(1 for _ in c.decode(video=0))
    assert frames > CHUNK_FRAMES  # so the clip really goes through several chunks
    sent = len(fake_comfy.prompts)
    job = wait_job(client, client.post(f"/api/clips/{talk['id']}/upscale").json(), timeout=60)
    assert job["status"] == "done", job
    (hd,) = job["outputs"]
    assert hd["kind"] == "talk" and (hd["width"], hd["height"]) == (1080, 1872) and hd["has_audio"]
    assert hd["meta"]["hd"] and hd["meta"]["source_clip_id"] == talk["id"]
    assert hd["meta"]["segments"] == talk["meta"]["segments"]  # subtitles carry over
    assert len(fake_comfy.prompts) - sent == -(-frames // CHUNK_FRAMES)
    with av.open(io.BytesIO(client.get(hd["url"]).content)) as c:
        assert [s.type for s in c.streams] == ["video", "audio"]
        assert sum(1 for _ in c.decode(video=0)) == frames
    assert hd["duration"] == pytest.approx(talk["duration"], abs=0.1)

    assert client.post(f"/api/clips/{hd['id']}/upscale").status_code == 422  # already HD
    speech = next(c for c in client.get(f"/api/characters/{character['id']}/clips").json() if c["kind"] == "speech")
    assert client.post(f"/api/clips/{speech['id']}/upscale").status_code == 422  # not a video
    assert client.post("/api/clips/nope/upscale").status_code == 404
