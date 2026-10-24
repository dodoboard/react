"""Export: clips stitched into one post-ready MP4 with burned-in captions and a music bed.

Video: every clip is resampled to 30 fps by time (sources run at 16, 25, 30 or 32 fps), scaled to
cover the target format and center-cropped. Captions are drawn with Pillow and alpha-blended.
Audio: clip sound is laid on the timeline, music is ducked under speech, and the mix is mastered
to -14 LUFS integrated, -1.5 dBTP (what Instagram, TikTok and YouTube normalize to).
"""

from __future__ import annotations

import asyncio
import json
import math
import shutil
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import av
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .hd import VIDEO_KINDS, HDStudio, is_hd
from .jobs import Job, JobQueue
from .media import AUDIO_RATE, extract_audio, probe
from .models import ExportRequest
from .service import Invalid, NotFound
from .store import Store
from .subtitles import clip_cues, window

FORMATS = {"9:16": (1080, 1920), "4:5": (1080, 1350), "1:1": (1080, 1080), "16:9": (1920, 1080)}
FPS = 30
MAX_SECONDS = 180
TARGET_LUFS, TRUE_PEAK = -14.0, -1.5
DUCK_DB = -10.0  # music level change while someone speaks
SPEECH_GATE_DB = -40.0
FONT = Path(__file__).parent / "assets" / "fonts" / "Poppins-ExtraBold.ttf"
HIGHLIGHT = (255, 225, 77)  # the word being spoken (karaoke style)


@dataclass
class Segment:
    """One clip on the timeline: source [start, end) placed at `offset`."""

    path: Path
    start: float
    end: float
    offset: float
    has_audio: bool
    cues: list[dict] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return self.end - self.start


# ── captions ────────────────────────────────────────────────────────────────
class Captions:
    """Renders cues to RGBA overlays (cached per cue and highlighted word)."""

    def __init__(self, width: int, height: int, style: str = "reels", position: str = "lower"):
        self.width, self.height, self.style = width, height, style
        self.size = round(min(width, height) * (0.075 if style == "reels" else 0.055))  # 81 px on 1080
        self.font = ImageFont.truetype(str(FONT), self.size)
        self.max_width = width * 0.86
        self.center_y = height * (0.68 if position == "lower" else 0.5)  # clear of TikTok/Reels buttons
        self._cache: dict[tuple, tuple[np.ndarray, int, int]] = {}

    def _lines(self, words: list[str]) -> list[list[int]]:
        lines: list[list[int]] = [[]]
        space = self.font.getlength(" ")
        width = 0.0
        for i, word in enumerate(words):
            w = self.font.getlength(word)
            if lines[-1] and width + space + w > self.max_width:
                lines.append([])
                width = 0.0
            width += (space if lines[-1] else 0) + w
            lines[-1].append(i)
        return lines

    def overlay(self, cue: dict, active: int | None) -> tuple[np.ndarray, int, int]:
        """(RGBA array, x, y) for `cue` with word `active` highlighted."""
        key = (cue["start"], cue["text"], active if self.style == "reels" else None)
        if key in self._cache:
            return self._cache[key]
        words = [w["text"] for w in cue["words"]] or cue["text"].split()
        lines = self._lines(words)
        line_h = round(self.size * 1.25)
        stroke = max(2, round(self.size * 0.09)) if self.style == "reels" else 0
        pad = round(self.size * 0.35)
        img = Image.new("RGBA", (self.width, line_h * len(lines) + 2 * pad), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        space = self.font.getlength(" ")
        for row, indices in enumerate(lines):
            widths = [self.font.getlength(words[i]) for i in indices]
            total = sum(widths) + space * (len(indices) - 1)
            x, y = (self.width - total) / 2, pad + row * line_h
            if self.style == "minimal":
                draw.rounded_rectangle([x - pad, y - pad * 0.4, x + total + pad, y + line_h + pad * 0.2],
                                       radius=pad, fill=(0, 0, 0, 150))
            for i, w in zip(indices, widths):
                fill = HIGHLIGHT if self.style == "reels" and i == active else (255, 255, 255)
                draw.text((x, y), words[i], font=self.font, fill=fill, stroke_width=stroke, stroke_fill=(0, 0, 0))
                x += w + space
        box = img.getbbox() or (0, 0, 1, 1)
        cropped = np.asarray(img.crop(box))
        y = round(self.center_y - img.height / 2) + box[1]
        self._cache[key] = result = (cropped, box[0], max(0, min(self.height - cropped.shape[0], y)))
        return result


def active_cue(cues: list[dict], t: float) -> tuple[dict, int | None] | None:
    for cue in cues:
        if cue["start"] <= t < cue["end"]:
            word = next((i for i, w in enumerate(cue["words"]) if w["start"] <= t < w["end"]), None)
            return cue, word
    return None


def blend(frame: np.ndarray, overlay: np.ndarray, x: int, y: int) -> None:
    h, w = overlay.shape[:2]
    h, w = min(h, frame.shape[0] - y), min(w, frame.shape[1] - x)
    region = frame[y:y + h, x:x + w].astype(np.float32)
    alpha = overlay[:h, :w, 3:4].astype(np.float32) / 255
    frame[y:y + h, x:x + w] = (region * (1 - alpha) + overlay[:h, :w, :3] * alpha).astype(np.uint8)


# ── video ───────────────────────────────────────────────────────────────────
def _cover(frame: av.VideoFrame, width: int, height: int) -> np.ndarray:
    scale = max(width / frame.width, height / frame.height)
    sw, sh = max(width, math.ceil(frame.width * scale)), max(height, math.ceil(frame.height * scale))
    rgb = frame.reformat(width=sw, height=sh, format="rgb24", interpolation="LANCZOS").to_ndarray()
    x, y = (sw - width) // 2, (sh - height) // 2
    return np.ascontiguousarray(rgb[y:y + height, x:x + width])


def segment_frames(seg: Segment, width: int, height: int, fps: int = FPS):
    """RGB frames at seg.start + k/fps: the source frame on screen at each instant (frame hold)."""
    count = max(1, round(seg.duration * fps))
    with av.open(str(seg.path)) as container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        origin = container.start_time / av.time_base if container.start_time else 0.0
        frames = container.decode(stream)
        current, upcoming, image = None, next(frames, None), None
        for k in range(count):
            t = seg.start + k / fps
            while upcoming is not None and (current is None or (upcoming.time or 0) - origin <= t + 1e-6):
                current, upcoming, image = upcoming, next(frames, None), None
            if current is None:
                raise ValueError(f"no video frames in {seg.path.name}")
            if image is None:
                image = _cover(current, width, height)
            yield image


# ── audio ───────────────────────────────────────────────────────────────────
def _read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path)) as w:
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    return data.reshape(-1, 2).astype(np.float32) / 32768


def _place(track: np.ndarray, audio: np.ndarray, at: int) -> None:
    n = max(0, min(len(audio), len(track) - at))
    track[at:at + n] += audio[:n]


def duck_gain(speech: np.ndarray, rate: int = AUDIO_RATE, duck_db: float = DUCK_DB,
              attack: float = 0.05, release: float = 0.4) -> np.ndarray:
    """Per-sample gain for music: duck_db while speech is above the gate, smoothed."""
    block = rate // 50  # 20 ms
    n = len(speech)
    blocks = max(1, math.ceil(n / block))
    mono = np.zeros(blocks * block, dtype=np.float32)
    mono[:n] = speech.mean(axis=1)
    rms = np.sqrt(np.mean(mono.reshape(blocks, block) ** 2, axis=1) + 1e-12)
    target = np.where(20 * np.log10(rms) > SPEECH_GATE_DB, duck_db, 0.0)
    down, up = math.exp(-0.02 / attack), math.exp(-0.02 / release)
    gain_db = np.empty(blocks, dtype=np.float32)
    g = 0.0
    for i, want in enumerate(target):
        coeff = down if want < g else up
        g = want + (g - want) * coeff
        gain_db[i] = g
    per_sample = np.repeat(10 ** (gain_db / 20), block)[:n]
    return per_sample[:, None]


def master(mix: np.ndarray, work: Path, rate: int = AUDIO_RATE) -> np.ndarray:
    """Linear gain to TARGET_LUFS, capped so true peak stays under TRUE_PEAK (FFmpeg loudnorm stats)."""
    probe_path = work / "mix.wav"
    _write_wav(probe_path, mix, rate)
    with av.open(str(probe_path)) as c:
        stats = json.loads(av.filter.loudnorm.stats(f"i={TARGET_LUFS}:tp={TRUE_PEAK}:lra=11", c.streams.audio[0]))
    measured, peak = float(stats["input_i"]), float(stats["input_tp"])
    if not math.isfinite(measured):
        return mix
    gain = min(TARGET_LUFS - measured, TRUE_PEAK - peak)
    return np.clip(mix * 10 ** (gain / 20), -1, 1)


def _write_wav(path: Path, audio: np.ndarray, rate: int) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())


@dataclass
class Music:
    path: Path
    start: float = 0.0
    volume_db: float = -16.0
    duck: bool = True


def mix_audio(segments: list[Segment], music: Music | None, total: float, work: Path) -> np.ndarray | None:
    n = round(total * AUDIO_RATE)
    speech = np.zeros((n, 2), dtype=np.float32)
    for i, seg in enumerate(segments):
        if seg.has_audio:
            tmp = work / f"seg_{i}.wav"
            extract_audio(seg.path, tmp, start=seg.start, seconds=seg.duration)
            _place(speech, _read_wav(tmp), round(seg.offset * AUDIO_RATE))
    mix = speech
    if music is not None:
        tmp = work / "music.wav"
        extract_audio(music.path, tmp, start=music.start, seconds=total)
        bed = np.zeros_like(speech)
        _place(bed, _read_wav(tmp), 0)
        bed *= 10 ** (music.volume_db / 20)
        if music.duck:
            bed *= duck_gain(speech)
        mix = speech + bed
    if not np.any(mix):
        return None
    return master(mix, work)


# ── render ──────────────────────────────────────────────────────────────────
def render(segments: list[Segment], dst: Path, *, size: tuple[int, int], captions: Captions | None,
           music: Music | None, work: Path, on_progress: Callable[[float], None] = lambda p: None) -> None:
    width, height = size
    total = sum(s.duration for s in segments)
    audio = mix_audio(segments, music, total, work)
    if audio is not None:
        audio = audio.astype(np.float32)
    cues = [cue for s in segments for cue in s.cues]
    total_frames = sum(max(1, round(s.duration * FPS)) for s in segments)
    with av.open(str(dst), "w", format="mp4", options={"movflags": "+faststart"}) as out:
        video = out.add_stream("libx264", rate=FPS)
        video.width, video.height, video.pix_fmt = width, height, "yuv420p"
        video.options = {"crf": "18", "preset": "fast", "profile": "high"}
        sound = None
        if audio is not None:
            sound = out.add_stream("aac", rate=AUDIO_RATE, layout="stereo")
            sound.bit_rate = 192_000
        written, sent = 0, 0  # video frames, audio samples

        def send_audio(until: int) -> None:
            nonlocal sent
            while sound is not None and sent < min(until, len(audio)):
                chunk = audio[sent:min(sent + 1024, until, len(audio))]
                frame = av.AudioFrame.from_ndarray(np.ascontiguousarray(chunk.T), format="fltp", layout="stereo")
                frame.sample_rate, frame.pts = AUDIO_RATE, sent
                for packet in sound.encode(frame):
                    out.mux(packet)
                sent += len(chunk)

        for seg in segments:
            for k, image in enumerate(segment_frames(seg, width, height)):
                t = seg.offset + k / FPS
                if captions is not None and (hit := active_cue(cues, t)):
                    image = image.copy()  # the same source frame can repeat: never draw on the cache
                    blend(image, *captions.overlay(*hit))
                frame = av.VideoFrame.from_ndarray(image, format="rgb24").reformat(format="yuv420p")
                frame.pts = written
                for packet in video.encode(frame):
                    out.mux(packet)
                written += 1
                send_audio(round(written / FPS * AUDIO_RATE))  # interleave sound with the picture
                on_progress(written / total_frames)
        for packet in video.encode():
            out.mux(packet)
        if sound is not None:
            send_audio(len(audio))
            for packet in sound.encode():
                out.mux(packet)


# ── job ─────────────────────────────────────────────────────────────────────
class ExportStudio:
    def __init__(self, store: Store, jobs: JobQueue, hd: HDStudio, work_dir: Path):
        self.store, self.jobs, self.hd, self.work_dir = store, jobs, hd, work_dir

    def export(self, req: ExportRequest) -> Job:
        character = self.store.character(req.character_id)
        if not character:
            raise NotFound(f"character {req.character_id} not found")
        items = []
        total = 0.0
        for item in req.items:
            clip = self.store.clip(item.clip_id)
            if not clip or clip["character_id"] != character["id"]:
                raise NotFound(f"clip {item.clip_id} not found for this influencer")
            if clip["kind"] not in VIDEO_KINDS:
                raise Invalid(f"{clip['kind']} clips cannot be exported")
            end = clip["duration"] if item.end is None else min(item.end, clip["duration"])
            if not 0 <= item.start < end - 0.2:
                raise Invalid("each clip needs a start before its end")
            items.append((clip, item.start, end))
            total += end - item.start
        if total > MAX_SECONDS:
            raise Invalid(f"exports are limited to {MAX_SECONDS // 60} minutes")
        music = None
        if req.music:
            track = self.store.clip(req.music.clip_id)
            if not track or track["kind"] != "music":
                raise NotFound(f"music {req.music.clip_id} not found")
            if req.music.start >= track["duration"]:
                raise Invalid("the music starts after the song ends")
            music = Music(self.store.clip_path(track), req.music.start, req.music.volume_db, req.music.duck)
        size = FORMATS[req.format]

        async def run(job: Job) -> list[dict]:
            work = self.work_dir / job.id
            work.mkdir(parents=True, exist_ok=True)
            try:
                needs_hd = [c for c, _, _ in items if req.hd and not is_hd(c)]
                split = 0.6 if needs_hd else 0.0
                segments, offset = [], 0.0
                for clip, start, end in items:
                    if req.hd and not is_hd(clip):
                        i = needs_hd.index(clip)
                        clip = self.hd.find_hd(clip) or await self.hd.render_hd(
                            job, clip, (split * i / len(needs_hd), split * (i + 1) / len(needs_hd)))
                    cues = window(clip_cues(clip), start, end, offset) if req.subtitles.enabled else []
                    segments.append(Segment(self.store.clip_path(clip), start, end, offset, clip["has_audio"], cues))
                    offset += end - start
                captions = Captions(*size, req.subtitles.style, req.subtitles.position) if req.subtitles.enabled else None
                out = work / "export.mp4"
                await asyncio.to_thread(render, segments, out, size=size, captions=captions, music=music, work=work,
                                        on_progress=lambda p: setattr(job, "progress", split + (1 - split) * p))
                caption = f"{req.format} · {len(items)} clip{'s' if len(items) > 1 else ''}" + (
                    " · subtitles" if req.subtitles.enabled else "") + (" · music" if music else "")
                meta = {"format": req.format, "items": [i.model_dump() for i in req.items], "hd_clips": req.hd,
                        "subtitles": req.subtitles.model_dump(), "music": req.music.model_dump() if req.music else None}
                return [self.store.save_clip(out, kind="export", ext="mp4", info=probe(out).public(),
                                             name=character["name"], caption=caption, character_id=character["id"],
                                             meta=meta)]
            finally:
                shutil.rmtree(work, ignore_errors=True)

        return self.jobs.submit("export", run, group="upscale" if req.hd else "export")
