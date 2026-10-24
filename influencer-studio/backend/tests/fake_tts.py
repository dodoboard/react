"""The real TTS server (tts/server.py) with a fake engine: a tone whose length follows the text.

    python -m tests.fake_tts --port 7870
"""

from __future__ import annotations

import argparse
import io
import math
import struct
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tts"))
from server import create_app  # noqa: E402

SECONDS_PER_CHAR = 0.06


class ToneEngine:
    sample_rate = 24000
    device = "cpu"
    languages = {"tr": "Turkish", "en": "English", "de": "German"}

    def __init__(self):
        self.calls: list[dict] = []
        self.offloads = 0

    def synthesize(self, text, language, voice, exaggeration, cfg_weight, temperature, seed):
        self.calls.append({"text": text, "language": language, "voice": voice, "seed": seed})
        n = int(len(text) * SECONDS_PER_CHAR * self.sample_rate)
        return b"".join(struct.pack("<h", int(7000 * math.sin(i * 0.05))) for i in range(n))

    def offload(self):
        self.offloads += 1
        return self.device != "cpu"


class FakeWhisper:
    """Recognizes one word every half second of audio: "kelime1", "kelime2"…, sentences of four."""

    def __init__(self):
        self.calls: list[str | None] = []

    def transcribe(self, audio: bytes, language: str | None) -> dict:
        self.calls.append(language)
        with wave.open(io.BytesIO(audio)) as w:
            seconds = w.getnframes() / w.getframerate()
        words = [{"text": f"kelime{i + 1}" + ("." if i % 4 == 3 else ""), "start": i * 0.5, "end": i * 0.5 + 0.4}
                 for i in range(int(seconds / 0.5))]
        return {"language": language or "tr", "words": words}


def create_fake_tts(engine: ToneEngine | None = None):
    engine = engine or ToneEngine()
    # no clean-up: output lengths stay exact (cleanup.py is tested in tts/test_server.py)
    whisper = FakeWhisper()
    app = create_app(lambda: engine, planned_device=lambda: engine.device, postprocess=False,
                     transcriber_factory=lambda: whisper)
    app.state.engine, app.state.whisper = engine, whisper
    return app


if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=7870)
    uvicorn.run(create_fake_tts(), host="127.0.0.1", port=parser.parse_args().port)
