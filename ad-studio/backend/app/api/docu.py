"""Documentary channels API: characters, channels (per-channel YouTube OAuth), topic backlog, episodes, quota."""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import date, datetime, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..config import boot, paths
from ..models import Channel, Character, Episode, EpisodeStat, Topic, session
from ..pipeline.docu import topics as topics_mod
from ..pipeline.docu.runner import ACTIVE, docu_runner, ep_dict, ep_dir, ep_update
from ..pipeline.docu.scheduler import _upload_blocking, kinds, slots
from ..providers import ollama, tts, yt

router = APIRouter(prefix="/api/docu", tags=["documentary"])


# ---------- characters ----------
class CharacterIn(BaseModel):
    name: str
    persona: str = ""
    speaking_style: str = ""
    catchphrases: str = ""
    opening_line: str = ""
    closing_line: str = ""
    look_prompt: str = ""
    avatar: str = ""
    voice_id: str = ""
    language: str = "tr"


def char_out(c: Character) -> dict:
    d = c.model_dump()
    d["avatar_url"] = paths.url(paths.avatars / c.avatar) if c.avatar and (paths.avatars / c.avatar).exists() else None
    with session() as s:
        d["channels"] = s.query(Channel).filter(Channel.character_id == c.id).count()
    return d


@router.get("/characters")
def list_characters() -> list[dict]:
    with session() as s:
        return [char_out(c) for c in s.query(Character).order_by(Character.id).all()]


@router.post("/characters")
def create_character(body: CharacterIn) -> dict:
    with session() as s:
        c = Character(**body.model_dump())
        s.add(c)
        s.commit()
        s.refresh(c)
    return char_out(c)


@router.put("/characters/{cid}")
def update_character(cid: int, body: CharacterIn) -> dict:
    with session() as s:
        c = s.get(Character, cid) or _404()
        for k, v in body.model_dump().items():
            setattr(c, k, v)
        s.add(c)
        s.commit()
        s.refresh(c)
    return char_out(c)


@router.delete("/characters/{cid}")
def delete_character(cid: int) -> dict:
    with session() as s:
        if s.query(Channel).filter(Channel.character_id == cid).count():
            raise HTTPException(409, "Bu karakteri kullanan kanallar var")
        s.delete(s.get(Character, cid) or _404())
        s.commit()
    return {"ok": True}


class PersonaIn(BaseModel):
    niche: str
    name: str = ""
    vibe: str = ""
    language: str = "tr"


class PersonaOut(BaseModel):
    name: str
    persona: str = Field(description="3-4 cümlelik kurgusal biyografi ve uzmanlık")
    speaking_style: str = Field(description="Konuşma tarzı: tempo, ton, hitap")
    catchphrases: str = Field(description="2-3 kısa imza ifade, virgülle")
    opening_line: str = Field(description="Her bölümün imza açılış cümlesi")
    closing_line: str = Field(description="Her bölümün imza kapanış cümlesi")
    look_prompt: str = Field(description="English: consistent visual description for image generation (age, face, hair, outfit, setting)")


@router.post("/characters/generate")
async def generate_persona(body: PersonaIn) -> dict:
    if boot.dry_run:
        return PersonaOut(name=body.name or "Deniz Arda", persona=f"{body.niche} meraklısı kurgusal bir araştırmacı-anlatıcı.",
                          speaking_style="Sakin, sıcak, merak uyandıran; izleyiciye 'siz' diye hitap eder.",
                          catchphrases="Gelin birlikte bakalım, Asıl soru şu", opening_line="Hoş geldiniz, ben Deniz.",
                          closing_line="Merakınız hiç bitmesin.",
                          look_prompt="a 35 year old documentary presenter, short dark hair, warm eyes, olive field jacket, "
                                      "library background").model_dump()
    p = await ollama.chat_json(
        "Sen YouTube belgesel kanalları için kurgusal sunucu karakterler tasarlıyorsun. Gerçek bir kişiyi taklit etme. "
        "Karakter güven veren, akılda kalıcı ve konuya hizmet eden biri olsun. Yalnızca JSON döndür.",
        f"Niş: {body.niche}\nİsim (varsa): {body.name}\nHava: {body.vibe}\nDil: {body.language}", PersonaOut)
    return p.model_dump()


class PreviewIn(BaseModel):
    text: str = ""


@router.post("/characters/{cid}/preview")
async def preview_voice(cid: int, body: PreviewIn) -> dict:
    with session() as s:
        c = s.get(Character, cid) or _404()
    text = body.text or c.opening_line or f"Merhaba, ben {c.name}. Bugün sizi çok eski bir hikâyeye götüreceğim."
    out = paths.media / "previews" / f"char_{cid}_{uuid.uuid4().hex[:6]}.mp3"
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        await tts.synthesize(text[:400], out, c.language, c.voice_id or None, boot.dry_run)
    except Exception as e:
        raise HTTPException(502, f"Ses önizleme başarısız: {e}") from e
    return {"url": paths.url(out)}


# ---------- channels ----------
class ChannelIn(BaseModel):
    name: str
    niche: str = ""
    language: str = "tr"
    character_id: int | None = None
    format: str = "both"
    target_minutes: float = 8
    visual_style: str = "cinematic documentary photography, natural light, rich detail, 35mm film look"
    music: str = ""
    privacy: str = "public"
    category_id: str = "27"
    default_tags: str = ""
    playlist_id: str = ""
    schedule_json: str = '{"long": [["tue", 19], ["fri", 19]], "shorts": [["*", 12]]}'
    lead_days: int = 2
    daily_cap: int = 3
    min_quality: float = 7.0
    paused: bool = False
    run_hour: int = 1


def _validate(body: ChannelIn) -> None:
    if body.format not in ("long", "shorts", "both"):
        raise HTTPException(422, "Format long/shorts/both olmalı")
    if not 1 <= body.target_minutes <= 30:
        raise HTTPException(422, "Süre 1-30 dk")
    if body.privacy not in ("public", "unlisted", "private"):
        raise HTTPException(422, "Gizlilik geçersiz")
    try:
        sch = json.loads(body.schedule_json)
        for k in ("long", "shorts"):
            for d, h in sch.get(k, []):
                assert d in ("*", "mon", "tue", "wed", "thu", "fri", "sat", "sun") and 0 <= int(h) <= 23
    except Exception as e:
        raise HTTPException(422, "Takvim biçimi geçersiz") from e


def channel_out(c: Channel) -> dict:
    d = c.model_dump()
    now = datetime.now()
    with session() as s:
        eps = s.query(Episode).filter(Episode.channel_id == c.id).all()
        ch = s.get(Character, c.character_id) if c.character_id else None
        backlog = s.query(Topic).filter(Topic.channel_id == c.id, Topic.status == "approved").count()
        views = sum(st.views for st in s.query(EpisodeStat).filter(EpisodeStat.episode_id.in_([e.id for e in eps])).all()) if eps else 0
    upcoming = sorted([e for e in eps if e.slot_at and e.slot_at > now and e.status not in ("failed", "needs_review")],
                      key=lambda e: e.slot_at)
    d |= {
        "character": char_out(ch) if ch else None,
        "connected": yt.channel_token(c.id).exists(),
        "backlog": backlog,
        "episodes": len(eps),
        "published": sum(e.status == "published" for e in eps),
        "in_production": sum(e.status in ACTIVE for e in eps),
        "needs_review": sum(e.status == "needs_review" for e in eps),
        "next": ep_dict(upcoming[0]) if upcoming else None,
        "next_slots": [t.isoformat() for k in kinds(c) for t in slots(c, k, now, 7)][:8],
        "views": views,
    }
    return d


@router.get("/channels")
def list_channels() -> list[dict]:
    with session() as s:
        return [channel_out(c) for c in s.query(Channel).order_by(Channel.id).all()]


@router.get("/channels/{cid}")
def get_channel(cid: int) -> dict:
    with session() as s:
        return channel_out(s.get(Channel, cid) or _404())


@router.post("/channels")
def create_channel(body: ChannelIn) -> dict:
    _validate(body)
    with session() as s:
        c = Channel(**body.model_dump())
        s.add(c)
        s.commit()
        s.refresh(c)
    return channel_out(c)


@router.put("/channels/{cid}")
def update_channel(cid: int, body: ChannelIn) -> dict:
    _validate(body)
    with session() as s:
        c = s.get(Channel, cid) or _404()
        for k, v in body.model_dump().items():
            setattr(c, k, v)
        s.add(c)
        s.commit()
        s.refresh(c)
    return channel_out(c)


@router.delete("/channels/{cid}")
def delete_channel(cid: int) -> dict:
    with session() as s:
        if s.query(Episode).filter(Episode.channel_id == cid, Episode.status.in_(list(ACTIVE))).count():
            raise HTTPException(409, "Üretimde bölüm var")
        for e in s.query(Episode).filter(Episode.channel_id == cid).all():
            for st in s.query(EpisodeStat).filter(EpisodeStat.episode_id == e.id).all():
                s.delete(st)
            s.delete(e)
        for t in s.query(Topic).filter(Topic.channel_id == cid).all():
            s.delete(t)
        s.delete(s.get(Channel, cid) or _404())
        s.commit()
    yt.channel_token(cid).unlink(missing_ok=True)
    return {"ok": True}


@router.post("/channels/{cid}/pause")
def pause(cid: int, paused: bool) -> dict:
    with session() as s:
        c = s.get(Channel, cid) or _404()
        c.paused = paused
        s.add(c)
        s.commit()
        s.refresh(c)
    return channel_out(c)


@router.post("/channels/{cid}/connect")
async def connect(cid: int) -> dict:
    with session() as s:
        s.get(Channel, cid) or _404()
    try:
        await asyncio.to_thread(yt.run_flow, yt.channel_token(cid))
        info = await asyncio.to_thread(yt.channel_info, yt.channel_token(cid))
    except (yt.YTError, ImportError) as e:
        raise HTTPException(400, str(e)) from e
    return {"connected": True, "channel": info}


@router.get("/channels/{cid}/youtube")
async def yt_info(cid: int) -> dict:
    token = yt.channel_token(cid)
    if not token.exists():
        return {"connected": False}
    try:
        return {"connected": True, "channel": await asyncio.to_thread(yt.channel_info, token)}
    except Exception as e:
        return {"connected": True, "error": str(e)[:200]}


@router.get("/channels/{cid}/stats")
def channel_stats(cid: int, days: int = 28) -> dict:
    start = date.today() - timedelta(days=days - 1)
    with session() as s:
        eps = {e.id: e for e in s.query(Episode).filter(Episode.channel_id == cid).all()}
        stats = s.query(EpisodeStat).filter(EpisodeStat.episode_id.in_(list(eps)), EpisodeStat.day >= start).all() if eps else []
    series = {start + timedelta(days=i): 0 for i in range(days)}
    per: dict[int, dict] = {}
    for st in stats:
        series[st.day] = series.get(st.day, 0) + st.views
        p = per.setdefault(st.episode_id, {"views": 0, "w": 0.0})
        p["views"] += st.views
        p["w"] += st.avg_view_pct * st.views
    top = sorted(per.items(), key=lambda kv: -kv[1]["views"])[:10]
    return {"series": [{"day": d.isoformat(), "views": v} for d, v in series.items()],
            "top": [{"id": eid, "title": eps[eid].title, "kind": eps[eid].kind, "views": p["views"],
                     "retention": round(p["w"] / p["views"], 1) if p["views"] else None} for eid, p in top]}


# ---------- topics ----------
@router.get("/channels/{cid}/topics")
def list_topics(cid: int) -> list[dict]:
    with session() as s:
        return [t.model_dump() for t in s.query(Topic).filter(Topic.channel_id == cid)
                .order_by(Topic.status, Topic.score.desc()).all()]


@router.post("/channels/{cid}/topics/generate")
async def gen_topics(cid: int, n: int = 10) -> list[dict]:
    with session() as s:
        c = s.get(Channel, cid) or _404()
        ch = s.get(Character, c.character_id) if c.character_id else None
    out = await topics_mod.generate(c, ch, max(1, min(n, 20)), boot.dry_run)
    return [t.model_dump() for t in out]


class TopicPatch(BaseModel):
    status: str | None = None
    title: str | None = None


@router.patch("/topics/{tid}")
def patch_topic(tid: int, body: TopicPatch) -> dict:
    with session() as s:
        t = s.get(Topic, tid) or _404()
        if body.status:
            if body.status not in ("idea", "approved", "rejected"):
                raise HTTPException(422, "Geçersiz durum")
            if body.status == "approved" and t.sensitive:
                raise HTTPException(409, f"Hassas konu onaylanamaz: {t.sensitive_reason}")
            t.status = body.status
        if body.title:
            t.title = body.title
        s.add(t)
        s.commit()
        s.refresh(t)
        return t.model_dump()


class TopicIn(BaseModel):
    title: str
    angle: str = ""


@router.post("/channels/{cid}/topics")
def add_topic(cid: int, body: TopicIn) -> dict:
    flag = topics_mod.keyword_flag(f"{body.title} {body.angle}")
    with session() as s:
        s.get(Channel, cid) or _404()
        t = Topic(channel_id=cid, title=body.title, angle=body.angle, score=7, sensitive=bool(flag),
                  sensitive_reason=flag or "", status="rejected" if flag else "approved")
        s.add(t)
        s.commit()
        s.refresh(t)
        return t.model_dump()


# ---------- episodes ----------
@router.get("/episodes")
def list_episodes(channel_id: int | None = None, limit: int = 200) -> list[dict]:
    with session() as s:
        q = s.query(Episode)
        if channel_id:
            q = q.filter(Episode.channel_id == channel_id)
        return [ep_dict(e) for e in q.order_by(Episode.id.desc()).limit(limit).all()]


@router.get("/episodes/{eid}")
def get_episode(eid: int) -> dict:
    with session() as s:
        e = s.get(Episode, eid) or _404()
    d = ep_dict(e)
    d["script"] = json.loads(e.script_json) if e.script_json else None
    d["outline"] = json.loads(e.outline_json) if e.outline_json else None
    d["srt_url"] = paths.url(e.srt_path)
    return d


class EpisodeIn(BaseModel):
    topic_id: int | None = None
    kind: str = "long"
    slot_at: datetime | None = None


@router.post("/channels/{cid}/episodes")
def create_episode(cid: int, body: EpisodeIn) -> dict:
    with session() as s:
        c = s.get(Channel, cid) or _404()
        if body.kind not in ("long", "short"):
            raise HTTPException(422, "kind long/short")
        t = s.get(Topic, body.topic_id) if body.topic_id else topics_mod.next_topic(cid)
        if not t:
            raise HTTPException(409, "Onaylı konu yok — önce konu üretin")
        if t.sensitive:
            raise HTTPException(409, "Hassas konu")
        t = s.get(Topic, t.id)
        t.status = "used"
        e = Episode(channel_id=c.id, topic_id=t.id, kind=body.kind, slot_at=body.slot_at, title=t.title)
        s.add_all([t, e])
        s.commit()
        s.refresh(e)
    docu_runner.enqueue(e.id)
    return ep_dict(e)


@router.post("/episodes/{eid}/retry")
def retry(eid: int, full: bool = False) -> dict:
    with session() as s:
        e = s.get(Episode, eid) or _404()
    if e.status in ACTIVE:
        raise HTTPException(409, "Zaten üretimde")
    if full:
        ep_update(eid, stage_done="", outline_json="", script_json="")
    docu_runner.enqueue(eid, None if full else docu_runner.resume_stages(eid))
    return {"ok": True}


@router.post("/episodes/{eid}/approve")
def approve(eid: int) -> dict:
    """Manual override for needs_review: continue production from the voice stage."""
    with session() as s:
        e = s.get(Episode, eid) or _404()
    if e.status != "needs_review":
        raise HTTPException(409, "Yalnızca incelemedeki bölümler")
    ep_update(eid, stage_done="gate", error="")
    docu_runner.enqueue(eid, docu_runner.resume_stages(eid))
    return {"ok": True}


@router.post("/episodes/{eid}/cancel")
def cancel(eid: int) -> dict:
    ep_update(eid, status="cancelled", step="İptal edildi")
    return {"ok": True}


@router.post("/episodes/{eid}/publish-now")
async def publish_now(eid: int) -> dict:
    with session() as s:
        e = s.get(Episode, eid) or _404()
        c = s.get(Channel, e.channel_id)
        parent = s.get(Episode, e.parent_id) if e.parent_id else None
    if e.status != "ready" or e.yt_id:
        raise HTTPException(409, "Bölüm yayına hazır değil veya zaten yüklendi")
    e.slot_at = None
    try:
        yid = await asyncio.to_thread(_upload_blocking, e, c, parent.yt_id if parent else "")
    except Exception as ex:
        raise HTTPException(502, str(ex)) from ex
    ep_update(eid, yt_id=yid, status="published", published_at=datetime.now(), step="Yayında")
    return {"yt_id": yid}


@router.delete("/episodes/{eid}")
def delete_episode(eid: int) -> dict:
    import shutil
    with session() as s:
        e = s.get(Episode, eid) or _404()
        if e.status in ACTIVE:
            raise HTTPException(409, "Üretimde")
        for st in s.query(EpisodeStat).filter(EpisodeStat.episode_id == eid).all():
            s.delete(st)
        s.delete(e)
        s.commit()
    shutil.rmtree(ep_dir(eid), ignore_errors=True)
    return {"ok": True}


@router.get("/quota")
def quota() -> dict:
    from ..config import config
    return {"used": yt.quota_used(), "limit": config.get().youtube_daily_quota, "episode_cost": yt.EPISODE_COST,
            "uploads_left": max(0, yt.quota_left() // yt.EPISODE_COST)}


@router.get("/upcoming")
def upcoming(limit: int = 8) -> list[dict]:
    now = datetime.now()
    with session() as s:
        eps = s.query(Episode).filter(Episode.slot_at.is_not(None), Episode.slot_at > now,
                                      Episode.status.notin_(["failed", "needs_review", "cancelled"])) \
            .order_by(Episode.slot_at).limit(limit).all()
        chans = {c.id: c.name for c in s.query(Channel).all()}
    return [ep_dict(e) | {"channel_name": chans.get(e.channel_id, "")} for e in eps]


def _404():
    raise HTTPException(404, "Bulunamadı")

