"""Voice studio: Turkish (and multilingual) speech with cloned voices, and lip-synced talking videos.

Speech comes from the local TTS server (tts/server.py, Chatterbox Multilingual); lip-sync runs
InfiniteTalk in ComfyUI. Scripts are normalized (numbers, %, money…) and split into sentence
chunks, synthesized one by one and joined with short pauses.
"""

from __future__ import annotations

import asyncio
import io
import math
import random
import shutil
import wave
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
from .turkish import chunk, normalize
from .video import RESOLUTIONS, TALK_FPS, TalkParams, build_talk_graph

MAX_TALK_SECONDS = 30
SENTENCE_PAUSE = 0.25  # seconds of silence between synthesized chunks
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


def join_wavs(parts: list[bytes], pause: float) -> bytes:
    """Concatenate mono/stereo 16-bit WAVs of one sample rate with `pause` seconds of silence between."""
    out = io.BytesIO()
    params = None
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
                    dst.writeframes(bytes(int(pause * params[2]) * params[0] * params[1]))
                dst.writeframes(src.readframes(src.getnframes()))
    return out.getvalue()


class VoiceStudio:
    def __init__(self, comfy: ComfyBackend, tts: TTSClient, store: Store, jobs: JobQueue, motion: MotionStudio):
        self.comfy, self.tts, self.store, self.jobs, self.motion = comfy, tts, store, jobs, motion

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

    async def _synthesize(self, job: Job, req: SpeakRequest | TalkRequest, voice: dict | None, work: Path,
                          span: tuple[float, float]) -> tuple[bytes, str]:
        text = normalize(req.text) if req.language == "tr" else req.text.strip()
        parts = chunk(text)
        if not parts:
            raise Invalid("the script is empty")
        try:
            if (await self.tts.health()).get("device") not in (None, "cpu"):
                await self.comfy.free()  # TTS and ComfyUI share the GPU: unload ComfyUI's models first
        except Exception:
            pass  # health/free are best effort; synthesize reports a real outage
        reference = await self._voice_wav(voice, work)
        seed = req.seed if req.seed is not None else random.randrange(2**31)
        wavs = []
        for i, part in enumerate(parts):
            wavs.append(await self.tts.synthesize(part, language=req.language, voice=reference,
                                                  exaggeration=req.exaggeration, cfg_weight=req.cfg_weight,
                                                  temperature=req.temperature, seed=seed + i))
            job.progress = span[0] + (span[1] - span[0]) * (i + 1) / len(parts)
        return join_wavs(wavs, SENTENCE_PAUSE), text

    def _save_speech(self, wav_bytes: bytes, work: Path, *, script: str, spoken: str, character_id: str | None,
                     voice: dict | None, seed: int | None) -> dict:
        path = work / "speech.wav"
        path.write_bytes(wav_bytes)
        info = probe(path)
        caption = (script[:77] + "…") if len(script) > 80 else script
        return self.store.save_clip(path, kind="speech", ext="wav", info=info.public(), caption=caption,
                                    prompt=spoken, seed=seed, character_id=character_id,
                                    name=voice["name"] if voice else "default voice")

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
                wav_bytes, spoken = await self._synthesize(job, req, voice, work, (0.0, 1.0))
                return [self._save_speech(wav_bytes, work, script=req.text.strip(), spoken=spoken,
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
                if speech:
                    src, script = self.store.clip_path(speech), speech["caption"]
                else:
                    wav_bytes, spoken = await self._synthesize(job, req, voice, work, (0.0, 0.1))
                    saved = self._save_speech(wav_bytes, work, script=req.text.strip(), spoken=spoken,
                                              character_id=character_id, voice=voice, seed=req.seed)
                    src, script = self.store.clip_path(saved), saved["caption"]
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
                                            caption=script, prompt=prompt, seed=seed, character_id=character_id,
                                            source_image_id=source["id"])
                return [clip]
            finally:
                shutil.rmtree(work, ignore_errors=True)

        return self.jobs.submit("talk", run)


def public_schema() -> dict:
    return {
        "languages": [{"id": k, "label": v} for k, v in LANGUAGES.items()],
        "limits": {"talk_seconds": MAX_TALK_SECONDS, "fps": TALK_FPS, "voice_seconds": VOICE_REFERENCE_SECONDS},
        "resolutions": {o: {"width": w, "height": h} for o, (w, h) in RESOLUTIONS["480p"].items()},
    }
