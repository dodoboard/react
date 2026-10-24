"""Voice studio: Turkish (and multilingual) speech with cloned voices, and lip-synced talking videos.

Speech comes from the local TTS server (tts/server.py, Chatterbox Multilingual); lip-sync runs
InfiniteTalk in ComfyUI. Scripts are split into sentence chunks, normalized (numbers, %, money…),
synthesized one by one and joined with pauses that follow the punctuation. Each chunk's time
span is stored with the speech clip (meta.segments) for subtitles.

TTS and ComfyUI share one GPU. Before synthesis ComfyUI's models are unloaded only when its free
VRAM is below what the TTS model needs; afterwards the TTS model is moved to system RAM.
"""

from __future__ import annotations

import asyncio
import io
import math
import random
import shutil
import wave
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from .comfy import ComfyBackend
from .jobs import Job, JobQueue
from .media import extract_audio, probe
from .models import CharacterSpec, SpeakRequest, TalkRequest
from .motion import MotionStudio
from .prompting import talk_prompt
from .service import Invalid, NotFound
from .store import Store
from .turkish import Chunk, chunk, normalize
from .video import RESOLUTIONS, TALK_FPS, TalkParams, build_talk_graph

MAX_TALK_SECONDS = 30
VRAM_POLICIES = ("auto", "free", "never")
VOICE_REFERENCE_SECONDS = 15  # Chatterbox conditions on the first ~10 s anyway

LANGUAGES = {  # Chatterbox Multilingual's languages, Turkish first
    "tr": "Türkçe", "en": "English", "de": "Deutsch", "fr": "Français", "es": "Español", "it": "Italiano",
    "pt": "Português", "nl": "Nederlands", "ru": "Русский", "ar": "العربية", "pl": "Polski", "sv": "Svenska",
    "da": "Dansk", "no": "Norsk", "fi": "Suomi", "el": "Ελληνικά", "he": "עברית", "hi": "हिन्दी",
    "ko": "한국어", "ja": "日本語", "ms": "Bahasa Melayu", "sw": "Kiswahili",
}


class TTSClient:
    def __init__(self, base_url: str, timeout: float = 600.0):
        self._http = httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def health(self) -> dict:
        r = await self._http.get("/health", timeout=5)
        r.raise_for_status()
        return r.json()

    async def offload(self) -> None:
        """Ask the TTS server to move its model to system RAM (best effort)."""
        try:
            await self._http.post("/offload", timeout=30)
        except httpx.HTTPError:
            pass

    async def transcribe(self, wav: bytes, language: str | None) -> dict:
        try:
            r = await self._http.post("/transcribe", data={"language": language or ""},
                                      files={"audio": ("audio.wav", wav, "audio/wav")})
        except httpx.TransportError as e:
            raise RuntimeError("TTS server is not running: start tts/start.bat") from e
        if r.status_code != 200:
            raise RuntimeError(f"speech recognition failed: {r.text}")
        return r.json()

    async def synthesize(self, text: str, *, language: str, voice: bytes | None, exaggeration: float,
                         cfg_weight: float, temperature: float, seed: int | None) -> bytes:
        data = {"text": text, "language": language, "exaggeration": str(exaggeration),
                "cfg_weight": str(cfg_weight), "temperature": str(temperature)}
        if seed is not None:
            data["seed"] = str(seed)
        files = {"voice": ("voice.wav", voice, "audio/wav")} if voice else None
        try:
            r = await self._http.post("/synthesize", data=data, files=files)
        except httpx.TransportError as e:
            raise RuntimeError("TTS server is not running: start tts/start.bat") from e
        if r.status_code != 200:
            raise RuntimeError(f"TTS failed: {r.json().get('detail', r.text) if r.headers.get('content-type', '').startswith('application/json') else r.text}")
        return r.content


def join_wavs(parts: list[bytes], pauses: list[float]) -> tuple[bytes, list[tuple[float, float]]]:
    """Concatenate 16-bit WAVs of one format, `pauses[i]` seconds of silence after part i.

    Returns the WAV and each part's (start, end) in seconds.
    """
    out = io.BytesIO()
    spans: list[tuple[float, float]] = []
    params = None
    written = 0  # sample frames
    with wave.open(out, "wb") as dst:
        for i, part in enumerate(parts):
            with wave.open(io.BytesIO(part)) as src:
                if params is None:
                    params = (src.getnchannels(), src.getsampwidth(), src.getframerate())
                    dst.setnchannels(params[0])
                    dst.setsampwidth(params[1])
                    dst.setframerate(params[2])
                elif (src.getnchannels(), src.getsampwidth(), src.getframerate()) != params:
                    raise ValueError("TTS chunks have different audio formats")
                if i:
                    gap = round(pauses[i - 1] * params[2])
                    dst.writeframes(bytes(gap * params[0] * params[1]))
                    written += gap
                n = src.getnframes()
                dst.writeframes(src.readframes(n))
                spans.append((written / params[2], (written + n) / params[2]))
                written += n
    return out.getvalue(), spans


@dataclass
class Speech:
    wav: bytes
    chunks: list[Chunk]
    spans: list[tuple[float, float]] = field(default_factory=list)
    language: str = "tr"

    @property
    def spoken(self) -> str:
        return " ".join(c.spoken for c in self.chunks)

    def meta(self) -> dict:
        return {"language": self.language, "segments": [{"start": round(a, 3), "end": round(b, 3), "text": c.display, "spoken": c.spoken}
                             for c, (a, b) in zip(self.chunks, self.spans)]}


class VoiceStudio:
    def __init__(self, comfy: ComfyBackend, tts: TTSClient, store: Store, jobs: JobQueue, motion: MotionStudio,
                 vram_policy: str = "auto", vram_gb: float = 4.0):
        if vram_policy not in VRAM_POLICIES:
            raise ValueError(f"vram_policy must be one of {VRAM_POLICIES}")
        self.comfy, self.tts, self.store, self.jobs, self.motion = comfy, tts, store, jobs, motion
        self.vram_policy, self.vram_bytes = vram_policy, int(vram_gb * 2**30)

    # ── status ──────────────────────────────────────────────────────────────
    async def health(self) -> dict:
        try:
            tts = await self.tts.health()
        except Exception as e:
            tts = {"ok": False, "error": f"TTS server not reachable ({type(e).__name__})"}
        motion = await self.motion.health()
        return {"tts": tts, "comfy": motion["comfy"], "missing_models": motion["modes"].get("talk", [])}

    # ── helpers ─────────────────────────────────────────────────────────────
    def _voice(self, voice_id: str | None) -> dict | None:
        if not voice_id:
            return None
        clip = self.store.clip(voice_id)
        if not clip or clip["kind"] != "voice":
            raise NotFound(f"voice {voice_id} not found")
        return clip

    async def _voice_wav(self, clip: dict | None, work: Path) -> bytes | None:
        if clip is None:
            return None
        ref = work / f"voice_{clip['id']}.wav"
        await asyncio.to_thread(extract_audio, self.store.clip_path(clip), ref, start=0,
                                seconds=min(clip["duration"], VOICE_REFERENCE_SECONDS))
        return ref.read_bytes()

    async def _make_room(self) -> None:
        """Unload ComfyUI's models when a GPU TTS would not fit next to them."""
        if self.vram_policy == "never":
            return
        try:
            if (await self.tts.health()).get("device") in (None, "cpu"):
                return
            if self.vram_policy == "auto":
                devices = (await self.comfy.system_stats()).get("devices") or [{}]
                if devices[0].get("vram_free", 0) >= self.vram_bytes:
                    return  # enough room: keep ComfyUI's models loaded for the next render
            await self.comfy.free()
        except Exception:
            pass  # best effort; synthesize reports a real outage

    async def _synthesize(self, job: Job, req: SpeakRequest | TalkRequest, voice: dict | None, work: Path,
                          span: tuple[float, float]) -> Speech:
        chunks = chunk(req.text, speak=normalize if req.language == "tr" else str.strip)
        if not chunks:
            raise Invalid("the script is empty")
        await self._make_room()
        reference = await self._voice_wav(voice, work)
        seed = req.seed if req.seed is not None else random.randrange(2**31)
        wavs = []
        try:
            for i, c in enumerate(chunks):
                wavs.append(await self.tts.synthesize(c.spoken, language=req.language, voice=reference,
                                                      exaggeration=req.exaggeration, cfg_weight=req.cfg_weight,
                                                      temperature=req.temperature, seed=seed + i))
                job.progress = span[0] + (span[1] - span[0]) * (i + 1) / len(chunks)
        finally:
            await self.tts.offload()  # hand the VRAM back to ComfyUI
        wav, spans = join_wavs(wavs, [c.pause for c in chunks])
        return Speech(wav, chunks, spans, req.language)

    def _save_speech(self, speech: Speech, work: Path, *, script: str, character_id: str | None,
                     voice: dict | None, seed: int | None) -> dict:
        path = work / "speech.wav"
        path.write_bytes(speech.wav)
        info = probe(path)
        caption = (script[:77] + "…") if len(script) > 80 else script
        return self.store.save_clip(path, kind="speech", ext="wav", info=info.public(), caption=caption,
                                    prompt=speech.spoken, seed=seed, character_id=character_id,
                                    name=voice["name"] if voice else "default voice", meta=speech.meta())

    def _work(self, job: Job) -> Path:
        work = self.motion.work_dir / job.id
        work.mkdir(parents=True, exist_ok=True)
        return work

    # ── speech ──────────────────────────────────────────────────────────────
    def speak(self, req: SpeakRequest) -> Job:
        character = self.store.character(req.character_id) if req.character_id else None
        if req.character_id and not character:
            raise NotFound(f"character {req.character_id} not found")
        voice = self._voice(req.voice_id or (character or {}).get("voice_id"))

        async def run(job: Job) -> list[dict]:
            work = self._work(job)
            try:
                speech = await self._synthesize(job, req, voice, work, (0.0, 1.0))
                return [self._save_speech(speech, work, script=req.text.strip(),
                                          character_id=req.character_id, voice=voice, seed=req.seed)]
            finally:
                shutil.rmtree(work, ignore_errors=True)

        return self.jobs.submit("speech", run)

    # ── talking video ───────────────────────────────────────────────────────
    def talk(self, character_id: str, req: TalkRequest) -> Job:
        character = self.motion.character(character_id)
        source = self.motion.source_image(character, req)
        speech = None
        if req.speech_id:
            speech = self.store.clip(req.speech_id)
            if not speech or speech["kind"] != "speech":
                raise NotFound(f"speech {req.speech_id} not found")
            if speech["duration"] > MAX_TALK_SECONDS + 0.5:
                raise Invalid(f"speech is {speech['duration']:.0f} s; talking videos are limited to {MAX_TALK_SECONDS} s")
        voice = None if speech else self._voice(req.voice_id or character.get("voice_id"))
        width, height = self.motion.size(req, source["width"], source["height"])
        spec = CharacterSpec.model_validate(character["spec"])
        prompt = talk_prompt(spec, req.prompt)
        seed = req.seed if req.seed is not None else random.randrange(2**32)

        async def run(job: Job) -> list[dict]:
            work = self._work(job)
            try:
                if speech is None:
                    synthesized = await self._synthesize(job, req, voice, work, (0.0, 0.1))
                    track = self._save_speech(synthesized, work, script=req.text.strip(),
                                              character_id=character_id, voice=voice, seed=req.seed)
                else:
                    track = speech
                src = self.store.clip_path(track)
                info = await asyncio.to_thread(probe, src)
                if info.duration > MAX_TALK_SECONDS + 0.5:
                    raise Invalid(f"the speech runs {info.duration:.0f} s; shorten the script to {MAX_TALK_SECONDS} s")
                await asyncio.to_thread(extract_audio, src, work / "talk.wav", start=0, seconds=info.duration)
                frames = max(1, math.ceil(info.duration * TALK_FPS))
                params = TalkParams(
                    image=await self.motion.upload_source(source),
                    audio=await self.comfy.upload((work / "talk.wav").read_bytes(), f"studio_{job.id}_speech.wav"),
                    frames=frames, width=width, height=height, prompt=prompt, seed=seed, smooth=req.smooth,
                )
                graph = build_talk_graph(params)
                job.progress = 0.12
                (video,) = await self.comfy.run(graph, lambda p: setattr(job, "progress", 0.12 + 0.88 * p),
                                                progress_nodes=graph.samplers())
                out = work / "talk.mp4"
                out.write_bytes(video)
                clip = self.store.save_clip(out, kind="talk", ext="mp4", info=(await asyncio.to_thread(probe, out)).public(),
                                            caption=track["caption"], prompt=prompt, seed=seed,
                                            character_id=character_id, source_image_id=source["id"],
                                            meta={"speech_id": track["id"], **track["meta"]})
                return [clip]
            finally:
                shutil.rmtree(work, ignore_errors=True)

        return self.jobs.submit("talk", run)


TRANSCRIBE_SECONDS = 180


def transcribe_job(voice: VoiceStudio, clip_id: str, language: str | None) -> Job:
    """Word timings for a clip's audio (recordings, uploaded voice-overs, dance music…) → meta.words."""
    clip = voice.store.clip(clip_id)
    if not clip:
        raise NotFound(f"clip {clip_id} not found")
    if not clip["has_audio"]:
        raise Invalid("this clip has no audio")
    if clip["duration"] > TRANSCRIBE_SECONDS:
        raise Invalid(f"clips up to {TRANSCRIBE_SECONDS // 60} minutes can be transcribed")

    async def run(job: Job) -> list[dict]:
        work = voice._work(job)
        try:
            wav = work / "audio.wav"
            await asyncio.to_thread(extract_audio, voice.store.clip_path(clip), wav, start=0, seconds=clip["duration"])
            job.progress = 0.1
            result = await voice.tts.transcribe(wav.read_bytes(), language)
            if not result["words"]:
                raise Invalid("no speech found in this clip")
            return [voice.store.update_clip_meta(clip_id, words=result["words"], language=result.get("language"),
                                                 cues=None)]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    return voice.jobs.submit("transcribe", run, group="tts")


def public_schema() -> dict:
    return {
        "languages": [{"id": k, "label": v} for k, v in LANGUAGES.items()],
        "limits": {"talk_seconds": MAX_TALK_SECONDS, "fps": TALK_FPS, "voice_seconds": VOICE_REFERENCE_SECONDS},
        "resolutions": {o: {"width": w, "height": h} for o, (w, h) in RESOLUTIONS["480p"].items()},
    }
