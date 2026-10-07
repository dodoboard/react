import io

import av
import pytest

from tests.conftest import wait_job
from tests.media_fixtures import make_video, make_wav

SPEC = {"age": 24, "selections": {"gender": {"values": ["woman"]}, "hair_style": {"values": ["bob"]}}}


@pytest.fixture
def character(client):
    job = wait_job(client, client.post("/api/builder/generate", json={"spec": SPEC, "count": 1, "aspect": "3:4"}).json())
    return client.post("/api/characters", json={"name": "Mira", "spec": SPEC, "image_id": job["outputs"][0]["id"]}).json()


def upload(client, kind, path, name=None):
    with open(path, "rb") as f:
        return client.post(f"/api/motion/uploads?kind={kind}", files={"file": (name or path.name, f, "application/octet-stream")})


def graph_of(fake_comfy):
    return fake_comfy.prompts[-1]


def class_types(graph):
    return [n["class_type"] for n in graph.values()]


def decode(client, clip):
    data = client.get(clip["url"]).content
    with av.open(io.BytesIO(data)) as c:
        return [s.type for s in c.streams], sum(1 for _ in c.decode(video=0))


def test_schema_and_health(client, fake_comfy):
    schema = client.get("/api/motion/schema").json()
    assert {s["id"] for s in schema["styles"]} == {"kpop", "street", "latin", "tap", "classical"}
    assert schema["resolutions"]["480p"]["portrait"] == {"width": 480, "height": 832}
    health = client.get("/api/motion/health").json()
    assert health["comfy"] and all(m == [] for m in health["modes"].values())
    fake_comfy.app.state.models = {}
    health = client.get("/api/motion/health").json()
    assert len(health["modes"]["dance"]) == 4 and len(health["modes"]["smooth"]) == 1


def test_uploads_are_validated(client, tmp_path):
    driver = upload(client, "driver", make_video(tmp_path / "dance.mp4", seconds=2))
    assert driver.status_code == 201
    d = driver.json()
    assert d["kind"] == "driver" and d["has_audio"] and d["width"] == 640 and d["duration"] == pytest.approx(2, abs=0.1)
    assert client.get(d["url"]).headers["content-type"] == "video/mp4"

    song = upload(client, "music", make_wav(tmp_path / "song.wav", seconds=6, onset=0)).json()
    assert song["kind"] == "music" and not song["width"]
    assert [c["id"] for c in client.get("/api/motion/uploads?kind=music").json()] == [song["id"]]

    assert upload(client, "driver", make_wav(tmp_path / "x.wav", seconds=1, onset=0)).status_code == 422  # not a video
    assert upload(client, "music", make_video(tmp_path / "silent.mp4", seconds=1, audio=False)).status_code == 422
    (tmp_path / "fake.mp4").write_bytes(b"garbage")
    assert upload(client, "driver", tmp_path / "fake.mp4").status_code == 422
    assert upload(client, "driver", tmp_path / "fake.mp4", name="x.exe").status_code == 422
    assert upload(client, "selfie", tmp_path / "fake.mp4").status_code == 422


def test_dance_transfer(client, fake_comfy, character, tmp_path):
    driver = upload(client, "driver", make_video(tmp_path / "dance.mp4", seconds=3, fps=30, size=(360, 640))).json()
    body = {"source_image_id": character["portrait_id"], "driver_id": driver["id"], "start": 0.5, "seconds": 2}
    job = wait_job(client, client.post(f"/api/characters/{character['id']}/motion/dance", json=body).json())
    assert job["status"] == "done", job
    (clip,) = job["outputs"]
    assert clip["kind"] == "dance" and clip["character_id"] == character["id"] and clip["has_audio"]
    assert (clip["width"], clip["height"]) == (480, 832)  # auto orientation follows the portrait driver
    assert decode(client, clip)[0] == ["video", "audio"]

    g = graph_of(fake_comfy)
    (animate,) = [n["inputs"] for n in g.values() if n["class_type"] == "WanAnimate2ToVideo"]
    assert animate["length"] == 33  # 2 s at 16 fps = 32 frames → one 33-frame window
    assert "LoadAudio" in class_types(g) and "Dancing" in next(
        n["inputs"]["text"] for n in g.values() if n["class_type"] == "CLIPTextEncode")
    assert client.get(f"/api/characters/{character['id']}/clips").json()[0]["id"] == clip["id"]

    body |= {"keep_audio": False, "smooth": True, "orientation": "square", "resolution": "720p", "seconds": 20}
    job = wait_job(client, client.post(f"/api/characters/{character['id']}/motion/dance", json=body).json())
    (clip,) = job["outputs"]
    assert (clip["width"], clip["height"]) == (960, 960) and not clip["has_audio"]
    g = graph_of(fake_comfy)
    assert "LoadAudio" not in class_types(g) and "FrameInterpolate" in class_types(g)
    # seconds are clamped to what the clip has left after `start`: 2.5 s → 40 frames
    assert [n["inputs"]["length"] for n in g.values() if n["class_type"] == "WanAnimate2ToVideo"] == [41]


def test_music_dance(client, fake_comfy, character, tmp_path):
    song = upload(client, "music", make_wav(tmp_path / "song.wav", seconds=12, onset=1)).json()
    body = {"source_image_id": character["portrait_id"], "music_id": song["id"], "start": 1, "seconds": 10,
            "style": "street", "energy": "max"}
    job = wait_job(client, client.post(f"/api/characters/{character['id']}/motion/music", json=body).json())
    assert job["status"] == "done", job
    (clip,) = job["outputs"]
    assert clip["kind"] == "music_dance" and clip["has_audio"] and clip["caption"].startswith("Street · Max energy")
    g = graph_of(fake_comfy)
    (pad,) = [n["inputs"] for n in g.values() if n["class_type"] == "WanDancerPadKeyframesList"]
    assert pad["num_segments"] == 2
    url = f"/api/characters/{character['id']}/motion/music"
    assert client.post(url, json=body | {"seconds": 15}).status_code == 422  # only 11 s left after start
    assert client.post(url, json=body | {"seconds": 7}).status_code == 422
    assert client.post(url, json=body | {"style": "waltz"}).status_code == 422


def test_motion_preset_and_clip_lifecycle(client, fake_comfy, character, tmp_path):
    url = f"/api/characters/{character['id']}/motion/preset"
    body = {"source_image_id": character["portrait_id"], "preset_id": "hair_flip", "prompt": "in slow motion"}
    job = wait_job(client, client.post(url, json=body).json())
    (clip,) = job["outputs"]
    assert clip["kind"] == "motion" and clip["caption"] == "Hair flip"
    text = next(n["inputs"]["text"] for n in graph_of(fake_comfy).values() if n["class_type"] == "CLIPTextEncode")
    assert "The woman flips her hair over the shoulder" in text and "in slow motion" in text
    kinds, frames = decode(client, clip)
    assert kinds == ["video"] and frames == 32

    assert client.post(url, json={"source_image_id": character["portrait_id"]}).status_code == 422
    assert client.post(url, json=body | {"preset_id": "moonwalk"}).status_code == 422
    other = wait_job(client, client.post("/api/builder/generate", json={"spec": SPEC, "count": 1}).json())["outputs"][0]
    assert client.post(url, json=body | {"source_image_id": other["id"]}).status_code == 422  # not this character's

    assert client.delete(f"/api/clips/{clip['id']}").status_code == 204
    assert client.get(clip["url"]).status_code == 404

    job = wait_job(client, client.post(url, json=body).json())
    path = client.app.state.studio.store.clip_path(job["outputs"][0])
    assert path.exists()
    client.delete(f"/api/characters/{character['id']}")
    assert not path.exists()


def test_progress_spans_all_samplers(client, fake_comfy, character, tmp_path):
    driver = upload(client, "driver", make_video(tmp_path / "long.mp4", seconds=12, fps=16, audio=False)).json()
    body = {"source_image_id": character["portrait_id"], "driver_id": driver["id"], "seconds": 11}
    job = client.post(f"/api/characters/{character['id']}/motion/dance", json=body).json()
    seen = []
    while job["status"] in ("queued", "running"):
        job = client.get(f"/api/jobs/{job['id']}").json()
        seen.append(job["progress"])
    windows = [n for n in graph_of(fake_comfy).values() if n["class_type"] == "WanAnimate2ToVideo"]
    assert len(windows) == 3 and job["status"] == "done"
    assert seen == sorted(seen)  # monotonic across the three sampling passes
