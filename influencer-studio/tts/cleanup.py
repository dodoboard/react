"""Speech clean-up: trim leading/trailing silence and even out loudness across chunks.

Every chunk of a script is synthesized separately, so without this the level jumps between
sentences and silence piles up at the joins (the studio inserts its own, punctuation-aware pauses).
"""

from __future__ import annotations

import io
import wave

import numpy as np

TARGET_LUFS = -20.0  # speech level per chunk; the final export is mastered to -14 LUFS
PEAK_DBFS = -1.0
KEEP_SECONDS = 0.06  # silence kept at each end so consonants are not clipped
FRAME_SECONDS = 0.02


def trim_silence(x: np.ndarray, sr: int, floor_db: float = -45.0, below_peak_db: float = 40.0) -> np.ndarray:
    """Cut quiet frames from both ends. Quiet = under `floor_db` or `below_peak_db` under the loudest frame."""
    frame = max(1, int(sr * FRAME_SECONDS))
    n = len(x) // frame
    if n == 0:
        return x
    rms = np.sqrt(np.mean(x[: n * frame].reshape(n, frame) ** 2, axis=1) + 1e-12)
    level = 20 * np.log10(rms)
    loud = np.flatnonzero(level > max(floor_db, level.max() - below_peak_db))
    if loud.size == 0:
        return x
    keep = int(sr * KEEP_SECONDS)
    return x[max(0, loud[0] * frame - keep): min(len(x), (loud[-1] + 1) * frame + keep)]


def loudness(x: np.ndarray, sr: int) -> float:
    """Integrated loudness (ITU-R BS.1770); RMS for clips shorter than one 400 ms block."""
    if len(x) >= int(0.4 * sr):
        import pyloudnorm

        value = pyloudnorm.Meter(sr).integrated_loudness(x)
        if np.isfinite(value):
            return float(value)
    return float(20 * np.log10(np.sqrt(np.mean(x**2)) + 1e-12))


def normalize(x: np.ndarray, sr: int, target: float = TARGET_LUFS, peak_db: float = PEAK_DBFS) -> np.ndarray:
    if not len(x) or not np.any(x):
        return x
    y = x * 10 ** ((target - loudness(x, sr)) / 20)
    peak, limit = np.abs(y).max(), 10 ** (peak_db / 20)
    return y * (limit / peak) if peak > limit else y


def clean_speech(pcm: bytes, sr: int) -> bytes:
    """Mono 16-bit PCM in and out."""
    x = np.frombuffer(pcm, dtype=np.int16).astype(np.float64) / 32768
    y = normalize(trim_silence(x, sr), sr)
    return (np.clip(y, -1, 1) * 32767).astype(np.int16).tobytes()


def clean_reference(data: bytes) -> bytes:
    """A voice sample (16-bit WAV, any channel count) → trimmed, normalized mono WAV."""
    try:
        with wave.open(io.BytesIO(data)) as w:
            channels, width, sr = w.getnchannels(), w.getsampwidth(), w.getframerate()
            frames = w.readframes(w.getnframes())
    except (wave.Error, EOFError):
        return data  # not a plain WAV: let the model's own loader handle it
    if width != 2:
        return data
    x = np.frombuffer(frames, dtype=np.int16).astype(np.float64).reshape(-1, channels).mean(axis=1) / 32768
    y = normalize(trim_silence(x, sr), sr)
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(y, -1, 1) * 32767).astype(np.int16).tobytes())
    return out.getvalue()
