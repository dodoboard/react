"""TTS server tests with a fake engine (no torch or model weights needed).

    pytest tts/test_server.py
"""

import io
import wave

from fastapi.testclient import TestClient

from server import create_app


class FakeEngine:
    sample_rate = 24000
    device = "cpu"
    languages = {"tr": "Turkish", "en": "English"}

    def __init__(self):
        self.calls = []

    def synthesize(self, text, language, voice, exaggeration, cfg_weight, temperature, seed):
        self.calls.append((text, language, voice, exaggeration, cfg_weight, temperature, seed))
        return b"\x01\x00" * (self.sample_rate // 10 * len(text.split()))  # 0.1 s per word


def make_client(factory, device="cpu"):
    return TestClient(create_app(factory, planned_device=lambda: device))


def test_synthesize_returns_wav_and_passes_parameters():
    engine = FakeEngine()
    client = make_client(lambda: engine)
    health = client.get("/health").json()
    assert health["loaded"] is False and health["device"] == "cpu"  # lazy load, but the device is known
    r = client.post("/synthesize", data={"text": "  Merhaba dünya  ", "language": "tr", "exaggeration": 0.7, "seed": 3},
                    files={"voice": ("ref.wav", b"RIFFvoice", "audio/wav")})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
    with wave.open(io.BytesIO(r.content)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 24000)
        assert w.getnframes() == 4800
    assert engine.calls == [("Merhaba dünya", "tr", b"RIFFvoice", 0.7, 0.5, 0.8, 3)]
    health = client.get("/health").json()
    assert health["loaded"] and health["device"] == "cpu" and health["languages"]["tr"] == "Turkish"


def test_default_voice_and_validation():
    engine = FakeEngine()
    client = make_client(lambda: engine)
    assert client.post("/synthesize", data={"text": "Selam"}).status_code == 200
    assert engine.calls[-1][2] is None and engine.calls[-1][1] == "tr"
    assert client.post("/synthesize", data={"text": "   "}).status_code == 422
    assert client.post("/synthesize", data={"text": "x" * 601}).status_code == 422
    assert client.post("/synthesize", data={"text": "hi", "language": "xx"}).status_code == 422
    assert client.post("/synthesize", data={"text": "hi", "exaggeration": 9}).status_code == 422


def test_load_failure_is_reported_and_retried():
    attempts = []

    def factory():
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("CUDA error: no kernel image is available")
        return FakeEngine()

    client = make_client(factory)
    r = client.post("/synthesize", data={"text": "Merhaba"})
    assert r.status_code == 503 and "no kernel image" in r.json()["detail"]
    assert "no kernel image" in client.get("/health").json()["error"]
    assert client.post("/warmup").json()["loaded"] is True  # next request retries the load
    assert client.get("/health").json()["error"] is None
