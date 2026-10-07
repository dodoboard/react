import io
import wave

import av
import pytest

from studio.video import TALK_FPS, talk_windows
from studio.voice import SENTENCE_PAUSE, join_wavs
from tests.conftest import wait_job
from tests.fake_tts import SECONDS_PER_CHAR
from tests.media_fixtures import make_recording, make_wav

SPEC = {"age": 29, "selections": {"gender": {"values": ["woman"]}, "origin": {"values": ["turkish"]}}}


@pytest.fixture
def character(client):
    job = wait_job(client, client.post("/api/builder/generate", json={"spec": SPEC, "count": 1}).json())
    return client.post("/api/characters", json={"name": "Deniz", "spec": SPEC, "image_id": job["outputs"][0]["id"]}).json()


def upload(client, kind, path):
    with open(path, "rb") as f:
        return client.post(f"/api/motion/uploads?kind={kind}", files={"file": (path.name, f)})


def wav_seconds(data: bytes) -> float:
    with wave.open(io.BytesIO(data)) as w:
        return w.getnframes() / w.getframerate()


def test_schema_and_health(client, fake_comfy):
    schema = client.get("/api/voice/schema").json()
    assert schema["languages"][0] == {"id": "tr", "label": "Türkçe"} and schema["limits"]["talk_seconds"] == 30
    health = client.get("/api/voice/health").json()
    assert health["tts"]["ok"] and health["comfy"] and health["missing_models"] == []
    fake_comfy.app.state.models = {}
    assert {m["folder"] for m in client.get("/api/voice/health").json()["missing_models"]} >= {"model_patches", "audio_encoders"}


def test_voice_upload_and_character_assignment(client, character, tmp_path):
    assert upload(client, "voice", make_wav(tmp_path / "short.wav", seconds=2, onset=0)).status_code == 422  # < 3 s
    voice = upload(client, "voice", make_wav(tmp_path / "me.wav", seconds=6, onset=0)).json()
    assert voice["kind"] == "voice"
    url = f"/api/characters/{character['id']}"
    assert client.patch(url, json={"voice_id": voice["id"]}).json()["voice_id"] == voice["id"]
    assert client.patch(url, json={"voice_id": "nope"}).status_code == 422
    assert client.patch(url, json={"voice_id": ""}).json()["voice_id"] is None

    mic = upload(client, "voice", make_recording(tmp_path / "mic.webm", seconds=5)).json()  # browser recording
    assert mic["kind"] == "voice" and mic["duration"] == pytest.approx(5, abs=0.05)
    client.patch(url, json={"voice_id": mic["id"]})
    client.delete(f"/api/clips/{mic['id']}")
    assert client.get(url).json()["voice_id"] is None  # deleting a voice unassigns it


def test_turkish_speech_is_normalized_chunked_and_joined(client, fake_tts, character, tmp_path):
    voice = upload(client, "voice", make_wav(tmp_path / "me.wav", seconds=6, onset=0)).json()
    client.patch(f"/api/characters/{character['id']}", json={"voice_id": voice["id"]})
    script = "Bugün %20 indirim var! " + "Yeni koleksiyonu 2026'da tanıtıyoruz ve çok heyecanlıyım. " * 5
    job = wait_job(client, client.post("/api/voice/speak", json={
        "text": script, "character_id": character["id"], "seed": 7, "exaggeration": 0.8}).json())
    assert job["status"] == "done", job
    (clip,) = job["outputs"]
    assert clip["kind"] == "speech" and clip["ext"] == "wav" and clip["character_id"] == character["id"]

    calls = fake_tts.calls
    assert len(calls) > 1 and all(len(c["text"]) <= 250 for c in calls)  # chunked
    assert calls[0]["text"].startswith("Bugün yüzde yirmi indirim var!")
    assert "iki bin yirmi altıda" in calls[1]["text"] and "%" not in "".join(c["text"] for c in calls)
    assert [c["seed"] for c in calls] == list(range(7, 7 + len(calls)))
    assert all(c["voice"] and c["voice"][:4] == b"RIFF" for c in calls)  # the character's voice, as WAV
    expected = sum(len(c["text"]) for c in calls) * SECONDS_PER_CHAR + SENTENCE_PAUSE * (len(calls) - 1)
    assert wav_seconds(client.get(clip["url"]).content) == pytest.approx(expected, abs=0.05)


def test_other_languages_are_not_normalized(client, fake_tts):
    job = wait_job(client, client.post("/api/voice/speak", json={"text": "Save 20% today", "language": "en"}).json())
    assert job["status"] == "done" and fake_tts.calls[-1]["text"] == "Save 20% today"
    assert fake_tts.calls[-1]["voice"] is None  # built-in voice when none is set
    assert client.post("/api/voice/speak", json={"text": "   "}).status_code == 422
    assert client.post("/api/voice/speak", json={"text": "hi", "language": "xx"}).status_code == 422


def test_talk_from_script(client, fake_comfy, fake_tts, character):
    script = "Merhaba arkadaşlar, bugün size en sevdiğim kahve tarifini göstereceğim."
    job = wait_job(client, client.post(f"/api/characters/{character['id']}/talk", json={
        "source_image_id": character["portrait_id"], "text": script, "prompt": "smiling, cozy kitchen",
        "orientation": "portrait"}).json())
    assert job["status"] == "done", job
    (talk,) = job["outputs"]
    assert talk["kind"] == "talk" and talk["has_audio"] and (talk["width"], talk["height"]) == (480, 832)

    clips = client.get(f"/api/characters/{character['id']}/clips").json()
    speech = next(c for c in clips if c["kind"] == "speech")  # the synthesized track is kept too
    frames = -(-int(speech["duration"] * 1000) * TALK_FPS // 1000)
    graph = fake_comfy.prompts[-1]
    windows = [n["inputs"] for n in graph.values() if n["class_type"] == "WanInfiniteTalkToVideo"]
    assert len(windows) == talk_windows(frames)[1] >= 2
    assert all(w["mode"] == "single_speaker" for w in windows) and "previous_frames" in windows[1]
    text = next(n["inputs"]["text"] for n in graph.values() if n["class_type"] == "CLIPTextEncode")
    assert "talking to the camera" in text and "Smiling, cozy kitchen." in text
    with av.open(io.BytesIO(client.get(talk["url"]).content)) as c:
        assert [s.type for s in c.streams] == ["video", "audio"]
    assert fake_comfy.app.state.frees == 0  # TTS on CPU: no need to unload ComfyUI


def test_gpu_tts_unloads_comfyui_first(client, fake_comfy, fake_tts):
    fake_tts.app.state.engine.device = "cuda"
    job = wait_job(client, client.post("/api/voice/speak", json={"text": "Selam!"}).json())
    assert job["status"] == "done" and fake_comfy.app.state.frees == 1


def test_talk_from_uploaded_speech_and_validation(client, fake_comfy, fake_tts, character, tmp_path):
    speech = upload(client, "speech", make_wav(tmp_path / "vo.wav", seconds=2, onset=0)).json()
    url = f"/api/characters/{character['id']}/talk"
    body = {"source_image_id": character["portrait_id"], "speech_id": speech["id"]}
    job = wait_job(client, client.post(url, json=body).json())
    assert job["status"] == "done" and not fake_tts.calls  # no TTS when a recording is given
    (window,) = [n["inputs"] for n in fake_comfy.prompts[-1].values() if n["class_type"] == "WanInfiniteTalkToVideo"]
    assert window["length"] == 53  # 2 s × 25 fps = 50 frames → one 53-frame window

    assert client.post(url, json={"source_image_id": character["portrait_id"]}).status_code == 422
    assert client.post(url, json=body | {"text": "hem metin hem ses"}).status_code == 422
    long = upload(client, "speech", make_wav(tmp_path / "long.wav", seconds=32, onset=0)).json()
    assert client.post(url, json=body | {"speech_id": long["id"]}).status_code == 422
    assert client.post(url, json=body | {"resolution": "720p"}).status_code == 422


def test_tts_outage_is_reported_on_the_job(client, character):
    client.app.state.voice.tts._http.base_url = "http://127.0.0.1:9"  # nothing listens there
    job = wait_job(client, client.post("/api/voice/speak", json={"text": "Merhaba"}).json())
    assert job["status"] == "error" and "TTS server is not running" in job["error"]
    assert client.get("/api/voice/health").json()["tts"]["ok"] is False


def test_join_wavs_inserts_pauses():
    def tone(seconds, rate=24000):
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(b"\x10\x00" * int(seconds * rate))
        return buf.getvalue()

    assert wav_seconds(join_wavs([tone(1), tone(0.5), tone(0.25)], 0.2)) == pytest.approx(2.15)
    with pytest.raises(ValueError):
        join_wavs([tone(1), tone(1, rate=16000)], 0.2)
