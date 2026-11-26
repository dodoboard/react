"""Documentary episode pipeline: outline → script → quality gate → voice → visuals → compose → thumbnail → shorts cut."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from pydantic import BaseModel

from ...config import boot, config, paths
from ...events import broker
from ...media import probe_duration, run_ffmpeg
from ...models import Channel, Character, Episode, Topic, now, session
from ...providers import comfy, ollama, tts
from .. import graphics, luts, product as product_mod, realism, speech, subtitles, visuals
from ..compose import VERTICAL, WIDE, Effects, Segment, compose
from ..gpu import gpu_lock
from ..runner import pick_music
from . import script as ds

log = logging.getLogger("adforge.docu")
STAGES = ("outline", "script", "gate", "voice", "visuals", "compose", "thumbnail", "shorts")
GPU = {"outline", "script", "gate", "voice", "visuals", "thumbnail", "shorts"}
LLM = {"outline", "script", "gate"}
PROGRESS = {"outline": (0, 4), "script": (4, 14), "gate": (14, 17), "voice": (17, 25), "visuals": (25, 80),
            "compose": (80, 92), "thumbnail": (92, 95), "shorts": (95, 100)}
ACTIVE = {"queued", *STAGES}
GAP = 0.9  # seconds of breath between chapters
WIDE_IMG = (1344, 768)
S2V_WIDE = (832, 480)
I2V_WIDE = (1280, 704)
PRESENTER_CHUNK = 10.0
OUTRO_SECONDS = 4.0


class Stop(Exception):
    """Pipeline halted on purpose (cancelled / needs review)."""


@dataclass
class Item:
    chapter: int
    seg: int
    kind: str
    start: float
    end: float
    text: str
    visual_prompt: str
    lower_third: str


def ep_dir(eid: int) -> Path:
    d = paths.media / "episodes" / str(eid)
    d.mkdir(parents=True, exist_ok=True)
    return d


def ep_dict(e: Episode) -> dict:
    d = e.model_dump()
    d["video_url"] = paths.url(e.video_path)
    d["thumb_url"] = paths.url(e.thumb_path)
    d["chapters"] = json.loads(e.chapters_json) if e.chapters_json else []
    d["quality"] = json.loads(e.quality_json) if e.quality_json else None
    for k in ("outline_json", "script_json", "quality_json", "chapters_json"):
        d.pop(k, None)
    return d


def ep_update(eid: int, **kw) -> Episode:
    with session() as s:
        e = s.get(Episode, eid)
        for k, v in kw.items():
            setattr(e, k, v)
        e.updated_at = now()
        s.add(e)
        s.commit()
        s.refresh(e)
    broker.publish("episode", ep_dict(e))
    return e


def ep_load(eid: int) -> tuple[Episode, Channel, Character | None, Topic | None]:
    with session() as s:
        e = s.get(Episode, eid)
        c = s.get(Channel, e.channel_id)
        ch = s.get(Character, c.character_id) if c.character_id else None
        t = s.get(Topic, e.topic_id) if e.topic_id else None
        return e, c, ch, t


def avatar_path(ch: Character | None) -> Path | None:
    if ch and ch.avatar and (paths.avatars / ch.avatar).exists():
        return paths.avatars / ch.avatar
    return None


class DocuRunner:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[tuple[int, tuple[str, ...]]] = asyncio.Queue()
        self.current: int | None = None
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        with session() as s:
            for e in s.query(Episode).filter(Episode.status.in_(list(ACTIVE))).all():
                e.status, e.error = "failed", "Sunucu yeniden başlatıldı — tekrar deneyin."
                s.add(e)
            s.commit()
        self.queue = asyncio.Queue()
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()

    def resume_stages(self, eid: int) -> tuple[str, ...]:
        e, *_ = ep_load(eid)
        if e.stage_done in STAGES:
            rest = STAGES[STAGES.index(e.stage_done) + 1:]
            return rest or STAGES
        return STAGES

    def enqueue(self, eid: int, stages: tuple[str, ...] | None = None) -> None:
        stages = stages or STAGES
        ep_update(eid, status="queued", error="", step="Sırada", progress=PROGRESS[stages[0]][0])
        self.queue.put_nowait((eid, stages))

    async def _loop(self) -> None:
        while True:
            eid, stages = await self.queue.get()
            self.current = eid
            try:
                await self._run(eid, stages)
            except Exception:
                log.exception("episode %s crashed", eid)
            finally:
                self.current = None

    async def _run(self, eid: int, stages: tuple[str, ...]) -> None:
        t0 = time.time()
        llm_used = comfy_used = False
        try:
            for stage in stages:
                e, *_ = ep_load(eid)
                if e.status == "cancelled":
                    return
                if stage not in LLM and llm_used and not boot.dry_run:
                    await ollama.unload()
                    llm_used = False
                lock = gpu_lock() if stage in GPU else None
                if lock:
                    await lock.acquire()
                try:
                    lo, _ = PROGRESS[stage]
                    ep_update(eid, status=stage, progress=lo)
                    await getattr(self, f"_{stage}")(eid)
                    ep_update(eid, stage_done=stage)
                finally:
                    if lock:
                        lock.release()
                llm_used |= stage in LLM
                comfy_used |= stage in ("visuals", "thumbnail", "shorts")
            e, *_ = ep_load(eid)
            ep_update(eid, status="ready", progress=100, step="Yayına hazır", render_seconds=e.render_seconds + time.time() - t0)
        except Stop as s:
            ep_update(eid, step=str(s) or "Durduruldu")
        except Exception as ex:
            log.exception("episode %s failed", eid)
            ep_update(eid, status="failed", error=f"{ex}"[:1000])
        finally:
            if not boot.dry_run:
                if llm_used:
                    await ollama.unload()
                if comfy_used:
                    await comfy.free()

    async def _progress(self, eid: int, stage: str, frac: float, step: str) -> None:
        lo, hi = PROGRESS[stage]
        e, *_ = ep_load(eid)
        if e.status == "cancelled":
            raise Stop("İptal edildi")
        ep_update(eid, progress=round(lo + (hi - lo) * min(max(frac, 0), 1), 1), step=step)

    # ---------- stages ----------
    async def _outline(self, eid: int) -> None:
        e, c, ch, t = ep_load(eid)
        if e.outline_json:
            return
        if not t:
            raise ValueError("Bölümün konusu yok")
        await self._progress(eid, "outline", 0.2, "Taslak çıkarılıyor")
        o = ds.stub_outline(t, e.kind, c) if boot.dry_run else await ds.outline(c, ch, t, e.kind)
        ep_update(eid, outline_json=o.model_dump_json(), title=o.title)

    async def _script(self, eid: int, notes: str = "") -> None:
        e, c, ch, _ = ep_load(eid)
        if e.script_json and not notes:
            return
        o = ds.Outline.model_validate_json(e.outline_json)

        async def prog(f: float) -> None:
            await self._progress(eid, "script", f, f"Senaryo yazılıyor ({int(f * len(o.chapters))}/{len(o.chapters)} bölüm)")

        sc = ds.stub_script(o, c, e.kind) if boot.dry_run else await ds.write(c, ch, o, e.kind, notes, prog)
        ep_update(eid, script_json=sc.model_dump_json(), title=sc.title, tags=",".join(sc.tags))

    async def _gate(self, eid: int) -> None:
        e, c, *_ = ep_load(eid)
        sc = ds.DocScript.model_validate_json(e.script_json)
        await self._progress(eid, "gate", 0.3, "Kalite jürisi")
        v = await (ds.stub_judge(sc) if boot.dry_run else ds.judge(sc))
        if v.score < c.min_quality:
            await self._progress(eid, "gate", 0.6, f"Puan {v.score:.1f} — yeniden yazılıyor")
            await self._script(eid, v.rewrite_notes or "; ".join(v.issues) or "Daha özgün, daha akıcı ve temkinli yaz.")
            sc = ds.DocScript.model_validate_json(ep_load(eid)[0].script_json)
            v = await (ds.stub_judge(sc) if boot.dry_run else ds.judge(sc))
        ep_update(eid, quality_json=v.model_dump_json(), quality_score=v.score)
        if v.score < c.min_quality:
            ep_update(eid, status="needs_review", error=f"Kalite puanı {v.score:.1f} < {c.min_quality:g}: " + "; ".join(v.issues[:3]))
            raise Stop("Kalite eşiği geçilemedi — otomatik yayın durduruldu")

    async def _voice(self, eid: int) -> None:
        e, c, ch, _ = ep_load(eid)
        sc = ds.DocScript.model_validate_json(e.script_json)
        wd = ep_dir(eid)
        voice_id = (ch.voice_id if ch else "") or None
        lang = (ch.language if ch else "") or c.language
        try:
            vsettings = json.loads(ch.voice_settings) if ch and ch.voice_settings else None
        except json.JSONDecodeError:
            vsettings = None
        prov, model = tts.provider_model()
        items: list[Item] = []
        all_words: list[tts.Word] = []
        parts: list[Path] = []
        offset = 0.0
        for ci, chap in enumerate(sc.chapters):
            await self._progress(eid, "voice", ci / len(sc.chapters), f"Seslendirme {ci + 1}/{len(sc.chapters)}")
            originals = [s.text for s in chap.segments]
            spoken = [speech.spoken(t, lang, keep_tags=tts.uses_tags()) for t in originals]
            text = speech.join_with_breaks(spoken, [s.kind for s in chap.segments], model, prov)
            res = await tts.synthesize(text, wd / f"ch_{ci}.mp3", lang, voice_id, boot.dry_run, vsettings)
            parts.append(res.audio)
            counts = [len(speech.strip_tags(t).split()) for t in originals]
            total = sum(counts)
            words = speech.remap(speech.clean_words(res.words), originals, [speech.strip_tags(x) for x in spoken])

            def t_at(idx: int) -> float:
                if not words:
                    return res.duration * idx / max(total, 1)
                i = idx if len(words) == total else int(idx * len(words) / total)
                return words[min(i, len(words) - 1)].start

            acc, starts = 0, []
            for cnt in counts:
                starts.append(0.0 if acc == 0 else t_at(acc))
                acc += cnt
            chap_end = res.duration + GAP
            for si, seg in enumerate(chap.segments):
                end = starts[si + 1] if si + 1 < len(starts) else chap_end
                items.append(Item(ci, si, seg.kind, offset + starts[si], offset + end, seg.text, seg.visual_prompt, seg.lower_third))
            all_words += [tts.Word(w.text, w.start + offset, w.end + offset) for w in words]
            offset += chap_end
        # concat chapters with a breath of silence after each
        inputs: list[str] = []
        for p in parts:
            inputs += ["-i", str(p)]
        graph = "".join(f"[{i}:a]aresample=48000,apad=pad_dur={GAP}[a{i}];" for i in range(len(parts)))
        graph += "".join(f"[a{i}]" for i in range(len(parts))) + f"concat=n={len(parts)}:v=0:a=1[out]"
        await run_ffmpeg([*inputs, "-filter_complex", graph, "-map", "[out]", "-b:a", "192k", str(wd / "voice.mp3")])
        dur = await probe_duration(wd / "voice.mp3")
        (wd / "timeline.json").write_text(json.dumps({"duration": dur, "items": [asdict(i) for i in items]}, ensure_ascii=False))
        (wd / "words.json").write_text(json.dumps([w.__dict__ for w in all_words], ensure_ascii=False))

    def _timeline(self, eid: int) -> tuple[float, list[Item], list[tts.Word]]:
        wd = ep_dir(eid)
        t = json.loads((wd / "timeline.json").read_text())
        words = [tts.Word(**w) for w in json.loads((wd / "words.json").read_text())]
        return t["duration"], [Item(**i) for i in t["items"]], words

    async def _visuals(self, eid: int) -> None:
        e, c, ch, _ = ep_load(eid)
        wd = ep_dir(eid)
        _, items, _ = self._timeline(eid)
        avatar = avatar_path(ch)
        look = (ch.look_prompt if ch else "") or "a documentary presenter"
        cfg = config.get()
        media: list[dict] = []
        n = len(items)
        animate = pick_animated(items, cfg.doc_i2v_ratio)
        refs: dict[tuple[int, str], Path] = {}  # (chapter, "a"|"b") → identity-locked presenter frame

        async def ref_for(ci: int, cam: str, prog) -> Path:
            if (ci, cam) not in refs:
                place = next((x.visual_prompt for x in items if x.chapter == ci and x.kind == "narration" and x.visual_prompt), "")
                setting = f"in a location related to: {place[:160]}" if place else "in a quiet study with old books and maps"
                framing = "seen in a medium shot, seated," if cam == "a" else "seen in a close-up, slightly off-center,"
                refs[(ci, cam)] = await visuals.character_ref(avatar, setting, framing, wd / f"ref_{ci}_{cam}.png",
                                                              boot.dry_run, prog, S2V_WIDE)
            return refs[(ci, cam)]

        for k, it in enumerate(items):
            async def prog(f: float, _k=k) -> None:
                await self._progress(eid, "visuals", (_k + f) / n, f"Görsel {_k + 1}/{n}")

            span = it.end - it.start
            if it.kind == "presenter" and avatar:
                chunk = max(3.0, cfg.presenter_chunk)
                chunks = max(1, int(span // chunk) + (1 if span % chunk > 0.5 else 0))
                step = span / chunks
                for j in range(chunks):
                    a, b = it.start + j * step, it.start + (j + 1) * step
                    cam = "a" if j % 2 == 0 else "b"  # A/B camera cut on long pieces to camera
                    ref = await ref_for(it.chapter, cam, prog)
                    f = await visuals._presenter(k * 10 + j, avatar, (a, b), wd / "voice.mp3", wd, boot.dry_run, prog,
                                                 size=S2V_WIDE, prompt=f"{look}, talking to the camera, documentary interview",
                                                 ref_frame=ref)
                    media.append({"file": f.name, "start": a, "end": b, "kind": "presenter", "cam": cam})
                continue
            prompt = ", ".join(x for x in (it.visual_prompt, c.visual_style) if x)
            shot = realism.doc_shot_type(it.visual_prompt)
            if boot.dry_run:
                img = graphics.stub_scene(wd / f"shot_{k}.png", k, it.lower_third or f"Sahne {k + 1}", "", WIDE_IMG)
                await prog(1)
            else:
                img = await visuals._t2i(prompt, wd, f"shot_{k}", prog, "text, caption, watermark", WIDE_IMG, shot, "doc")
            legacy = cfg.i2v_mode != "off" and (cfg.i2v_mode == "all" or it.seg == 0)
            if not boot.dry_run and (k in animate or legacy):
                img = await visuals._i2v(img, it.visual_prompt, span, k, wd, prog, I2V_WIDE, shot, "doc")
            media.append({"file": img.name, "start": it.start, "end": it.end, "kind": "narration"})
        (wd / "media.json").write_text(json.dumps(media))

    async def _compose(self, eid: int) -> None:
        e, c, ch, _ = ep_load(eid)
        if e.kind == "short":
            await self._compose_vertical(eid, None)
            return
        wd = ep_dir(eid)
        sc = ds.DocScript.model_validate_json(e.script_json)
        dur, items, words = self._timeline(eid)
        media = json.loads((wd / "media.json").read_text())
        accent = graphics.hex_rgb("#EAB308")
        segs = [Segment(wd / m["file"], max(0.4, m["end"] - m["start"])) for m in media]
        still = next((wd / m["file"] for m in media if m["file"].endswith(".png") and m["kind"] == "narration"), None)
        outro = graphics.doc_card(wd / "outro.png", sc.title, "Abone olun · Yeni bölümler her hafta", accent, (1920, 1080), still)
        segs.append(Segment(outro, OUTRO_SECONDS))
        heads: list[tuple[float, float, str]] = []
        chapters = []
        for ci, chap in enumerate(sc.chapters):
            first = next(i for i in items if i.chapter == ci)
            chapters.append((first.start, chap.title))
            if ci == 1:
                heads.append((first.start + 0.2, first.start + 4.5, sc.title))
            elif ci > 1:
                heads.append((first.start + 0.2, first.start + 3.5, chap.title))
        for it in items:
            if it.lower_third:
                heads.append((it.start + 0.4, min(it.end, it.start + 4.5), it.lower_third))
        ass = subtitles.build([], heads, wd / "titles.ass", "Inter", "#EAB308", c.language, res=(1920, 1080))
        srt = subtitles.to_srt(words, wd / "captions.srt")
        await self._progress(eid, "compose", 0.1, "Belgesel montajı (16:9)")
        final = wd / f"episode_{eid}.mp4"
        fx = Effects(punch=False, progress_color=None, sfx_volume=0, xfade=0.5, film=True, canvas=WIDE,
                     lut=luts.lut_path(config.get().lut_doc), loudness=-16.0)
        await compose(segs, wd / "voice.mp3", ass, final, wd, pick_music(c.music), 0.12, fx)
        chapter_txt = chapter_lines(chapters)
        desc = "\n\n".join(x for x in [sc.description, chapter_txt, " ".join("#" + t.replace(" ", "") for t in sc.tags[:5]),
                                       "Bu videoda yapay zekâ destekli seslendirme ve görseller kullanılmıştır."] if x)
        ep_update(eid, video_path=str(final), srt_path=str(srt), duration=round(dur + OUTRO_SECONDS, 2), description=desc,
                  chapters_json=json.dumps([{"t": round(t, 1), "title": n} for t, n in chapters], ensure_ascii=False))

    async def _compose_vertical(self, eid: int, window: tuple[float, float] | None, source: int | None = None) -> Path:
        """Render a 9:16 short. window=None → whole episode (standalone short); else a cut from the source episode."""
        e, c, ch, _ = ep_load(eid)
        src = source or eid
        wd, sd = ep_dir(eid), ep_dir(src)
        dur, items, words = self._timeline(src)
        media = json.loads((sd / "media.json").read_text())
        se, *_ = ep_load(src)
        sc = ds.DocScript.model_validate_json(se.script_json)
        a, b = window or (0.0, dur)
        voice = wd / "voice_short.mp3"
        await run_ffmpeg(["-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", str(sd / "voice.mp3"), "-af",
                          f"afade=t=in:d=0.05,afade=t=out:st={max(0, b - a - 0.3):.2f}:d=0.3", "-b:a", "192k", str(voice)])
        segs: list[Segment] = []
        for m in media:
            s0, s1 = max(a, m["start"]), min(b, m["end"])
            if s1 - s0 < 0.3:
                continue
            f = sd / m["file"]
            if f.suffix == ".png":
                v = wd / f"v_{f.name}"
                if not v.exists():
                    graphics.blur_pad(f, v, (1080, 1920))
                f = v
            segs.append(Segment(f, s1 - s0))
        card = graphics.doc_card(wd / "short_end.png", sc.title, "Tam belgesel kanalda ▶" if window else "Daha fazlası için takip et",
                                 graphics.hex_rgb("#EAB308"), (1080, 1920))
        segs.append(Segment(card, 2.0))
        sw = [tts.Word(w.text, w.start - a, w.end - a) for w in words if a <= w.start < b]
        hook_end = sw[min(len(sw) - 1, 6)].end if sw else 0
        ass = subtitles.build(sw, [(0.05, min(3.0, b - a), sc.title)], wd / "short.ass", config.get().subtitle_font,
                              "#EAB308", c.language, "bold_yellow", hook_end)
        out = wd / f"short_{eid}.mp4"
        fx = Effects(punch=True, progress_color="#EAB308", sfx_volume=0.2, canvas=VERTICAL,
                     lut=luts.lut_path(config.get().lut_doc), loudness=-14.0)
        await compose(segs, voice, ass, out, wd, pick_music(c.music), 0.12, fx)
        ep_update(eid, video_path=str(out), duration=round(b - a + 2.0, 2))
        return out

    async def _thumbnail(self, eid: int) -> None:
        e, c, ch, _ = ep_load(eid)
        if e.kind == "short":
            return
        wd = ep_dir(eid)
        sc = ds.DocScript.model_validate_json(e.script_json)
        await self._progress(eid, "thumbnail", 0.2, "Kapak görseli")
        if boot.dry_run:
            bg = graphics.stub_scene(wd / "thumb_bg.png", 4, "", "", WIDE_IMG)
        else:
            async def prog(_: float) -> None: ...
            bg = await visuals._t2i(f"{sc.thumbnail_prompt}, dramatic lighting, high contrast, cinematic, 16:9", wd,
                                    "thumb_bg", prog, "text, letters, watermark", WIDE_IMG)
        person = None
        av = avatar_path(ch)
        if av and config.get().identity_lock and not boot.dry_run:
            async def _p(_: float) -> None: ...
            bg = await visuals.character_ref(av, f"inside this scene: {sc.thumbnail_prompt}", "on the right third of the frame, "
                                             "with an intrigued expression,", wd / "thumb_bg_person.png", False, _p, (672, 384))
            av = None  # already in the picture
        if av:
            try:
                person = product_mod.make_cutout(av, wd / "presenter_cut.png")
            except Exception as ex:
                log.info("presenter cutout skipped: %s", ex)
        thumb = graphics.yt_thumbnail(wd / "thumbnail.jpg", bg, sc.thumbnail_text or sc.title, person)
        ep_update(eid, thumb_path=str(thumb))

    async def _shorts(self, eid: int) -> None:
        e, c, ch, _ = ep_load(eid)
        if e.kind != "long" or c.format != "both" or e.parent_id:
            return
        with session() as s:
            if s.query(Episode).filter(Episode.parent_id == eid).count():
                return
        dur, items, _ = self._timeline(eid)
        win = await pick_window(items, boot.dry_run)
        if not win:
            return
        with session() as s:
            child = Episode(channel_id=c.id, topic_id=e.topic_id, kind="short", parent_id=eid, status="shorts",
                            title=(e.title[:88] + " #Shorts"), outline_json=e.outline_json, script_json=e.script_json,
                            tags=e.tags, stage_done="shorts")
            s.add(child)
            s.commit()
            s.refresh(child)
        await self._progress(eid, "shorts", 0.3, "Shorts kesiti")
        await self._compose_vertical(child.id, win, source=eid)
        sc = ds.DocScript.model_validate_json(e.script_json)
        ep_update(child.id, status="ready", progress=100, step="Yayına hazır (uzun bölüm sonrası)",
                  description=f"{sc.description}\n\n#Shorts #belgesel", quality_score=e.quality_score)


def pick_animated(items: list[Item], ratio: float) -> set[int]:
    """Which b-roll shots get real motion (i2v): chapter openers first, then the longest shots."""
    narr = [k for k, it in enumerate(items) if it.kind == "narration"]
    budget = round(len(narr) * max(0.0, min(1.0, ratio)))
    if budget <= 0:
        return set()
    openers = [k for k in narr if k == 0 or items[k - 1].chapter != items[k].chapter or items[k - 1].kind == "presenter"]
    rest = sorted((k for k in narr if k not in openers), key=lambda k: items[k].end - items[k].start, reverse=True)
    return set((openers + rest)[:budget])


class Window(BaseModel):
    start_index: int
    end_index: int
    reason: str = ""


async def pick_window(items: list[Item], dry_run: bool, lo: float = 35.0, hi: float = 58.0) -> tuple[float, float] | None:
    """Contiguous self-contained 35-58 s span. LLM picks the most gripping start; we enforce the length."""
    if not items:
        return None
    start = 0
    if not dry_run and len(items) > 3:
        listing = "\n".join(f"{i}. ({it.end - it.start:.0f}s) {it.text}" for i, it in enumerate(items))
        try:
            w = await ollama.chat_json(
                "Belgeselden tek başına anlaşılır, en çarpıcı 40-55 saniyelik kesiti seç. Başlangıç cümlesi merak uyandırmalı.",
                listing, Window, temperature=0.2)
            start = max(0, min(w.start_index, len(items) - 1))
        except Exception:
            start = 0
    a = items[start].start
    b = a
    for it in items[start:]:
        if it.end - a > hi:
            break
        b = it.end
    if b - a < lo:  # extend backwards if the tail was too short
        for it in reversed(items[:start]):
            if b - it.start > hi:
                break
            a = it.start
    return (a, b) if b - a >= 15 else None


def chapter_lines(chapters: list[tuple[float, str]]) -> str:
    """YouTube chapters: first at 00:00, at least 3, each >= 10 s. Returns '' when the rules can't be met."""
    if len(chapters) < 3:
        return ""
    pts = [(0.0, chapters[0][1])] + [(t, n) for t, n in chapters[1:]]
    pts = [p for i, p in enumerate(pts) if i == 0 or p[0] - pts[i - 1][0] >= 10]
    if len(pts) < 3:
        return ""

    def fmt(t: float) -> str:
        t = int(t)
        return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60:02d}:{t % 60:02d}"

    return "Bölümler\n" + "\n".join(f"{fmt(t)} {n}" for t, n in pts)


docu_runner = DocuRunner()
