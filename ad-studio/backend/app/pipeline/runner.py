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
from . import graphics, insights, product as product_mod, script as script_mod, subtitles, timeline as tl_mod, visuals
from .compose import Effects, Overlay, Segment, compose

log = logging.getLogger("adforge.runner")
STAGES = ("script", "voice", "visuals", "compose")
PROGRESS = {"script": (0, 10), "voice": (10, 20), "visuals": (20, 85), "compose": (85, 100)}
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
        self.queue = asyncio.Queue()  # bind to the running loop
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()

    def resume_stages(self, vid: int) -> tuple[str, ...]:
        v, _, _ = load(vid)
        if not v.script_json:
            return STAGES
        done = v.stage_done if v.stage_done in STAGES else "script"
        rest = STAGES[STAGES.index(done) + 1:]
        return rest or STAGES[1:]

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
            if stage == "script":
                await self._tournament(alive)
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
                    update(vid, stage_done=stage)
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
    async def _tournament(self, vids: list[int]) -> None:
        """Pick hooks per campaign: N candidates per slot, LLM-judged, best kept."""
        if not config.get().hook_tournament:
            return
        by_camp: dict[int, list[Video]] = {}
        for vid in vids:
            v, c, _ = load(vid)
            if not v.script_json and not v.hook and v.status != VideoStatus.cancelled:
                by_camp.setdefault(c.id, []).append(v)
        for cid, group in by_camp.items():
            _, c, p = load(group[0].id)
            for v in group:
                update(v.id, status=VideoStatus.scripting, step="Hook turnuvası", progress=2)
            angles = [v.angle for v in group]
            try:
                picks = (script_mod.stub_tournament(angles, cid) if boot.dry_run else
                         await script_mod.tournament(p, c, angles, insights.winning_hooks(5, cid), config.get().hooks_per_slot))
            except Exception as e:  # tournament is an optimisation; fall back to per-video hooks
                log.warning("hook tournament failed for campaign %s: %s", cid, e)
                continue
            for v, (_, hook, score) in zip(group, picks):
                update(v.id, hook=hook, hook_score=score)

    async def _script(self, vid: int) -> None:
        v, c, p = load(vid)
        if v.script_json:
            return
        await self._progress(vid, "script", 0.2, "Ollama senaryo yazıyor")
        with session() as s:
            others = [x.hook for x in s.query(Video).filter(Video.campaign_id == c.id, Video.id != vid).all() if x.hook]
        sc = (script_mod.stub(p, c, v.angle, v.variant_index, v.hook) if boot.dry_run
              else await script_mod.generate(p, c, v.angle, others[-6:], v.hook, insights.winning_hooks(5, c.id)))
        update(vid, script_json=sc.model_dump_json(), hook=sc.hook, caption=script_mod.full_caption(sc),
               progress=PROGRESS["script"][1], step="Senaryo hazır")

    async def _voice(self, vid: int) -> None:
        v, c, _ = load(vid)
        cfg = config.get()
        sc = script_mod.AdScript.model_validate_json(v.script_json)
        text = " ".join([sc.hook, *(s.voiceover for s in sc.scenes), sc.cta])
        await self._progress(vid, "voice", 0.2, "Seslendirme")
        out = paths.video_dir(vid)
        res = await tts.synthesize(text, out / "voice.mp3", c.language, c.voice_id or None, boot.dry_run)
        (out / "words.json").write_text(json.dumps(
            {"duration": res.duration, "words": [w.__dict__ for w in res.words]}, ensure_ascii=False))
        tl_mod.build(sc, res.words, res.duration, cfg.end_card_seconds).save(out / "timeline.json")
        update(vid, tts_chars=v.tts_chars + (0 if boot.dry_run else len(text)))

    async def _visuals(self, vid: int) -> None:
        v, c, p = load(vid)
        sc = script_mod.AdScript.model_validate_json(v.script_json)
        out = paths.video_dir(vid)
        for pat in ("scene_*", "clip_*", "bg_*", "ref_*", "vo_*"):
            for f in out.glob(pat):
                f.unlink()
        cut = None
        if config.get().product_mode != "off" and any(s.shot in script_mod.PRODUCT_SHOTS for s in sc.scenes):
            await self._progress(vid, "visuals", 0.01, "Ürün kesiliyor")
            try:
                cut = await product_mod.cutout(p)
            except Exception as e:  # unusable photo: fall back to generated product shots
                log.warning("cutout failed for product %s: %s", p.id, e)
        n = len(sc.scenes)

        async def prog(f: float) -> None:
            await self._progress(vid, "visuals", f, f"ComfyUI sahne {min(int(f * n) + 1, n)}/{n}")

        media = await visuals.generate(sc, out, c, cut, tl_mod.Timeline.load(out / "timeline.json"),
                                       out / "voice.mp3", boot.dry_run, prog)
        (out / "media.json").write_text(json.dumps([m.name for m in media]))

    async def _compose(self, vid: int) -> None:
        v, c, p = load(vid)
        cfg = config.get()
        sc = script_mod.AdScript.model_validate_json(v.script_json)
        out = paths.video_dir(vid)
        meta = json.loads((out / "words.json").read_text())
        words = [tts.Word(**w) for w in meta["words"]]
        tl = tl_mod.Timeline.load(out / "timeline.json")
        scene_media = [out / n for n in json.loads((out / "media.json").read_text())]
        if len(scene_media) < len(sc.scenes) or not all(m.exists() for m in scene_media):
            raise RuntimeError("Eksik sahne görseli — görselleri yeniden üretin")

        durs = tl.scene_durations
        segs = [Segment(scene_media[i], durs[i]) for i in range(len(sc.scenes))]
        price = f"{p.price:,.2f} {p.currency}".replace(",", "X").replace(".", ",").replace("X", ".") if p.price else ""
        product_img = Path(p.image_path) if p.image_path else None
        stills = [f for f in scene_media if f.suffix == ".png"]
        card = graphics.end_card(out / "endcard.png", stills[-1] if stills else None, product_img, p.name, price,
                                 cfg.cta_default, cfg.brand_name)
        segs.append(Segment(card, max(0.6, tl.total - sum(s.duration for s in segs))))

        headlines, t = [], 0.0
        hero_at: tuple[float, float] | None = None
        for i, s in enumerate(segs[:-1]):
            text = sc.scenes[i].on_screen_text
            if i == 0 and len(sc.hook.split()) <= 6:
                text = sc.hook
            headlines.append((t + 0.05, t + s.duration - 0.05, text))
            if hero_at is None and sc.scenes[i].shot == "product_hero":
                hero_at = (t + 0.3, t + s.duration - 0.05)
            t += s.duration
        hook_end = len(sc.hook.split())
        ass = subtitles.build(words, headlines, out / "subs.ass", cfg.subtitle_font, cfg.subtitle_highlight, c.language,
                              cfg.caption_style, words[hook_end - 1].end + 0.01 if 0 < hook_end <= len(words) else 0.0)

        overlays = []
        if cfg.price_badge and price and hero_at:
            overlays.append(Overlay(graphics.price_badge(out / "badge.png", price, p.platform), *hero_at))
        fx = Effects(punch=cfg.hook_punch, progress_color=cfg.subtitle_highlight if cfg.progress_bar else None,
                     sfx_volume=cfg.sfx_volume, overlays=overlays)
        await self._progress(vid, "compose", 0.15, "FFmpeg montaj")
        final = out / f"adforge_{vid}.mp4"
        await compose(segs, out / "voice.mp3", ass, final, out, pick_music(c.music), cfg.music_volume, fx)
        first = scene_media[0] if scene_media[0].suffix == ".png" else (stills[0] if stills else card)
        thumb = graphics.thumbnail(out / "thumb.jpg", first, sc.hook)
        (out / "caption.txt").write_text(
            f"{sc.title}\n\n{v.caption}\n\n{tracking_url(p, v.subid)}".strip(), encoding="utf-8")
        update(vid, status=VideoStatus.done, progress=100, step="Hazır", video_path=str(final), thumb_path=str(thumb),
               duration=round(tl.total, 2))


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
