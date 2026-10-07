"""Synthetic media for tests, written with PyAV (no system FFmpeg needed)."""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

import av
from PIL import Image, ImageDraw

SQUARE_SPEED = 200  # px per second: the square's x position encodes the source time


def make_video(path: Path, *, seconds: float = 3.0, fps: int = 30, size: tuple[int, int] = (640, 360),
               audio: bool = True) -> Path:
    """A white square moving right at SQUARE_SPEED px/s on black, with an optional 440 Hz tone."""
    w, h = size
    with av.open(str(path), "w", format="mp4") as out:
        video = out.add_stream("libx264", rate=fps)
        video.width, video.height, video.pix_fmt = w, h, "yuv420p"
        tone = out.add_stream("aac", rate=44100, layout="stereo") if audio else None
        for i in range(round(seconds * fps)):
            img = Image.new("RGB", (w, h))
            x = int(i / fps * SQUARE_SPEED)
            ImageDraw.Draw(img).rectangle([x, h // 2 - 10, x + 20, h // 2 + 10], fill=(255, 255, 255))
            for packet in video.encode(av.VideoFrame.from_image(img)):
                out.mux(packet)
        for packet in video.encode():
            out.mux(packet)
        if tone is not None:
            total = int(seconds * 44100)
            for start in range(0, total, 1024):
                n = min(1024, total - start)
                frame = av.AudioFrame(format="s16", layout="stereo", samples=n)
                pcm = b"".join(struct.pack("<hh", s, s) for s in
                               (int(8000 * math.sin(2 * math.pi * 440 * (start + k) / 44100)) for k in range(n)))
                frame.planes[0].update(pcm + bytes(frame.planes[0].buffer_size - len(pcm)))
                frame.sample_rate, frame.pts = 44100, start
                for packet in tone.encode(frame):
                    out.mux(packet)
            for packet in tone.encode():
                out.mux(packet)
    return path


def make_wav(path: Path, *, seconds: float, onset: float) -> Path:
    """Silence until `onset`, then a tone: lets tests check where a cut starts."""
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(b"".join(
            struct.pack("<hh", v, v)
            for v in (int(9000 * math.sin(i * 0.07)) if i >= onset * 44100 else 0 for i in range(int(seconds * 44100)))
        ))
    return path


def wav_onset(path: Path, threshold: int = 1000) -> float:
    with wave.open(str(path)) as w:
        data = w.readframes(w.getnframes())
    left = struct.unpack(f"<{len(data) // 2}h", data)[0::2]
    return next(i for i, v in enumerate(left) if abs(v) > threshold) / 44100


def square_time(frame: av.VideoFrame, src_size: tuple[int, int], out_size: tuple[int, int]) -> float:
    """Source time shown by an output frame, read back from the square's x position (center-crop aware)."""
    img = frame.to_image().convert("L")
    w, h = out_size
    row = [img.getpixel((x, h // 2)) for x in range(w)]
    x = next(i for i, v in enumerate(row) if v > 128)
    scale = max(w / src_size[0], h / src_size[1])
    crop = (src_size[0] * scale - w) / 2
    return (x + crop) / scale / SQUARE_SPEED


def make_recording(path: Path, *, seconds: float) -> Path:
    """Opus WebM without a duration header, like Chrome's MediaRecorder writes."""
    rate = 48000
    with av.open(str(path), "w", format="webm", options={"live": "1"}) as out:
        stream = out.add_stream("libopus", rate=rate, layout="mono")
        for start in range(0, int(seconds * rate), 960):
            frame = av.AudioFrame(format="s16", layout="mono", samples=960)
            pcm = b"".join(struct.pack("<h", int(8000 * math.sin(i * 0.06))) for i in range(start, start + 960))
            frame.planes[0].update(pcm + bytes(frame.planes[0].buffer_size - len(pcm)))
            frame.sample_rate, frame.pts = rate, start
            for packet in stream.encode(frame):
                out.mux(packet)
        for packet in stream.encode():
            out.mux(packet)
    return path
