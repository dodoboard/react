import io
import wave

import pytest
from PIL import Image

from studio.face import Face
from studio.voice import parse_dialog
from tests.conftest import wait_job
from tests.media_fixtures import make_wav

WOMAN = {"age": 26, "selections": {"gender": {"values": ["woman"]}}}
MAN = {"age": 31, "selections": {"gender": {"values": ["man"]}}}


def make(client, name, spec):
    job = wait_job(client, client.post("/api/builder/generate", json={"spec": spec, "count": 1}).json())
    return client.post("/api/characters", json={"name": name, "spec": spec, "image_id": job["outputs"][0]["id"]}).json()


def by_type(graph, class_type):
    return [n["inputs"] for n in graph.values() if n["class_type"] == class_type]


def test_parse_dialog_turns():
    turns = parse_dialog("A: Merhaba!\nDeniz: Selam, nasılsın?\n  devam eden satır\n\nb: İyiyim.", {"a": "Ela", "b": "Deniz"})
    assert turns == [("a", "Merhaba!"), ("b", "Selam, nasılsın? devam eden satır"), ("b", "İyiyim.")]
    with pytest.raises(ValueError):
        parse_dialog("merhaba", {"a": "Ela", "b": "Deniz"})


def test_dialog_video_with_two_voices_and_masks(client, fake_comfy, fake_tts, tmp_path):
    ela, deniz = make(client, "Ela", WOMAN), make(client, "Deniz", MAN)
    with open(make_wav(tmp_path / "v.wav", seconds=6, onset=0), "rb") as f:
        voice = client.post("/api/motion/uploads?kind=voice", files={"file": ("v.wav", f)}).json()
    client.patch(f"/api/characters/{deniz['id']}", json={"voice_id": voice["id"]})
    # two faces in the frame: speaker regions split between them
    portrait = client.get(f"/api/characters/{ela['id']}").json()["images"][0]
    # face centers at 25 % and 60 % of the width
    client.app.state.voice.detector = lambda img: [Face(img.width * 0.25 - 40, 100, 80, 80),
                                                   Face(img.width * 0.60 - 40, 100, 80, 80)]
    job = wait_job(client, client.post(f"/api/characters/{ela['id']}/dialog", json={
        "partner_id": deniz["id"], "source_image_id": portrait["id"], "orientation": "landscape",
        "text": "A: Merhaba Deniz, bugün ne çekiyoruz?\nB: Yeni koleksiyonu tanıtacağız.\nA: Harika!"}).json())
    assert job["status"] == "done", job
    (clip,) = job["outputs"]
    assert clip["kind"] == "talk" and clip["meta"]["dialog"] and clip["meta"]["partner_id"] == deniz["id"]
    assert [s["speaker"] for s in clip["meta"]["segments"]] == ["Ela", "Deniz", "Ela"]

    calls = fake_tts.calls
    assert [c["voice"] is None for c in calls] == [True, False, True]  # Deniz speaks with his own voice
    graph = fake_comfy.prompts[-1]
    (window, *_) = by_type(graph, "WanInfiniteTalkToVideo")
    assert window["mode"] == "two_speakers" and {"mode.audio_encoder_output_2", "mode.mask_1", "mode.mask_2"} <= window.keys()
    assert len(by_type(graph, "ImageToMask")) == 2 and len(by_type(graph, "AudioEncoderEncode")) == 2

    uploads = fake_comfy_inputs(fake_comfy)
    mask1 = Image.open(io.BytesIO(uploads[next(k for k in uploads if k.endswith("_mask1.png"))])).convert("L")
    split = next(x for x in range(mask1.width) if mask1.getpixel((x, 10)) == 0)
    assert abs(split - round(mask1.width * 0.425)) <= 3  # midway between the two face centers
    track1 = uploads[next(k for k in uploads if k.endswith("_speaker1.wav"))]
    mix = uploads[next(k for k in uploads if k.endswith("_mix.wav"))]
    with wave.open(io.BytesIO(track1)) as a, wave.open(io.BytesIO(mix)) as m:
        assert a.getnframes() == m.getnframes()  # each speaker's track spans the whole conversation
        second_turn = clip["meta"]["segments"][1]
        a.setpos(int((second_turn["start"] + 0.1) * a.getframerate()))
        assert not any(a.readframes(1000))  # Ela is silent while Deniz talks


def fake_comfy_inputs(fake_comfy):
    return fake_comfy.app.state.inputs


def test_dialog_validation(client):
    ela, deniz = make(client, "Ela", WOMAN), make(client, "Deniz", MAN)
    url = f"/api/characters/{ela['id']}/dialog"
    body = {"partner_id": deniz["id"], "source_image_id": ela["portrait_id"], "text": "A: Selam"}
    assert client.post(url, json=body | {"partner_id": ela["id"]}).status_code == 404
    assert client.post(url, json=body | {"text": ""}).status_code == 422
    assert client.post(url, json=body | {"text": "selam"}).status_code == 422
    other = make(client, "Su", WOMAN)
    assert client.post(url, json=body | {"source_image_id": other["portrait_id"]}).status_code == 422
