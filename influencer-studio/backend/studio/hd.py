"""HD: Real-ESRGAN upscaling for images (2x) and generated videos (short side 1080 px).

Videos are upscaled a few seconds at a time: the clip is split into CHUNK_FRAMES-frame pieces,
each goes through ComfyUI (Real-ESRGAN 4x, then Lanczos down to the target size) and the pieces
are joined with the original audio. One graph for a whole 30 s clip would hold every 4x frame
in RAM at once (~57 GB at 480p); a chunk needs ~3.7 GB.
"""

from __future__ import annotations

import asyncio
import shutil
from fractions import Fraction
from pathlib import Path

import av

from .comfy import ComfyBackend
from .jobs import Job, JobQueue
from .media import join_video, probe, split_video
from .service import Invalid, NotFound
from .store import Store
from .video import REALESRGAN, Graph, out

IMAGE_SCALE = 2  # 4x model, then halved: sharper than a native 2x model
HD_SHORT_SIDE = 1080
CHUNK_FRAMES = 48
VIDEO_KINDS = {"dance", "music_dance", "motion", "talk"}  # generated clips


def is_hd(clip: dict) -> bool:
    return bool(clip["meta"].get("hd")) or min(clip["width"], clip["height"]) >= HD_SHORT_SIDE


def hd_size(width: int, height: int) -> tuple[int, int]:
    """Short side HD_SHORT_SIDE, aspect kept, even dimensions for H.264."""
    scale = HD_SHORT_SIDE / min(width, height)
    return round(width * scale / 2) * 2, round(height * scale / 2) * 2


def build_image_upscale_graph(image: str, scale: float = IMAGE_SCALE) -> Graph:
    g = Graph()
    model = g.add("UpscaleModelLoader", model_name=REALESRGAN.name)
    upscaled = g.add("ImageUpscaleWithModel", upscale_model=model, image=g.add("LoadImage", image=image))
    g.add("PreviewImage", images=g.add("ImageScaleBy", image=upscaled, upscale_method="lanczos", scale_by=scale / 4))
    return g


def build_video_upscale_graph(video: str, width: int, height: int) -> Graph:
    g = Graph()
    parts = g.add("GetVideoComponents", video=g.add("LoadVideo", file=video))
    model = g.add("UpscaleModelLoader", model_name=REALESRGAN.name)
    upscaled = g.add("ImageUpscaleWithModel", upscale_model=model, image=parts)
    scaled = g.add("ImageScale", image=upscaled, upscale_method="lanczos", width=width, height=height, crop="center")
    g.add("SaveVideo", video=g.add("CreateVideo", images=scaled, fps=out(parts, 2)),
          filename_prefix="influencer-studio/hd", format="mp4")
    return g


class HDStudio:
    def __init__(self, comfy: ComfyBackend, store: Store, jobs: JobQueue, work_dir: Path):
        self.comfy, self.store, self.jobs, self.work_dir = comfy, store, jobs, work_dir

    async def _require_model(self) -> None:
        if REALESRGAN.name not in {n.replace("\\", "/") for n in await self.comfy.models(REALESRGAN.folder)}:
            raise Invalid(f"missing models/{REALESRGAN.folder}/{REALESRGAN.name}: run "
                          "python scripts/download_models.py --comfy <ComfyUI> --profile none --video hd")

    def upscale_image(self, image_id: str) -> Job:
        img = self.store.image(image_id)
        if not img:
            raise NotFound(f"image {image_id} not found")
        if not img["character_id"]:
            raise Invalid("upscale works on an influencer's images")

        async def run(job: Job) -> list[dict]:
            await self._require_model()
            name = await self.comfy.upload(self.store.image_path(image_id).read_bytes(), f"studio_{image_id}.png")
            (data,) = await self.comfy.run(build_image_upscale_graph(name), lambda p: setattr(job, "progress", p))
            caption = " · ".join(filter(None, (img["caption"], "HD")))
            return [self.store.save_image(data, kind="content", caption=caption, prompt=img["prompt"], seed=img["seed"],
                                          character_id=img["character_id"])]

        return self.jobs.submit("upscale_image", run, group="upscale")

    @staticmethod
    def check_clip(clip: dict | None, clip_id: str) -> dict:
        if not clip:
            raise NotFound(f"clip {clip_id} not found")
        if clip["kind"] not in VIDEO_KINDS:
            raise Invalid("HD works on generated videos")
        if is_hd(clip):
            raise Invalid("this video is already HD")
        return clip

    def find_hd(self, clip: dict) -> dict | None:
        """An earlier HD copy of `clip`, if any."""
        return next((c for c in self.store.clips(character_id=clip["character_id"], kinds=(clip["kind"],))
                     if c["meta"].get("source_clip_id") == clip["id"] and c["meta"].get("hd")), None)

    async def render_hd(self, job: Job, clip: dict, span: tuple[float, float] = (0.0, 1.0)) -> dict:
        """Upscale `clip` chunk by chunk and store the HD copy (used by the HD and export jobs)."""
        await self._require_model()
        width, height = hd_size(clip["width"], clip["height"])
        work = self.work_dir / f"{job.id}_hd_{clip['id']}"
        work.mkdir(parents=True, exist_ok=True)
        lo, hi = span
        try:
            src = self.store.clip_path(clip)
            with av.open(str(src)) as c:
                rate = c.streams.video[0].average_rate or Fraction(round(clip["fps"] or 25))
            chunks = await asyncio.to_thread(split_video, src, work, CHUNK_FRAMES)
            upscaled = []
            for i, chunk in enumerate(chunks):
                name = await self.comfy.upload(chunk.read_bytes(), f"studio_{job.id}_{clip['id']}_{i:03}.mp4")
                a = lo + (hi - lo) * 0.95 * i / len(chunks)
                b = lo + (hi - lo) * 0.95 * (i + 1) / len(chunks)
                (video,) = await self.comfy.run(build_video_upscale_graph(name, width, height),
                                                lambda p, a=a, b=b: setattr(job, "progress", a + (b - a) * p))
                upscaled.append(work / f"hd_{i:03}.mp4")
                upscaled[-1].write_bytes(video)
            result = work / "hd.mp4"
            await asyncio.to_thread(join_video, upscaled, result, rate=rate,
                                    audio_src=src if clip["has_audio"] else None)
            meta = {**clip["meta"], "hd": True, "source_clip_id": clip["id"]}
            caption = " · ".join(filter(None, (clip["caption"], "HD")))
            return self.store.save_clip(result, kind=clip["kind"], ext="mp4", info=probe(result).public(),
                                        name=clip["name"], caption=caption, prompt=clip["prompt"], seed=clip["seed"],
                                        character_id=clip["character_id"], source_image_id=clip["source_image_id"],
                                        meta=meta)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def upscale_clip(self, clip_id: str) -> Job:
        clip = self.check_clip(self.store.clip(clip_id), clip_id)

        async def run(job: Job) -> list[dict]:
            return [await self.render_hd(job, clip)]

        return self.jobs.submit("upscale_video", run, group="upscale")
