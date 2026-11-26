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
from ..models import ACTIVE, Campaign, CampaignProduct, Product, Video, VideoStatus, now, session
from ..providers import comfy, ollama, tts
from . import brandkit, graphics, insights, product as product_mod, script as script_mod, subtitles, timeline as tl_mod, visuals
from .compose import Effects, Overlay, Segment, compose
from .gpu import gpu_lock

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


def campaign_products(c: Campaign) -> list[Product]:
    with session() as s:
        links = s.query(CampaignProduct).filter(CampaignProduct.campaign_id == c.id).order_by(CampaignProduct.position).all()
        prods = [s.get(Product, l.product_id) for l in links] if links else [s.get(Product, c.product_id)]
    return [p for p in prods if p]


def product_subid(subid: str, p: Product, multi: bool) -> str:
    return f"{subid}p{p.id}" if multi else subid


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
            if stage != "compose":
                await gpu_lock().acquire()
            try:
                await self._stage(stage, alive, timers)
            finally:
                if stage != "compose":
                    gpu_lock().release()
        self._finish(job, alive, timers)

    async def _stage(self, stage: str, alive: list[int], timers: dict[int, float]) -> None:
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

    def _finish(self, job: Job, alive: list[int], timers: dict[int, float]) -> None:
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
            _, c, _ = load(group[0].id)
            prods = campaign_products(c)
            style = brandkit.resolve(c)
            for v in group:
                update(v.id, status=VideoStatus.scripting, step="Hook turnuvası", progress=2)
            angles = [v.angle for v in group]
            try:
                picks = (script_mod.stub_tournament(angles, cid) if boot.dry_run else
                         await script_mod.tournament(prods, c, angles, insights.winning_hooks(5, cid), config.get().hooks_per_slot, style))
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
        prods = campaign_products(c)
        style = brandkit.resolve(c)
        bad: list[str] = []
        if boot.dry_run:
            sc = script_mod.stub(prods, c, v.angle, v.variant_index, v.hook)
        else:
            sc, bad = await script_mod.generate(prods, c, v.angle, others[-6:], v.hook, insights.winning_hooks(5, c.id), style)
        update(vid, script_json=sc.model_dump_json(), hook=sc.hook, caption=script_mod.full_caption(sc, style),
               progress=PROGRESS["script"][1],
               step=f"Uyarı: yasaklı kelime ({', '.join(bad)}) — senaryoyu düzenleyin" if bad else "Senaryo hazır")

    async def _voice(self, vid: int) -> None:
        v, c, _ = load(vid)
        cfg = config.get()
        sc = script_mod.AdScript.model_validate_json(v.script_json)
        text = " ".join([sc.hook, *(s.voiceover for s in sc.scenes), sc.cta])
        await self._progress(vid, "voice", 0.2, "Seslendirme")
        out = paths.video_dir(vid)
        voice_id = c.voice_id or brandkit.resolve(c).voice_id or None
        res = await tts.synthesize(text, out / "voice.mp3", c.language, voice_id, boot.dry_run)
        (out / "words.json").write_text(json.dumps(
            {"duration": res.duration, "words": [w.__dict__ for w in res.words]}, ensure_ascii=False))
        tl_mod.build(sc, res.words, res.duration, cfg.end_card_seconds).save(out / "timeline.json")
        update(vid, tts_chars=v.tts_chars + (0 if boot.dry_run else len(text)))

    async def _visuals(self, vid: int) -> None:
        v, c, _ = load(vid)
        sc = script_mod.AdScript.model_validate_json(v.script_json)
        out = paths.video_dir(vid)
        for pat in ("scene_*", "clip_*", "bg_*", "ref_*", "vo_*"):
            for f in out.glob(pat):
                f.unlink()
        prods = campaign_products(c)
        cuts: list[Path | None] = [None] * len(prods)
        used = {s.product_ref for s in sc.scenes if s.shot in script_mod.PRODUCT_SHOTS}
        if config.get().product_mode != "off" and used:
            await self._progress(vid, "visuals", 0.01, "Ürünler kesiliyor")
            for i in sorted(used):
                if i >= len(prods):
                    continue
                try:
                    cuts[i] = await product_mod.cutout(prods[i])
                except Exception as e:  # unusable photo: fall back to generated product shots
                    log.warning("cutout failed for product %s: %s", prods[i].id, e)
        n = len(sc.scenes)

        async def prog(f: float) -> None:
            await self._progress(vid, "visuals", f, f"ComfyUI sahne {min(int(f * n) + 1, n)}/{n}")

        media = await visuals.generate(sc, out, c, cuts, tl_mod.Timeline.load(out / "timeline.json"),
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
        style = brandkit.resolve(c)
        prods = campaign_products(c) or [p]
        multi = c.kind == "collection" and len(prods) > 1
        stills = [f for f in scene_media if f.suffix == ".png"]
        token = graphics.FONT_OVERRIDE.set(style.font_path)
        try:
            if multi:
                items = [(Path(x.cutout_path or x.image_path) if (x.cutout_path or x.image_path) else None, x.name, fmt_price(x))
                         for x in prods]
                title = sc.hook if len(sc.hook) <= 40 else f"{len(prods)} ürün"
                card = graphics.collection_card(out / "endcard.png", stills[-1] if stills else None, items, title,
                                                style.cta, style.name, style.primary, style.accent, style.logo)
            else:
                card = graphics.end_card(out / "endcard.png", stills[-1] if stills else None,
                                         Path(p.image_path) if p.image_path else None, p.name, fmt_price(p),
                                         style.cta, style.name, style.primary, style.accent, style.logo)
            segs.append(Segment(card, max(0.6, tl.total - sum(s.duration for s in segs))))

            headlines, overlays, t = [], [], 0.0
            badge_done: set[int] = set()
            for i, s in enumerate(segs[:-1]):
                scn = sc.scenes[i]
                text = scn.on_screen_text
                if i == 0 and len(sc.hook.split()) <= 6 and not multi:
                    text = sc.hook
                headlines.append((t + 0.05, t + s.duration - 0.05, text))
                ref = min(scn.product_ref, len(prods) - 1)
                wants = scn.shot in script_mod.PRODUCT_SHOTS and (multi or scn.shot == "product_hero")
                if cfg.price_badge and wants and ref not in badge_done and fmt_price(prods[ref]):
                    badge_done.add(ref)
                    badge = graphics.price_badge(out / f"badge_{ref}.png", fmt_price(prods[ref]),
                                                 prods[ref].platform, style.accent)
                    overlays.append(Overlay(badge, t + 0.3, t + s.duration - 0.05))
                t += s.duration
            if style.logo:
                overlays.insert(0, Overlay(graphics.logo_watermark(out / "logo.png", style.logo), 0.0, tl.total, "44", "48"))
        finally:
            graphics.FONT_OVERRIDE.reset(token)
        hook_end = len(sc.hook.split())
        ass = subtitles.build(words, headlines, out / "subs.ass", style.font_name, style.highlight_hex, c.language,
                              cfg.caption_style, words[hook_end - 1].end + 0.01 if 0 < hook_end <= len(words) else 0.0)
        fx = Effects(punch=cfg.hook_punch, progress_color=style.highlight_hex if cfg.progress_bar else None,
                     sfx_volume=cfg.sfx_volume, overlays=overlays)
        await self._progress(vid, "compose", 0.15, "FFmpeg montaj")
        final = out / f"adforge_{vid}.mp4"
        await compose(segs, out / "voice.mp3", ass, final, out, pick_music(c.music), cfg.music_volume, fx)
        first = scene_media[0] if scene_media[0].suffix == ".png" else (stills[0] if stills else card)
        thumb = graphics.thumbnail(out / "thumb.jpg", first, sc.hook)
        links = [(x, tracking_url(x, product_subid(v.subid, x, multi))) for x in prods]
        link_txt = "\n".join(f"{x.name}: {u}" if multi else u for x, u in links if u)
        (out / "caption.txt").write_text(f"{sc.title}\n\n{v.caption}\n\n{link_txt}".strip(), encoding="utf-8")
        (out / "links.txt").write_text("\n".join(f"{x.name}\t{u}" for x, u in links), encoding="utf-8")
        update(vid, status=VideoStatus.done, progress=100, step="Hazır", video_path=str(final), thumb_path=str(thumb),
               duration=round(tl.total, 2))


def fmt_price(p: Product) -> str:
    if not p.price:
        return ""
    return f"{p.price:,.2f} {p.currency}".replace(",", "X").replace(".", ",").replace("X", ".")


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
