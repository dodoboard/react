"""TTS providers. All return audio file + word-level timings."""
from __future__ import annotations

import asyncio
import base64
import gc
from dataclasses import dataclass
from pathlib import Path

import httpx

from ..config import config, paths
from ..media import probe_duration, run_ffmpeg

EL_BASE = "https://api.elevenlabs.io"


@dataclass
class Word:
    text: str
    start: float
    end: float


@dataclass
class TTSResult:
    audio: Path
    words: list[Word]
    duration: float


class TTSError(RuntimeError):
    pass


def words_from_chars(chars: list[str], starts: list[float], ends: list[float]) -> list[Word]:
    words: list[Word] = []
    buf, s, e = "", 0.0, 0.0
    for ch, cs, ce in zip(chars, starts, ends):
        if ch.isspace():
            if buf:
                words.append(Word(buf, s, e))
                buf = ""
            continue
        if not buf:
            s = cs
        buf += ch
        e = ce
    if buf:
        words.append(Word(buf, s, e))
    return words


def estimate_words(text: str, duration: float) -> list[Word]:
    """Fallback alignment: distribute duration proportional to word length."""
    toks = text.split()
    total = sum(len(t) + 1 for t in toks) or 1
    t, out = 0.0, []
    for tok in toks:
        d = duration * (len(tok) + 1) / total
        out.append(Word(tok, t, t + d * 0.92))
        t += d
    return out


# ---------- ElevenLabs ----------
def _el_headers() -> dict:
    key = config.get().elevenlabs_api_key
    if not key:
        raise TTSError("ElevenLabs API anahtarı ayarlanmamış (Ayarlar).")
    return {"xi-api-key": key}


DEFAULT_VOICE = {"stability": 0.45, "similarity_boost": 0.8, "style": 0.35, "use_speaker_boost": True}


async def elevenlabs(text: str, out: Path, voice_id: str | None = None, settings: dict | None = None,
                     lang: str = "tr") -> TTSResult:
    cfg = config.get()
    vid = voice_id or cfg.elevenlabs_voice_id
    vs = DEFAULT_VOICE | {k: v for k, v in (settings or {}).items() if k in ("stability", "similarity_boost", "style", "speed", "use_speaker_boost")}
    body = {"text": text, "model_id": cfg.elevenlabs_model, "voice_settings": vs}
    async with httpx.AsyncClient(base_url=EL_BASE, timeout=300) as c:
        r = await c.post(f"/v1/text-to-speech/{vid}/with-timestamps", params={"output_format": "mp3_44100_128"},
                         headers=_el_headers(), json=body)
        if r.status_code in (400, 422) and cfg.elevenlabs_model.startswith("eleven_v3"):
            # timestamps may not be offered for every model: plain synthesis + local alignment
            r2 = await c.post(f"/v1/text-to-speech/{vid}", params={"output_format": "mp3_44100_128"},
                              headers=_el_headers(), json=body)
            if r2.status_code >= 400:
                raise TTSError(f"ElevenLabs {r2.status_code}: {r2.text[:300]}")
            out.write_bytes(r2.content)
            dur = await probe_duration(out)
            return TTSResult(out, await align_or_estimate(out, text, dur, lang), dur)
    if r.status_code >= 400:
        raise TTSError(f"ElevenLabs {r.status_code}: {r.text[:300]}")
    j = r.json()
    out.write_bytes(base64.b64decode(j["audio_base64"]))
    al = j.get("alignment") or j.get("normalized_alignment")
    dur = await probe_duration(out)
    words = (words_from_chars(al["characters"], al["character_start_times_seconds"], al["character_end_times_seconds"])
             if al else estimate_words(text, dur))
    return TTSResult(out, words, dur)


async def align_or_estimate(audio: Path, text: str, dur: float, lang: str) -> list[Word]:
    try:
        words = await asyncio.to_thread(_whisper_words_sync, audio, lang)
        src = text.split()
        return [Word(t, w.start, w.end) for t, w in zip(src, words)] if len(words) == len(src) else words
    except Exception:
        return estimate_words(text, dur)


async def elevenlabs_voices() -> list[dict]:
    async with httpx.AsyncClient(base_url=EL_BASE, timeout=15) as c:
        r = await c.get("/v1/voices", headers=_el_headers())
    r.raise_for_status()
    return [{"id": v["voice_id"], "name": v["name"], "preview_url": v.get("preview_url"),
             "labels": v.get("labels") or {}, "category": v.get("category")} for v in r.json()["voices"]]


async def elevenlabs_quota() -> dict:
    async with httpx.AsyncClient(base_url=EL_BASE, timeout=10) as c:
        r = await c.get("/v1/user/subscription", headers=_el_headers())
    r.raise_for_status()
    j = r.json()
    return {"used": j.get("character_count", 0), "limit": j.get("character_limit", 0), "tier": j.get("tier"),
            "reset_unix": j.get("next_character_count_reset_unix")}


# ---------- Chatterbox (local, MIT) + faster-whisper alignment ----------
_LOCK = asyncio.Lock()


def _chatterbox_sync(text: str, out: Path, lang: str, ref: Path | None, exaggeration: float = 0.6,
                     cfg_weight: float = 0.4) -> None:
    try:
        import torch
        import torchaudio
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    except ImportError as e:
        raise TTSError("Lokal TTS kurulu değil: pip install -r requirements-local-tts.txt") from e
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = ChatterboxMultilingualTTS.from_pretrained(device=device)
    kw = {"audio_prompt_path": str(ref)} if ref else {}
    wav = model.generate(text, language_id=lang, exaggeration=exaggeration, cfg_weight=cfg_weight, **kw)
    wav_path = out.with_suffix(".wav")
    torchaudio.save(str(wav_path), wav, model.sr)
    del model
    gc.collect()
    if device == "cuda":
        torch.cuda.empty_cache()


def _whisper_words_sync(audio: Path, lang: str) -> list[Word]:
    from faster_whisper import WhisperModel
    import torch

    cuda = torch.cuda.is_available()
    m = WhisperModel(config.get().whisper_model, device="cuda" if cuda else "cpu", compute_type="float16" if cuda else "int8")
    segs, _ = m.transcribe(str(audio), language=lang, word_timestamps=True, vad_filter=False)
    words = [Word(w.word.strip(), w.start, w.end) for s in segs for w in (s.words or []) if w.word.strip()]
    del m
    gc.collect()
    return words


async def chatterbox(text: str, out: Path, lang: str, voice: str | None = None, settings: dict | None = None) -> TTSResult:
    cfg = config.get()
    name = voice or cfg.chatterbox_voice
    ref = paths.voices / name if name else None
    st = settings or {}
    async with _LOCK:
        await asyncio.to_thread(_chatterbox_sync, text, out, lang, ref if ref and ref.exists() else None,
                                float(st.get("exaggeration", 0.6)), float(st.get("cfg_weight", 0.4)))
        wav = out.with_suffix(".wav")
        await run_ffmpeg(["-i", str(wav), "-b:a", "192k", str(out)])
        dur = await probe_duration(out)
        try:
            words = await asyncio.to_thread(_whisper_words_sync, wav, lang)
            # keep the script's own spelling when counts match (Whisper may misspell brand names)
            src = text.split()
            if len(words) == len(src):
                words = [Word(t, w.start, w.end) for t, w in zip(src, words)]
        except Exception:
            words = estimate_words(text, dur)
    return TTSResult(out, words, dur)


# ---------- stub ----------
async def stub(text: str, out: Path) -> TTSResult:
    text = " ".join(t for t in text.split() if not (t.startswith("<") or t.startswith("time=") or t == "/>"))
    dur = max(2.0, len(text.split()) * 0.36)
    await run_ffmpeg(["-f", "lavfi", "-i", f"sine=frequency=180:duration={dur:.2f}", "-af", "volume=0.04",
                      "-b:a", "128k", str(out)])
    return TTSResult(out, estimate_words(text, dur), dur)


async def synthesize(text: str, out: Path, lang: str, voice_id: str | None, dry_run: bool,
                     settings: dict | None = None) -> TTSResult:
    if dry_run:
        return await stub(text, out)
    if config.get().tts_provider == "chatterbox":
        return await chatterbox(text, out, lang, voice_id if voice_id and (paths.voices / voice_id).exists() else None, settings)
    return await elevenlabs(text, out, voice_id, settings, lang)


def provider_model() -> tuple[str, str]:
    cfg = config.get()
    return cfg.tts_provider, cfg.elevenlabs_model


def uses_tags() -> bool:
    p, m = provider_model()
    return p == "elevenlabs" and m.startswith("eleven_v3")
