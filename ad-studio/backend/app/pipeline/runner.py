"""Job queue. Single GPU worker, stage-batched so Ollama and ComfyUI never compete for VRAM."""
from __future__ import annotations

import asyncio
import json
import logging
import random
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..config import boot, config, paths
from ..events import broker
from ..models import ACTIVE, Campaign, Product, Video, VideoStatus, now, session
from ..providers import comfy, ollama, tts
from . import graphics, script as script_mod, subtitles, visuals
from .compose import Segment, compose

log = logging.getLogger("adforge.runner")
STAGES = ("script", "visuals", "voice", "compose")
PROGRESS = {"script": (0, 10), "visuals": (10, 70), "voice": (70, 80), "compose": (80, 100)}
STATUS = {"script": VideoStatus.scripting, "visuals": VideoStatus.visuals, "voice": VideoStatus.voice,
          "compose": VideoStatus.composing}


class Cancelled(Exception):
    pass


@dataclass
class Job:
    video_ids: list[int]
    stages: tuple[str, ...] = STAGES
    created: float = field(default_factory=time.time)


def video_dict(v: Video) -> dict:
    d = v.model_dump()
    d["video_url"] = paths.url(v.video_path)
    d["thumb_url"] = paths.url(v.thumb_path)
    d["script"] = json.loads(v.script_json) if v.script_json else None
    d.pop("script_json", None)
    return d


def update(vid: int, **kw) -> Video:
    with session() as s:
        v = s.get(Video, vid)
        for k, val in kw.items():
            setattr(v, k, val)
        v.updated_at = now()
        s.add(v)
        s.commit()
        s.refresh(v)
    broker.publish("video", video_dict(v))
    return v


def load(vid: int) -> tuple[Video, Campaign, Product]:
    with session() as s:
        v = s.get(Video, vid)
        c = s.get(Campaign, v.campaign_id)
        p = s.get(Product, c.product_id)
        return v, c, p


def tracking_url(p: Product, subid: str) -> str:
    u = p.affiliate_url
    if not u:
        return ""
    if "{subid}" in u:
        return u.replace("{subid}", subid)
    return u + ("&" if "?" in u else "?") + f"utm_source=adforge&utm_content={subid}"


class Runner:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[Job] = asyncio.Queue()
        self.current: Job | None = None
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        with session() as s:  # recover from crash
            for v in s.query(Video).filter(Video.status.in_([x.value for x in ACTIVE])).all():
                v.status, v.error = VideoStatus.failed, "Sunucu yeniden başlatıldı, tekrar deneyin."
                s.add(v)
            s.commit()
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()

    def enqueue(self, video_ids: list[int], stages: tuple[str, ...] = STAGES) -> None:
        for vid in video_ids:
            update(vid, status=VideoStatus.queued, error="", step="Sırada",
                   progress=PROGRESS[stages[0]][0])
        self.queue.put_nowait(Job(video_ids, stages))

    def snapshot(self) -> dict:
        return {"running": bool(self.current), "pending_jobs": self.queue.qsize(),
                "current": self.current.video_ids if self.current else []}

    async def _loop(self) -> None:
        while True:
            job = await self.queue.get()
            self.current = job
            try:
                await self._run(job)
            except Exception:  # never kill the worker
                log.exception("job failed")
            finally:
                self.current = None
                broker.publish("queue", self.snapshot())

    async def _run(self, job: Job) -> None:
        alive = list(job.video_ids)
        timers = {vid: 0.0 for vid in alive}
        for stage in job.stages:
            for vid in list(alive):
                v, _, _ = load(vid)
                if v.status == VideoStatus.cancelled:
                    alive.remove(vid)
                    continue
                t0 = time.time()
                try:
                    lo, _ = PROGRESS[stage]
                    update(vid, status=STATUS[stage], progress=lo)
                    await getattr(self, f"_{stage}")(vid)
                except Cancelled:
                    alive.remove(vid)
                except Exception as e:
                    log.exception("stage %s failed for %s", stage, vid)
                    update(vid, status=VideoStatus.failed, error=f"{stage}: {e}"[:1000])
                    alive.remove(vid)
                finally:
                    timers[vid] = timers.get(vid, 0) + time.time() - t0
            if stage == "script" and not boot.dry_run:
                await ollama.unload()
            if stage == "visuals" and not boot.dry_run:
                await comfy.free()
        for vid in job.video_ids:
            v, _, _ = load(vid)
            kw = {"render_seconds": v.render_seconds + timers.get(vid, 0)}
            if vid in alive and job.stages[-1] == "script":
                kw |= {"status": VideoStatus.scripted, "step": "Senaryo hazır — incele & render et", "progress": 10}
            update(vid, **kw)

    async def _progress(self, vid: int, stage: str, frac: float, step: str) -> None:
        lo, hi = PROGRESS[stage]
        v, _, _ = load(vid)
        if v.status == VideoStatus.cancelled:
            raise Cancelled
        update(vid, progress=round(lo + (hi - lo) * min(max(frac, 0), 1), 1), step=step)

    # ---------- stages ----------
    async def _script(self, vid: int) -> None:
        v, c, p = load(vid)
        if v.script_json:
            return
        await self._progress(vid, "script", 0.1, "Ollama senaryo yazıyor")
        with session() as s:
            others = [x.hook for x in s.query(Video).filter(Video.campaign_id == c.id, Video.id != vid).all() if x.hook]
        angle_key, angle_desc = next((a for a in script_mod.ANGLES if a[0] == v.angle), script_mod.ANGLES[0])
        sc = (script_mod.stub(p, c, angle_key, v.variant_index) if boot.dry_run
              else await script_mod.generate(p, c, angle_desc, others[-6:]))
        update(vid, script_json=sc.model_dump_json(), hook=sc.hook, caption=script_mod.full_caption(sc),
               progress=PROGRESS["script"][1], step="Senaryo hazır")

    async def _visuals(self, vid: int) -> None:
        v, c, _ = load(vid)
        sc = script_mod.AdScript.model_validate_json(v.script_json)
        out = paths.video_dir(vid)
        for f in out.glob("scene_*"):
            f.unlink()
        for f in out.glob("clip_*"):
            f.unlink()
        n = len(sc.scenes)

        async def prog(f: float) -> None:
            await self._progress(vid, "visuals", f, f"ComfyUI sahne {min(int(f * n) + 1, n)}/{n}")

        await visuals.generate(sc, out, c.visual_style, c.use_i2v or config.get().use_i2v, boot.dry_run, prog)

    async def _voice(self, vid: int) -> None:
        v, c, _ = load(vid)
        sc = script_mod.AdScript.model_validate_json(v.script_json)
        text = " ".join([sc.hook, *(s.voiceover for s in sc.scenes), sc.cta])
        await self._progress(vid, "voice", 0.2, "Seslendirme")
        res = await tts.synthesize(text, paths.video_dir(vid) / "voice.mp3", c.language, c.voice_id or None, boot.dry_run)
        (paths.video_dir(vid) / "words.json").write_text(json.dumps(
            {"duration": res.duration, "words": [w.__dict__ for w in res.words]}, ensure_ascii=False))
        update(vid, tts_chars=v.tts_chars + (0 if boot.dry_run else len(text)))

    async def _compose(self, vid: int) -> None:
        v, c, p = load(vid)
        cfg = config.get()
        sc = script_mod.AdScript.model_validate_json(v.script_json)
        out = paths.video_dir(vid)
        meta = json.loads((out / "words.json").read_text())
        words = [tts.Word(**w) for w in meta["words"]]
        dur = meta["duration"]
        media = sorted([*out.glob("clip_*"), *out.glob("scene_*")], key=lambda f: (int(f.stem.split("_")[1]), f.stem[0] != "c"))
        by_idx: dict[int, Path] = {}
        for f in media:  # prefer clip over still
            by_idx.setdefault(int(f.stem.split("_")[1]), f)
        scene_media = [by_idx[i] for i in sorted(by_idx)]
        if len(scene_media) < len(sc.scenes):
            raise RuntimeError("Eksik sahne görseli")

        # segment boundaries by word index: [hook+s0], s1..s(n-1), cta
        counts = [len(sc.hook.split()) + len(sc.scenes[0].voiceover.split()),
                  *(len(s.voiceover.split()) for s in sc.scenes[1:])]
        total_words = sum(counts) + len(sc.cta.split())

        def t_at(word_idx: int) -> float:
            if not words:
                return dur * word_idx / max(total_words, 1)
            i = word_idx if len(words) == total_words else int(word_idx * len(words) / total_words)
            return words[min(i, len(words) - 1)].start

        starts, acc = [0.0], 0
        for cnt in counts:
            acc += cnt
            starts.append(t_at(acc))
        cta_start = starts[-1]
        total = max(dur + 0.35, cta_start + cfg.end_card_seconds)
        segs = [Segment(scene_media[i], max(0.6, starts[i + 1] - starts[i])) for i in range(len(sc.scenes))]
        price = f"{p.price:,.2f} {p.currency}".replace(",", "X").replace(".", ",").replace("X", ".") if p.price else ""
        product_img = Path(p.image_path) if p.image_path else None
        still = next((f for f in reversed(scene_media) if f.suffix == ".png"), None) or next(iter(out.glob("scene_*.png")), None)
        card = graphics.end_card(out / "endcard.png", still, product_img, p.name, price, cfg.cta_default, cfg.brand_name)
        segs.append(Segment(card, total - sum(s.duration for s in segs)))

        headlines, t = [], 0.0
        for i, s in enumerate(segs[:-1]):
            text = sc.scenes[i].on_screen_text
            if i == 0 and len(sc.hook.split()) <= 6:
                text = sc.hook
            headlines.append((t + 0.05, t + s.duration - 0.05, text))
            t += s.duration
        ass = subtitles.build(words, headlines, out / "subs.ass", cfg.subtitle_font, cfg.subtitle_highlight, c.language)

        await self._progress(vid, "compose", 0.15, "FFmpeg montaj")
        music = pick_music(c.music)
        final = out / f"adforge_{vid}.mp4"
        await compose(segs, out / "voice.mp3", ass, final, out, music, cfg.music_volume)
        thumb = graphics.thumbnail(out / "thumb.jpg", scene_media[0] if scene_media[0].suffix == ".png" else card, sc.hook)
        (out / "caption.txt").write_text(
            f"{sc.title}\n\n{v.caption}\n\n{tracking_url(p, v.subid)}".strip(), encoding="utf-8")
        update(vid, status=VideoStatus.done, progress=100, step="Hazır", video_path=str(final), thumb_path=str(thumb),
               duration=round(total, 2))


def pick_music(choice: str) -> Path | None:
    if choice == "none":
        return None
    if choice:
        p = paths.music / choice
        return p if p.exists() else None
    tracks = [*paths.music.glob("*.mp3"), *paths.music.glob("*.m4a"), *paths.music.glob("*.wav")]
    return random.choice(tracks) if tracks else None


def new_subid() -> str:
    return "af" + secrets.token_hex(4)


runner = Runner()
