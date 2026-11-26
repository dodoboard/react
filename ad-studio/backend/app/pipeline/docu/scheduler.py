"""Fully automatic channel operation: keep topic backlog filled, produce episodes for upcoming slots,
upload with YouTube-native scheduling (publishAt), flip to published, pull analytics."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path

from ...config import boot
from ...events import broker
from ...models import Channel, Character, Episode, EpisodeStat, Topic, session
from ...providers import yt
from . import topics as topics_mod
from .runner import DocuRunner, ep_update

log = logging.getLogger("adforge.docu.scheduler")
DOW = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
DEAD = {"failed", "needs_review", "cancelled"}
MIN_BACKLOG = 3


def kinds(channel: Channel) -> list[str]:
    return {"long": ["long"], "shorts": ["short"], "both": ["long", "short"]}.get(channel.format, ["long"])


def schedule(channel: Channel) -> dict[str, list[tuple[str, int]]]:
    try:
        raw = json.loads(channel.schedule_json or "{}")
    except json.JSONDecodeError:
        raw = {}
    return {"long": [(d, int(h)) for d, h in raw.get("long", [])], "short": [(d, int(h)) for d, h in raw.get("shorts", [])]}


def slots(channel: Channel, kind: str, start: datetime, days: int) -> list[datetime]:
    out = []
    rules = schedule(channel)[kind]
    for i in range(days + 1):
        day = (start + timedelta(days=i)).date()
        for d, h in rules:
            if d == "*" or DOW.get(d) == day.weekday():
                t = datetime.combine(day, datetime.min.time()).replace(hour=h)
                if t > start + timedelta(minutes=45):
                    out.append(t)
    return sorted(set(out))


def produced_today(channel_id: int, today: date) -> int:
    start = datetime.combine(today, datetime.min.time())
    with session() as s:
        return s.query(Episode).filter(Episode.channel_id == channel_id, Episode.parent_id.is_(None),
                                       Episode.created_at >= start).count()


async def ensure_topics(channel: Channel) -> None:
    with session() as s:
        n = s.query(Topic).filter(Topic.channel_id == channel.id, Topic.status == "approved").count()
        ch = s.get(Character, channel.character_id) if channel.character_id else None
    if n < MIN_BACKLOG:
        await topics_mod.generate(channel, ch, 8, boot.dry_run)


async def plan(channel: Channel, now: datetime, runner: DocuRunner) -> list[int]:
    """Create episodes for free upcoming slots. Returns new episode ids."""
    created: list[int] = []
    with session() as s:
        eps = s.query(Episode).filter(Episode.channel_id == channel.id).all()
    for kind in kinds(channel):
        taken = {e.slot_at for e in eps if e.kind == kind and e.slot_at and e.status not in DEAD}
        for slot in slots(channel, kind, now, channel.lead_days):
            if slot in taken:
                continue
            if kind == "short" and channel.format == "both":
                # shorts in "both" mode are cut from long episodes: give the slot to the oldest unscheduled cut
                with session() as s:
                    cands = s.query(Episode).filter(Episode.channel_id == channel.id, Episode.kind == "short",
                                                    Episode.parent_id.is_not(None), Episode.slot_at.is_(None),
                                                    Episode.status == "ready").order_by(Episode.id).all()
                    parent_slot = {p.id: p.slot_at for p in s.query(Episode).filter(
                        Episode.id.in_([c.parent_id for c in cands])).all()} if cands else {}
                # never publish a short before the full episode it links to
                child = next((c for c in cands if parent_slot.get(c.parent_id) and parent_slot[c.parent_id] < slot), None)
                if child:
                    ep_update(child.id, slot_at=slot)
                    taken.add(slot)
                continue
            urgent = slot - now <= timedelta(hours=30)
            if not urgent and now.hour < channel.run_hour:
                continue
            if produced_today(channel.id, now.date()) >= channel.daily_cap:
                return created
            await ensure_topics(channel)
            topic = topics_mod.next_topic(channel.id)
            if not topic:
                log.info("channel %s: konu havuzu boş", channel.id)
                return created
            with session() as s:
                t = s.get(Topic, topic.id)
                t.status = "used"
                e = Episode(channel_id=channel.id, topic_id=t.id, kind=kind, slot_at=slot, title=t.title)
                s.add_all([t, e])
                s.commit()
                s.refresh(e)
            runner.enqueue(e.id)
            created.append(e.id)
            taken.add(slot)
    return created


def _upload_blocking(e: Episode, channel: Channel, parent_yt: str) -> str:
    token = yt.channel_token(channel.id)
    if not token.exists():
        if boot.dry_run:
            return f"dry{e.id:08d}"
        raise yt.YTError("Kanal YouTube'a bağlı değil")
    desc = e.description
    if parent_yt:
        desc = f"Tam belgesel ▶ https://youtu.be/{parent_yt}\n\n{desc}"
    tags = [t for t in (e.tags or "").split(",") if t] + [t.strip() for t in channel.default_tags.split(",") if t.strip()]
    return yt.upload_episode(
        token, Path(e.video_path), e.title, desc, tags, channel.category_id, channel.privacy, e.slot_at,
        Path(e.thumb_path) if e.thumb_path and e.kind == "long" else None,
        Path(e.srt_path) if e.srt_path and e.kind == "long" else None, channel.language,
        channel.playlist_id if e.kind == "long" else "")


async def publish(channel: Channel, now: datetime) -> list[int]:
    done: list[int] = []
    with session() as s:
        ready = s.query(Episode).filter(Episode.channel_id == channel.id, Episode.status == "ready",
                                        Episode.slot_at.is_not(None), Episode.yt_id == "").order_by(Episode.slot_at).all()
        parents = {p.id: p for p in s.query(Episode).filter(Episode.id.in_([e.parent_id for e in ready if e.parent_id])).all()}
    for e in ready:
        parent_yt = ""
        if e.parent_id:
            p = parents.get(e.parent_id)
            if not p or not p.yt_id:
                continue  # wait for the full episode so the short can link to it
            parent_yt = p.yt_id
        if not e.video_path:
            continue
        if yt.quota_left() < yt.EPISODE_COST and yt.channel_token(channel.id).exists():
            ep_update(e.id, step="Kota yetersiz — yarın yüklenecek")
            break
        ep_update(e.id, status="uploading", step="YouTube'a yükleniyor")
        try:
            yid = await asyncio.to_thread(_upload_blocking, e, channel, parent_yt)
        except Exception as ex:
            log.warning("upload failed for episode %s: %s", e.id, ex)
            ep_update(e.id, status="ready", step=f"Yükleme hatası: {ex}"[:200])
            continue
        when = e.slot_at if e.slot_at and e.slot_at > now else None
        ep_update(e.id, yt_id=yid, status="scheduled" if when else "published", published_at=None if when else now,
                  step=f"Planlandı: {when:%d.%m %H:%M}" if when else "Yayında")
        broker.publish("published", {"episode": e.id, "yt_id": yid, "channel": channel.name})
        done.append(e.id)
    with session() as s:
        live = s.query(Episode).filter(Episode.channel_id == channel.id, Episode.status == "scheduled",
                                       Episode.slot_at <= now).all()
    for e in live:
        ep_update(e.id, status="published", published_at=e.slot_at, step="Yayında")
    return done


async def tick(now: datetime, runner: DocuRunner) -> None:
    with session() as s:
        channels = s.query(Channel).filter(Channel.paused.is_(False)).all()
    for c in channels:
        try:
            await plan(c, now, runner)
            await publish(c, now)
        except Exception:
            log.exception("docu tick failed for channel %s", c.id)


def sync_stats_blocking(days: int = 28) -> int:
    rows = 0
    with session() as s:
        channels = s.query(Channel).all()
    for c in channels:
        token = yt.channel_token(c.id)
        if not token.exists():
            continue
        with session() as s:
            eps = [(e.id, e.yt_id) for e in s.query(Episode).filter(Episode.channel_id == c.id, Episode.yt_id != "",
                                                                     ~Episode.yt_id.startswith("dry")).all()]
        if not eps:
            continue
        yta = yt.build("youtubeAnalytics", "v2", token)
        end = date.today()
        for eid, yid in eps:
            resp = yta.reports().query(ids="channel==MINE", startDate=(end - timedelta(days=days)).isoformat(),
                                       endDate=end.isoformat(), dimensions="day",
                                       metrics="views,averageViewDuration,averageViewPercentage,likes,subscribersGained",
                                       filters=f"video=={yid}", sort="day").execute()
            rows += store_stats(eid, resp)
    return rows


def store_stats(eid: int, resp: dict) -> int:
    cols = [h["name"] for h in resp.get("columnHeaders", [])]
    data = [dict(zip(cols, r)) for r in resp.get("rows", []) or []]
    with session() as s:
        for r in data:
            day = date.fromisoformat(r["day"])
            st = s.query(EpisodeStat).filter(EpisodeStat.episode_id == eid, EpisodeStat.day == day).first() \
                or EpisodeStat(episode_id=eid, day=day)
            st.views = int(r.get("views", 0))
            st.avg_view_duration = float(r.get("averageViewDuration", 0))
            st.avg_view_pct = float(r.get("averageViewPercentage", 0))
            st.likes = int(r.get("likes", 0))
            st.subs_gained = int(r.get("subscribersGained", 0))
            s.add(st)
        s.commit()
    return len(data)
