"""Autopilot: daily campaigns from a product pool, ROI-weighted with exploration, auto-scheduled into peak slots."""
from __future__ import annotations

import logging
import math
import random
from collections import defaultdict
from datetime import date, datetime, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..models import AutopilotRule, Campaign, Product, RevenueEntry, Video, VideoStatus, session
from .campaigns import CampaignIn, create_campaign_service

router = APIRouter(prefix="/api/autopilot", tags=["autopilot"])
log = logging.getLogger("adforge.autopilot")
BEST_HOURS = (12, 19, 21)
EXPLORE = 0.2


class RuleIn(BaseModel):
    name: str = "Otopilot"
    enabled: bool = True
    product_ids: list[int] = []
    videos_per_day: int = 3
    run_hour: int = 2
    platform: str = "tiktok"
    language: str = "tr"
    format: str = "broll"
    avatar: str = ""
    i2v_mode: str = "off"
    auto_schedule: bool = True


def rule_dict(r: AutopilotRule) -> dict:
    d = r.model_dump()
    d["product_ids"] = [int(x) for x in r.product_ids.split(",") if x]
    with session() as s:
        camps = s.query(Campaign).filter(Campaign.autopilot_id == r.id).all()
        ids = [c.id for c in camps]
        d["campaigns"] = len(camps)
        d["videos"] = s.query(Video).filter(Video.campaign_id.in_(ids)).count() if ids else 0
    return d


def _apply(r: AutopilotRule, body: RuleIn) -> None:
    if not 1 <= body.videos_per_day <= 30 or not 0 <= body.run_hour <= 23:
        raise HTTPException(422, "Günlük video 1-30, saat 0-23 olmalı")
    for k, v in body.model_dump(exclude={"product_ids"}).items():
        setattr(r, k, v)
    r.product_ids = ",".join(str(i) for i in body.product_ids)


@router.get("")
def list_rules() -> list[dict]:
    with session() as s:
        return [rule_dict(r) for r in s.query(AutopilotRule).order_by(AutopilotRule.id).all()]


@router.post("")
def create_rule(body: RuleIn) -> dict:
    with session() as s:
        r = AutopilotRule()
        _apply(r, body)
        s.add(r)
        s.commit()
        s.refresh(r)
    return rule_dict(r)


@router.put("/{rid}")
def update_rule(rid: int, body: RuleIn) -> dict:
    with session() as s:
        r = s.get(AutopilotRule, rid) or _404()
        _apply(r, body)
        s.add(r)
        s.commit()
        s.refresh(r)
    return rule_dict(r)


@router.delete("/{rid}")
def delete_rule(rid: int) -> dict:
    with session() as s:
        s.delete(s.get(AutopilotRule, rid) or _404())
        s.commit()
    return {"ok": True}


@router.post("/{rid}/run")
def run_now(rid: int) -> dict:
    with session() as s:
        r = s.get(AutopilotRule, rid) or _404()
    return {"campaigns": run_rule(r)}


def product_scores() -> dict[int, float]:
    """Revenue per produced video, smoothed (new products are not starved)."""
    with session() as s:
        camp_prod = {c.id: c.product_id for c in s.query(Campaign).all()}
        vids = s.query(Video).filter(Video.status == VideoStatus.done).all()
        revs = s.query(RevenueEntry).all()
    count: dict[int, int] = defaultdict(int)
    vid_prod = {}
    for v in vids:
        pid = camp_prod.get(v.campaign_id)
        vid_prod[v.id] = pid
        count[pid] += 1
    rev: dict[int, float] = defaultdict(float)
    for r in revs:
        pid = vid_prod.get(r.video_id) if r.video_id else camp_prod.get(r.campaign_id)
        if pid:
            rev[pid] += r.amount
    return {pid: (rev[pid] + 50) / (count[pid] + 1) for pid in set(count) | set(rev)}


def pick_products(pool: list[Product], k: int, rng: random.Random) -> list[Product]:
    scores = product_scores()
    chosen: list[Product] = []
    remaining = pool[:]
    while remaining and len(chosen) < k:
        if rng.random() < EXPLORE:
            p = rng.choice(remaining)
        else:
            weights = [scores.get(p.id, 50.0) for p in remaining]
            p = rng.choices(remaining, weights=weights)[0]
        chosen.append(p)
        remaining.remove(p)
    return chosen


def run_rule(r: AutopilotRule, rng: random.Random | None = None) -> list[int]:
    rng = rng or random.Random()
    ids = [int(x) for x in r.product_ids.split(",") if x]
    with session() as s:
        q = s.query(Product).filter(Product.id.in_(ids)) if ids else s.query(Product).filter(Product.active.is_(True))
        pool = [p for p in q.all() if p.image_path]
    if not pool:
        log.warning("autopilot %s: ürün havuzu boş (görselli ürün yok)", r.id)
        return []
    k = min(len(pool), max(1, math.ceil(r.videos_per_day / 3)))
    products = pick_products(pool, k, rng)
    per = [r.videos_per_day // k + (1 if i < r.videos_per_day % k else 0) for i in range(k)]
    created = []
    for p, n in zip(products, per):
        if n <= 0:
            continue
        body = CampaignIn(product_id=p.id, name=f"Otopilot · {p.name} · {date.today():%d.%m}", language=r.language,
                          variants=n, target_platform=r.platform, format=r.format, avatar=r.avatar,
                          i2v_mode=r.i2v_mode, auto_render=True)
        created.append(create_campaign_service(body, autopilot_id=r.id))
    with session() as s:
        rr = s.get(AutopilotRule, r.id)
        if rr:
            rr.last_run = date.today()
            s.add(rr)
            s.commit()
    return created


def due_rules(now: datetime) -> list[AutopilotRule]:
    with session() as s:
        return [r for r in s.query(AutopilotRule).filter(AutopilotRule.enabled.is_(True)).all()
                if now.hour >= r.run_hour and r.last_run != now.date()]


def next_slots(taken: set[datetime], start: datetime, n: int) -> list[datetime]:
    out, day = [], start.date()
    while len(out) < n:
        for h in BEST_HOURS:
            t = datetime.combine(day, datetime.min.time()).replace(hour=h)
            if t > start + timedelta(minutes=30) and t not in taken:
                out.append(t)
                taken.add(t)
                if len(out) == n:
                    break
        day += timedelta(days=1)
    return out


def auto_schedule(now: datetime) -> int:
    """Put finished autopilot videos into free peak slots."""
    with session() as s:
        rules = {r.id: r for r in s.query(AutopilotRule).filter(AutopilotRule.auto_schedule.is_(True)).all()}
        if not rules:
            return 0
        camps = {c.id: c for c in s.query(Campaign).filter(Campaign.autopilot_id.in_(list(rules))).all()}
        if not camps:
            return 0
        todo = s.query(Video).filter(Video.campaign_id.in_(list(camps)), Video.status == VideoStatus.done,
                                     Video.scheduled_at.is_(None), Video.published_at.is_(None)).order_by(Video.hook_score.desc()).all()
        taken = {v.scheduled_at for v in s.query(Video).filter(Video.scheduled_at.is_not(None)).all()}
        slots = next_slots(taken, now, len(todo))
        for v, t in zip(todo, slots):
            v.scheduled_at = t
            v.platform = rules[camps[v.campaign_id].autopilot_id].platform
            s.add(v)
        s.commit()
        return len(todo)


def _404():
    raise HTTPException(404, "Bulunamadı")
