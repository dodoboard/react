"""Local multilingual TTS server (Chatterbox Multilingual, MIT) for Influencer Studio.

    python server.py            # http://127.0.0.1:7870
    TTS_DEVICE=cpu python server.py

Runs in its own virtualenv: Chatterbox pins torch/transformers versions that would clash with
ComfyUI's. Weights (~3 GB) are downloaded from Hugging Face on first use. Every output carries
Resemble's inaudible Perth watermark, which marks the audio as AI-generated.
"""

from __future__ import annotations

import hashlib
import io
import os
import tempfile
import threading
import wave
from collections import OrderedDict
from typing import Callable, Protocol

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

MAX_TEXT = 600  # Chatterbox stops at 1000 speech tokens (~40 s); callers chunk longer scripts
VOICE_CACHE = 16


class Engine(Protocol):
    sample_rate: int
    device: str
    languages: dict[str, str]

    def synthesize(self, text: str, language: str, voice: bytes | None, exaggeration: float,
                   cfg_weight: float, temperature: float, seed: int | None) -> bytes:
        """Returns mono 16-bit PCM at `sample_rate`."""


class ChatterboxEngine:
    def __init__(self, device: str | None = None):
        import torch
        from chatterbox.mtl_tts import SUPPORTED_LANGUAGES, ChatterboxMultilingualTTS

        self._torch = torch
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = ChatterboxMultilingualTTS.from_pretrained(device=self.device)
        self.sample_rate = self.model.sr
        self.languages = dict(SUPPORTED_LANGUAGES)
        self._default_voice = self.model.conds  # built-in voice from conds.pt
        self._voices: OrderedDict[str, object] = OrderedDict()

    def _conditionals(self, voice: bytes | None, exaggeration: float):
        if voice is None:
            return self._default_voice
        key = hashlib.sha1(voice).hexdigest()
        if key not in self._voices:  # embedding a reference voice is the slow part: do it once
            fd, path = tempfile.mkstemp(suffix=".wav")
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(voice)
                self.model.prepare_conditionals(path, exaggeration=exaggeration)
            finally:
                os.unlink(path)
            self._voices[key] = self.model.conds
            while len(self._voices) > VOICE_CACHE:
                self._voices.popitem(last=False)
        self._voices.move_to_end(key)
        return self._voices[key]

    def synthesize(self, text, language, voice, exaggeration, cfg_weight, temperature, seed):
        self.model.conds = self._conditionals(voice, exaggeration)
        if seed is not None:
            self._torch.manual_seed(seed)
        wav = self.model.generate(text, language_id=language, exaggeration=exaggeration,
                                  cfg_weight=cfg_weight, temperature=temperature)
        samples = (wav.squeeze(0).clamp(-1, 1) * 32767).to(self._torch.int16)
        return samples.cpu().numpy().tobytes()


def to_wav(pcm: bytes, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


def _planned_device() -> str:
    if device := os.environ.get("TTS_DEVICE"):
        return device
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


def create_app(engine_factory: Callable[[], Engine] | None = None,
               planned_device: Callable[[], str] = _planned_device) -> FastAPI:
    factory = engine_factory or (lambda: ChatterboxEngine(os.environ.get("TTS_DEVICE") or None))
    app = FastAPI(title="Influencer Studio TTS")
    lock = threading.Lock()  # one model, one GPU: synthesize sequentially
    state: dict = {"engine": None, "error": None}

    def engine() -> Engine:
        with lock:
            if state["engine"] is None:
                try:
                    state["engine"] = factory()
                    state["error"] = None
                except Exception as e:  # missing weights, CUDA mismatch… reported via /health
                    state["error"] = f"{type(e).__name__}: {e}"
                    raise HTTPException(503, f"TTS model failed to load: {state['error']}") from e
            return state["engine"]

    @app.get("/health")
    def health() -> dict:
        # `device` is known before the model loads, so the studio can free ComfyUI's VRAM first.
        e = state["engine"]
        if "device" not in state:
            state["device"] = planned_device()
        return {"ok": True, "loaded": e is not None, "device": e.device if e else state["device"],
                "languages": e.languages if e else None, "error": state["error"]}

    @app.post("/warmup")
    def warmup() -> dict:
        e = engine()
        return {"loaded": True, "device": e.device, "sample_rate": e.sample_rate}

    @app.post("/synthesize")
    def synthesize(
        text: str = Form(...),
        language: str = Form("tr"),
        exaggeration: float = Form(0.5),
        cfg_weight: float = Form(0.5),
        temperature: float = Form(0.8),
        seed: int | None = Form(None),
        voice: UploadFile | None = File(None),
    ) -> Response:
        text = text.strip()
        if not text or len(text) > MAX_TEXT:
            raise HTTPException(422, f"text must be 1–{MAX_TEXT} characters")
        if not (0.25 <= exaggeration <= 2 and 0 <= cfg_weight <= 1 and 0.05 <= temperature <= 5):
            raise HTTPException(422, "exaggeration, cfg_weight or temperature out of range")
        e = engine()
        if language not in e.languages:
            raise HTTPException(422, f"unsupported language '{language}'")
        reference = voice.file.read() if voice else None
        with lock:
            pcm = e.synthesize(text, language, reference, exaggeration, cfg_weight, temperature, seed)
        return Response(to_wav(pcm, e.sample_rate), media_type="audio/wav")

    return app


if __name__ == "__main__":
    import uvicorn

    host, port = os.environ.get("TTS_HOST", "127.0.0.1"), int(os.environ.get("TTS_PORT", "7870"))
    print(f"Influencer Studio TTS: http://{host}:{port}  (model loads on first request)")
    uvicorn.run(create_app(), host=host, port=port)
