"""The real TTS server (tts/server.py) with a fake engine: a tone whose length follows the text.

    python -m tests.fake_tts --port 7870
"""

from __future__ import annotations

import argparse
import math
import struct
import sys
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

    def synthesize(self, text, language, voice, exaggeration, cfg_weight, temperature, seed):
        self.calls.append({"text": text, "language": language, "voice": voice, "seed": seed})
        n = int(len(text) * SECONDS_PER_CHAR * self.sample_rate)
        return b"".join(struct.pack("<h", int(7000 * math.sin(i * 0.05))) for i in range(n))


def create_fake_tts(engine: ToneEngine | None = None):
    engine = engine or ToneEngine()
    app = create_app(lambda: engine, planned_device=lambda: engine.device)
    app.state.engine = engine
    return app


if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=7870)
    uvicorn.run(create_fake_tts(), host="127.0.0.1", port=parser.parse_args().port)
