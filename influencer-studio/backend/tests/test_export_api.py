import io
import json

import av
import numpy as np
import pytest

from studio.export import DUCK_DB, FORMATS, HIGHLIGHT, TARGET_LUFS, duck_gain
from studio.media import AUDIO_RATE
from tests.conftest import wait_job
from tests.media_fixtures import make_video, make_wav

SPEC = {"age": 26, "selections": {"gender": {"values": ["woman"]}}}
SCRIPT = "Merhaba arkadaşlar! Bugün size %30 indirimli yeni koleksiyonu gösteriyorum."


@pytest.fixture
def character(client):
    job = wait_job(client, client.post("/api/builder/generate", json={"spec": SPEC, "count": 1}).json())
    return client.post("/api/characters", json={"name": "Su", "spec": SPEC, "image_id": job["outputs"][0]["id"]}).json()


@pytest.fixture
def talk(client, character):
    job = wait_job(client, client.post(f"/api/characters/{character['id']}/talk", json={
        "source_image_id": character["portrait_id"], "text": SCRIPT, "orientation": "portrait"}).json())
    return job["outputs"][0]


@pytest.fixture
def motion(client, character):
    job = wait_job(client, client.post(f"/api/characters/{character['id']}/motion/preset", json={
        "source_image_id": character["portrait_id"], "preset_id": "groove", "orientation": "portrait"}).json())
    return job["outputs"][0]


def upload(client, kind, path):
    with open(path, "rb") as f:
        return client.post(f"/api/motion/uploads?kind={kind}", files={"file": (path.name, f)}).json()


def frames_of(client, clip):
    with av.open(io.BytesIO(client.get(clip["url"]).content)) as c:
        return [f.to_ndarray(format="rgb24") for f in c.decode(video=0)]


def highlighted(frame):
    """Pixels in the karaoke colour inside the caption band."""
    h = frame.shape[0]
    band = frame[int(h * 0.55):int(h * 0.8)].astype(int)
    return int((np.abs(band - HIGHLIGHT).sum(axis=2) < 60).sum())


def test_cues_from_the_script_and_edits(client, talk):
    url = f"/api/clips/{talk['id']}/cues"
    body = client.get(url).json()
    assert body["source"] == "script" and body["scripted"] and body["cues"][0]["text"] == "Merhaba arkadaşlar!"
    assert " ".join(c["text"] for c in body["cues"]) == SCRIPT  # the script as written, with %30
    cues = body["cues"]
    edited = [{**c, "text": c["text"]} for c in cues]
    edited[1] = {**cues[1], "text": "Bugün size"}
    after = client.patch(url, json={"cues": edited}).json()
    assert after["source"] == "edited" and after["cues"][1]["text"] == "Bugün size"
    assert after["cues"][1]["words"][-1]["end"] == pytest.approx(cues[1]["end"])  # retimed within the cue
    assert after["cues"][0] == cues[0]  # untouched cues keep their word timings
    assert client.patch(url, json={"cues": []}).json()["source"] == "script"  # clearing edits restores the script


def test_transcribe_a_recording(client, fake_tts, tmp_path):
    rec = upload(client, "speech", make_wav(tmp_path / "vo.wav", seconds=3, onset=0))
    job = wait_job(client, client.post(f"/api/clips/{rec['id']}/transcribe", json={"language": "tr"}).json())
    assert job["status"] == "done", job
    assert job["outputs"][0]["meta"]["words"][0]["text"] == "kelime1" and fake_tts.app.state.whisper.calls == ["tr"]
    cues = client.get(f"/api/clips/{rec['id']}/cues").json()
    assert cues["source"] == "recognized" and not cues["scripted"]
    assert cues["cues"][0]["text"] == "kelime1 kelime2 kelime3"  # ≤ 24 chars
    silent = upload(client, "driver", make_video(tmp_path / "d.mp4", seconds=1, audio=False))
    assert client.post(f"/api/clips/{silent['id']}/transcribe", json={}).status_code == 422


def test_export_stitches_captions_and_ducked_music(client, character, talk, motion, tmp_path):
    song = upload(client, "music", make_wav(tmp_path / "song.wav", seconds=20, onset=0))
    body = {"character_id": character["id"], "format": "9:16",
            "items": [{"clip_id": talk["id"]}, {"clip_id": motion["id"], "start": 0.5}],
            "music": {"clip_id": song["id"], "volume_db": -12}}
    job = wait_job(client, client.post("/api/exports", json=body).json(), timeout=60)
    assert job["status"] == "done", job
    (out,) = job["outputs"]
    assert out["kind"] == "export" and (out["width"], out["height"]) == FORMATS["9:16"] and out["fps"] == 30
    total = talk["duration"] + motion["duration"] - 0.5
    assert out["duration"] == pytest.approx(total, abs=0.1) and out["has_audio"]
    assert out["caption"] == "9:16 · 2 clips · subtitles · music"

    frames = frames_of(client, out)
    assert len(frames) == pytest.approx(total * 30, abs=2)
    first_cue = client.get(f"/api/clips/{talk['id']}/cues").json()["cues"][0]
    at = int((first_cue["start"] + 0.05) * 30)
    assert highlighted(frames[at]) > 200  # the spoken word is drawn in the highlight colour
    assert highlighted(frames[-5]) < 50  # the motion clip has no speech: no captions (codec noise only)

    data = client.get(out["url"]).content
    path = tmp_path / "out.mp4"
    path.write_bytes(data)
    with av.open(str(path)) as c:
        stats = json.loads(av.filter.loudnorm.stats(f"i={TARGET_LUFS}", c.streams.audio[0]))
    assert float(stats["input_i"]) == pytest.approx(TARGET_LUFS, abs=1.0)  # mastered for social platforms
    assert float(stats["input_tp"]) <= -1.0


def test_duck_gain_follows_speech():
    t = np.arange(2 * AUDIO_RATE) / AUDIO_RATE
    speech = np.where(t < 1, 0.3 * np.sin(2 * np.pi * 200 * t), 0.0).astype(np.float32)
    gain = duck_gain(np.stack([speech, speech], axis=1))[:, 0]
    assert gain[int(0.8 * AUDIO_RATE)] == pytest.approx(10 ** (DUCK_DB / 20), rel=0.05)  # ducked under speech
    assert gain[-1] > 0.88 > gain[int(1.1 * AUDIO_RATE)]  # recovers over the 0.4 s release


def test_export_validation_and_hd(client, fake_comfy, character, talk, motion, tmp_path):
    url = "/api/exports"
    other = client.post("/api/characters", json={"name": "B", "spec": SPEC, "image_id": character["portrait_id"]}).json()
    assert client.post(url, json={"character_id": other["id"], "items": [{"clip_id": talk["id"]}]}).status_code == 404
    voice = upload(client, "voice", make_wav(tmp_path / "v.wav", seconds=4, onset=0))
    assert client.post(url, json={"character_id": character["id"], "items": [{"clip_id": talk["id"]}],
                                  "music": {"clip_id": voice["id"]}}).status_code == 404
    assert client.post(url, json={"character_id": character["id"], "items": [{"clip_id": talk["id"], "start": 99}]}).status_code == 422
    assert client.post(url, json={"character_id": character["id"], "items": []}).status_code == 422

    body = {"character_id": character["id"], "items": [{"clip_id": motion["id"]}], "format": "1:1", "hd": True,
            "subtitles": {"enabled": False}}
    sent = len(fake_comfy.prompts)
    job = wait_job(client, client.post(url, json=body).json(), timeout=60)
    assert job["status"] == "done", job
    assert (job["outputs"][0]["width"], job["outputs"][0]["height"]) == (1080, 1080)
    assert not job["outputs"][0]["has_audio"]  # silent clip, no music: no audio track
    upscales = len(fake_comfy.prompts) - sent
    assert upscales >= 1
    hd_copies = [c for c in client.get(f"/api/characters/{character['id']}/clips").json() if c["meta"].get("hd")]
    assert [c["meta"]["source_clip_id"] for c in hd_copies] == [motion["id"]]
    assert wait_job(client, client.post(url, json=body).json(), timeout=60)["status"] == "done"
    assert len(fake_comfy.prompts) - sent == upscales  # the HD copy is reused
