"""Motion studio use cases: dance transfer, music-driven dance and motion presets."""

from __future__ import annotations

import asyncio
import random
import shutil
import uuid
from pathlib import Path
from typing import Awaitable, Callable

from .comfy import ComfyBackend
from .jobs import Job, JobQueue
from .media import MediaError, extract_audio, prepare_driver, probe
from .models import (
    MAX_DANCE_SECONDS, MAX_MUSIC_SECONDS, CharacterSpec, DanceRequest, MotionBase, MotionPresetRequest,
    MusicDanceRequest,
)
from .prompting import dance_prompt, motion_prompt
from .service import Invalid, NotFound
from .store import Store
from .video import (
    DANCE_ENERGY, DANCE_STYLES, MODE_FILES, MOTION_PRESET_BY_ID, MOTION_PRESETS, RESOLUTIONS, WAN_FPS,
    DanceParams, Graph, MotionParams, MusicDanceParams, build_dance_graph, build_motion_graph, build_music_graph,
)

VIDEO_EXTS = {"mp4", "mov", "m4v", "webm", "mkv"}
AUDIO_EXTS = {"mp3", "wav", "m4a", "aac", "ogg", "opus", "flac"}
UPLOAD_KINDS = {  # audio kinds also accept videos (their soundtrack) and browser mic recordings (webm/ogg)
    "driver": VIDEO_EXTS,
    "music": AUDIO_EXTS | VIDEO_EXTS,
    "voice": AUDIO_EXTS | VIDEO_EXTS,  # reference recording to clone a voice from
    "speech": AUDIO_EXTS | VIDEO_EXTS,  # your own voice-over to lip-sync
}
MIN_SECONDS = {"voice": 3.0}
MAX_SOURCE_SECONDS = 600


def public_schema() -> dict:
    return {
        "resolutions": {r: {o: {"width": w, "height": h} for o, (w, h) in sizes.items()} for r, sizes in RESOLUTIONS.items()},
        "styles": [{"id": k, "label": label} for k, (label, _) in DANCE_STYLES.items()],
        "energies": [{"id": k, "label": label} for k, (label, _) in DANCE_ENERGY.items()],
        "presets": [{"id": p.id, "label": p.label} for p in MOTION_PRESETS],
        "limits": {"dance_seconds": MAX_DANCE_SECONDS, "music_seconds": MAX_MUSIC_SECONDS, "fps": WAN_FPS},
    }


class MotionStudio:
    def __init__(self, comfy: ComfyBackend, store: Store, jobs: JobQueue, work_dir: Path, pose_cache: str | None):
        self.comfy, self.store, self.jobs, self.pose_cache = comfy, store, jobs, pose_cache
        self.work_dir = work_dir
        self.work_dir.mkdir(parents=True, exist_ok=True)

    # ── uploads ─────────────────────────────────────────────────────────────
    def save_upload(self, kind: str, filename: str, path: Path) -> dict:
        """Validates an uploaded file at `path` and stores it as a driver clip or music track."""
        ext = Path(filename).suffix.lower().lstrip(".")
        if kind not in UPLOAD_KINDS:
            raise Invalid(f"kind must be one of {sorted(UPLOAD_KINDS)}")
        if ext not in UPLOAD_KINDS[kind]:
            raise Invalid(f"unsupported file type .{ext} for {kind}")
        try:
            info = probe(path)
        except MediaError as e:
            raise Invalid(str(e)) from e
        if kind == "driver" and not info.has_video:
            raise Invalid("the dance reference must be a video")
        if kind != "driver" and not info.has_audio:
            raise Invalid("the file has no audio track")
        if not MIN_SECONDS.get(kind, 0.5) <= info.duration <= MAX_SOURCE_SECONDS:
            raise Invalid(f"duration must be between {MIN_SECONDS.get(kind, 0.5):g} s and {MAX_SOURCE_SECONDS // 60} min")
        return self.store.save_clip(path, kind=kind, ext=ext, info=info.public(), name=Path(filename).name[:120])

    def uploads(self, kind: str) -> list[dict]:
        return self.store.clips(kinds=(kind,))

    def clips(self, character_id: str) -> list[dict]:
        self.character(character_id)
        return self.store.clips(character_id=character_id)

    def delete_clip(self, clip_id: str) -> None:
        if not self.store.clip(clip_id):
            raise NotFound(f"clip {clip_id} not found")
        self.store.delete_clip(clip_id)

    # ── helpers ─────────────────────────────────────────────────────────────
    def character(self, character_id: str) -> dict:
        if not (c := self.store.character(character_id)):
            raise NotFound(f"character {character_id} not found")
        return c

    def source_image(self, character: dict, req: MotionBase) -> dict:
        img = self.store.image(req.source_image_id)
        if not img or img["character_id"] != character["id"]:
            raise Invalid("pick one of this character's images as the source")
        return img

    def _clip(self, clip_id: str, kind: str) -> dict:
        clip = self.store.clip(clip_id)
        if not clip or clip["kind"] != kind:
            raise NotFound(f"{kind} {clip_id} not found")
        return clip

    @staticmethod
    def size(req: MotionBase, width: int, height: int) -> tuple[int, int]:
        orientation = req.orientation
        if orientation == "auto":
            ratio = width / height if height else 1.0
            orientation = "landscape" if ratio > 1.15 else "portrait" if ratio < 0.87 else "square"
        return RESOLUTIONS[req.resolution][orientation]

    def _submit(self, kind: str, character: dict, source: dict, render: Callable[[Job, Path], Awaitable[tuple[Graph, dict]]],
                caption: str, prompt: str) -> Job:
        async def run(job: Job) -> list[dict]:
            work = self.work_dir / job.id
            work.mkdir(parents=True, exist_ok=True)
            try:
                graph, meta = await render(job, work)
                (video,) = await self.comfy.run(
                    graph, lambda p: setattr(job, "progress", 0.05 + 0.95 * p), progress_nodes=graph.samplers()
                )
                out = work / "result.mp4"
                out.write_bytes(video)
                info = await asyncio.to_thread(probe, out)
                clip = self.store.save_clip(out, kind=kind, ext="mp4", info=info.public(), caption=caption,
                                            prompt=prompt, seed=meta["seed"], character_id=character["id"],
                                            source_image_id=source["id"])
                return [clip]
            finally:
                shutil.rmtree(work, ignore_errors=True)

        return self.jobs.submit(kind, run)

    async def upload_source(self, source: dict) -> str:
        return await self.comfy.upload(self.store.image_path(source["id"]).read_bytes(), f"studio_{source['id']}.png")

    # ── dance transfer ──────────────────────────────────────────────────────
    def dance(self, character_id: str, req: DanceRequest) -> Job:
        character = self.character(character_id)
        source = self.source_image(character, req)
        driver = self._clip(req.driver_id, "driver")
        seconds = min(req.seconds, driver["duration"] - req.start)
        if seconds < 1:
            raise Invalid("the selected range is shorter than 1 second")
        width, height = self.size(req, driver["width"], driver["height"])
        spec = CharacterSpec.model_validate(character["spec"])
        prompt, seed = dance_prompt(spec), req.seed if req.seed is not None else random.randrange(2**32)
        keep_audio = req.keep_audio and driver["has_audio"]

        async def render(job: Job, work: Path) -> tuple[Graph, dict]:
            src = self.store.clip_path(driver)
            frames = await asyncio.to_thread(prepare_driver, src, work / "driver.mp4", start=req.start, seconds=seconds,
                                             width=width, height=height, fps=WAN_FPS)
            audio = None
            if keep_audio:
                await asyncio.to_thread(extract_audio, src, work / "audio.wav", start=req.start, seconds=frames / WAN_FPS)
                audio = await self.comfy.upload((work / "audio.wav").read_bytes(), f"studio_{job.id}_audio.wav")
            job.progress = 0.05
            params = DanceParams(
                reference=await self.upload_source(source),
                driver=await self.comfy.upload((work / "driver.mp4").read_bytes(), f"studio_{job.id}_driver.mp4"),
                frames=frames, width=width, height=height, prompt=prompt, seed=seed, audio=audio,
                pose_strength=req.pose_strength, smooth=req.smooth, pose_cache=self.pose_cache,
            )
            return build_dance_graph(params), {"seed": seed}

        caption = f"dance · {driver['name']} · {seconds:.0f}s"
        return self._submit("dance", character, source, render, caption, prompt)

    # ── music-driven dance ──────────────────────────────────────────────────
    def music_dance(self, character_id: str, req: MusicDanceRequest) -> Job:
        character = self.character(character_id)
        source = self.source_image(character, req)
        music = self._clip(req.music_id, "music")
        if req.start + req.seconds > music["duration"] + 0.05:
            raise Invalid(f"the track has only {max(0.0, music['duration'] - req.start):.1f} s after the start point")
        width, height = self.size(req, source["width"], source["height"])
        seed = req.seed if req.seed is not None else random.randrange(2**32)

        async def render(job: Job, work: Path) -> tuple[Graph, dict]:
            await asyncio.to_thread(extract_audio, self.store.clip_path(music), work / "music.wav",
                                    start=req.start, seconds=req.seconds)
            job.progress = 0.05
            params = MusicDanceParams(
                image=await self.upload_source(source),
                audio=await self.comfy.upload((work / "music.wav").read_bytes(), f"studio_{job.id}_music.wav"),
                seconds=req.seconds, style=req.style, energy=req.energy, width=width, height=height, seed=seed,
                fast=not req.quality, smooth=req.smooth,
            )
            return build_music_graph(params), {"seed": seed}

        caption = f"{DANCE_STYLES[req.style][0]} · {DANCE_ENERGY[req.energy][0]} energy · {music['name']}"
        return self._submit("music_dance", character, source, render, caption, f"{req.style}/{req.energy}")

    # ── motion presets ──────────────────────────────────────────────────────
    def motion(self, character_id: str, req: MotionPresetRequest) -> Job:
        character = self.character(character_id)
        source = self.source_image(character, req)
        preset = MOTION_PRESET_BY_ID.get(req.preset_id or "")
        action = preset.action if preset else req.prompt
        if preset and req.prompt.strip():
            action = f"{action}, {req.prompt.strip()}"
        prompt = motion_prompt(CharacterSpec.model_validate(character["spec"]), action)
        width, height = self.size(req, source["width"], source["height"])
        seed = req.seed if req.seed is not None else random.randrange(2**32)

        async def render(job: Job, work: Path) -> tuple[Graph, dict]:
            image = await self.upload_source(source)
            return build_motion_graph(MotionParams(image, prompt, width, height, seed, req.smooth)), {"seed": seed}

        caption = preset.label if preset else req.prompt.strip()[:80]
        return self._submit("motion", character, source, render, caption, prompt)

    # ── status ──────────────────────────────────────────────────────────────
    async def health(self) -> dict:
        try:
            await self.comfy.system_stats()
        except Exception:
            return {"comfy": False, "modes": {m: [] for m in MODE_FILES}}
        listings: dict[str, set[str]] = {}
        modes = {}
        for mode, files in MODE_FILES.items():
            missing = []
            for f in files:
                if f.folder not in listings:
                    try:
                        listings[f.folder] = {n.replace("\\", "/") for n in await self.comfy.models(f.folder)}
                    except Exception:  # e.g. a ComfyUI too old to know models/frame_interpolation
                        listings[f.folder] = set()
                if f.name not in listings[f.folder]:
                    missing.append({"folder": f.folder, "file": f.name})
            modes[mode] = missing
        return {"comfy": True, "modes": modes}


def new_upload_path(work_dir: Path, filename: str) -> Path:
    return work_dir / f"upload_{uuid.uuid4().hex}{Path(filename).suffix.lower()}"
