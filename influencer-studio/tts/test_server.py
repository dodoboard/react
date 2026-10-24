"""TTS server tests with a fake engine (no torch or model weights needed).

    pytest tts/test_server.py
"""

import io
import math
import struct
import wave

import numpy as np
import pytest
from fastapi.testclient import TestClient

from cleanup import TARGET_LUFS, clean_reference, clean_speech, loudness
from server import ChatterboxEngine, create_app


class FakeEngine:
    sample_rate = 24000
    device = "cpu"
    languages = {"tr": "Turkish", "en": "English"}

    def __init__(self):
        self.calls = []

    def synthesize(self, text, language, voice, exaggeration, cfg_weight, temperature, seed):
        self.calls.append((text, language, voice, exaggeration, cfg_weight, temperature, seed))
        return b"\x01\x00" * (self.sample_rate // 10 * len(text.split()))  # 0.1 s per word


def make_client(factory, device="cpu", postprocess=False):
    return TestClient(create_app(factory, planned_device=lambda: device, postprocess=postprocess))


def tone(seconds, amplitude, sr=24000, before=0.0, after=0.0):
    """Silence, a 220 Hz tone, silence: mono 16-bit PCM."""
    n0, n1, n2 = (int(t * sr) for t in (before, seconds, after))
    body = (int(amplitude * 32767 * math.sin(2 * math.pi * 220 * i / sr)) for i in range(n1))
    return b"\x00\x00" * n0 + b"".join(struct.pack("<h", v) for v in body) + b"\x00\x00" * n2


def pcm_array(pcm):
    return np.frombuffer(pcm, dtype=np.int16).astype(np.float64) / 32768


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


def test_cleanup_trims_silence_and_evens_out_loudness():
    quiet = clean_speech(tone(1.0, 0.02, before=0.5, after=0.7), 24000)
    loud = clean_speech(tone(1.0, 0.6, before=0.1, after=0.1), 24000)
    for pcm in (quiet, loud):
        assert len(pcm) / 2 / 24000 == pytest.approx(1.0 + 2 * 0.06, abs=0.03)
        assert loudness(pcm_array(pcm), 24000) == pytest.approx(TARGET_LUFS, abs=0.5)
    assert clean_speech(b"\x00\x00" * 2400, 24000) == b"\x00\x00" * 2400  # silence stays silence


def test_reference_becomes_trimmed_mono():
    mono = tone(2.0, 0.3, sr=44100, before=1.0)
    stereo = b"".join(mono[i:i + 2] * 2 for i in range(0, len(mono), 2))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(stereo)
    with wave.open(io.BytesIO(clean_reference(buf.getvalue()))) as w:
        assert w.getnchannels() == 1 and w.getframerate() == 44100
        assert w.getnframes() / 44100 == pytest.approx(2.0 + 0.06, abs=0.03)  # leading second cut
    assert clean_reference(b"not a wav") == b"not a wav"


class ToneEngine(FakeEngine):
    def __init__(self):
        super().__init__()
        self.offloads = 0

    def synthesize(self, text, *args):
        super().synthesize(text, *args)
        return tone(0.05 * len(text), 0.1, before=0.4, after=0.4)

    def offload(self):
        self.offloads += 1
        return True


def test_server_cleans_output_and_offloads():
    engine = ToneEngine()
    client = make_client(lambda: engine, postprocess=True)
    assert client.post("/offload").json() == {"offloaded": False}  # nothing loaded yet
    r = client.post("/synthesize", data={"text": "Merhaba dünya"})
    with wave.open(io.BytesIO(r.content)) as w:
        assert w.getnframes() / 24000 == pytest.approx(0.65 + 0.12, abs=0.03)  # padding trimmed
    assert client.post("/offload").json() == {"offloaded": True} and engine.offloads == 1


class Moves:
    def __init__(self, log, name):
        self.log, self.name = log, name

    def to(self, device=None, **kw):
        self.log.append((self.name, device or kw["device"]))
        return self


def test_chatterbox_engine_offload_moves_weights_and_voices():
    log = []
    engine = ChatterboxEngine.__new__(ChatterboxEngine)
    engine._torch = type("T", (), {"cuda": type("C", (), {"is_available": staticmethod(lambda: False)})})
    engine.device, engine._resident = "cuda", "cuda"
    engine.model = type("M", (), {})()
    engine.model.t3, engine.model.s3gen, engine.model.ve = Moves(log, "t3"), Moves(log, "s3gen"), Moves(log, "ve")
    engine._default_voice = Moves(log, "default")
    engine._voices = {"abc": Moves(log, "voice")}
    assert engine.offload() is True and engine.model.device == "cpu"
    assert sorted(log) == sorted([(n, "cpu") for n in ("t3", "s3gen", "ve", "default", "voice")])
    assert engine.offload() is False  # already in RAM
    log.clear()
    engine._move(engine.device)  # what synthesize() does first
    assert len(log) == 5 and {d for _, d in log} == {"cuda"} and engine._resident == "cuda"


class FakeWhisper:
    def __init__(self):
        self.calls = []

    def transcribe(self, audio, language):
        self.calls.append((audio[:4], language))
        return {"language": language or "tr", "words": [{"text": "Merhaba", "start": 0.1, "end": 0.6}]}


def test_transcribe_loads_once_and_reports_failures():
    loads = []

    def factory():
        loads.append(1)
        return FakeWhisper()

    client = TestClient(create_app(lambda: FakeEngine(), transcriber_factory=factory, postprocess=False))
    for _ in range(2):
        r = client.post("/transcribe", data={"language": "tr"}, files={"audio": ("a.wav", b"RIFFdata", "audio/wav")})
        assert r.status_code == 200 and r.json()["words"][0]["text"] == "Merhaba"
    assert len(loads) == 1

    def broken():
        raise RuntimeError("model not downloaded")

    client = TestClient(create_app(lambda: FakeEngine(), transcriber_factory=broken, postprocess=False))
    r = client.post("/transcribe", files={"audio": ("a.wav", b"RIFF", "audio/wav")})
    assert r.status_code == 503 and "model not downloaded" in r.json()["detail"]


def test_whisper_transcriber_matches_faster_whisper_api():
    fw = pytest.importorskip("faster_whisper")
    from faster_whisper.utils import _MODELS

    assert "large-v3-turbo" in _MODELS  # the name WhisperTranscriber asks for
    import inspect

    params = inspect.signature(fw.WhisperModel.transcribe).parameters
    assert {"language", "word_timestamps", "vad_filter", "condition_on_previous_text"} <= set(params)
