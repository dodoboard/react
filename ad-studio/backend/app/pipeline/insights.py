"""Feedback loop: what worked before steers what gets produced next."""
from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass

from ..models import RevenueEntry, Video, VideoStat, session


@dataclass
class AngleStat:
    clicks: int = 0
    conversions: int = 0
    revenue: float = 0
    views: int = 0
    retention_sum: float = 0  # sum of avg_view_pct * views
    videos: int = 0

    @property
    def retention(self) -> float | None:
        return self.retention_sum / self.views / 100 if self.views else None


def angle_stats() -> dict[str, AngleStat]:
    with session() as s:
        vids = {v.id: v for v in s.query(Video).all()}
        revs = s.query(RevenueEntry).filter(RevenueEntry.video_id.is_not(None)).all()
        stats = s.query(VideoStat).all()
    out: dict[str, AngleStat] = defaultdict(AngleStat)
    for v in vids.values():
        if v.angle:
            out[v.angle].videos += 1
    for r in revs:
        v = vids.get(r.video_id)
        if v and v.angle:
            a = out[v.angle]
            a.clicks += r.clicks
            a.conversions += r.conversions
            a.revenue += r.amount
    for st in stats:
        v = vids.get(st.video_id)
        if v and v.angle:
            a = out[v.angle]
            a.views += st.views
            a.retention_sum += st.avg_view_pct * st.views
    return dict(out)


def _sample(a: AngleStat | None, rng: random.Random) -> float:
    """Thompson sample: conversion rate if we have clicks, else retention, else prior."""
    if a and a.clicks >= 20:
        return rng.betavariate(1 + a.conversions, 1 + max(a.clicks - a.conversions, 0))
    if a and a.retention is not None and a.views >= 100:
        k = min(a.views / 100, 50)  # confidence grows with views
        return rng.betavariate(1 + k * a.retention, 1 + k * (1 - a.retention)) * 0.05  # scale to CVR range
    return rng.betavariate(1, 1) * 0.05


def choose_angles(n: int, candidates: list[str], seed: int | None = None,
                  stats: dict[str, AngleStat] | None = None) -> list[str]:
    rng = random.Random(seed)
    stats = angle_stats() if stats is None else stats
    chosen: list[str] = []
    for _ in range(n):
        pool = [c for c in candidates if c not in chosen] or candidates
        chosen.append(max(pool, key=lambda c: _sample(stats.get(c), rng)))
    return chosen


def winning_hooks(k: int = 5, exclude_campaign: int | None = None) -> list[str]:
    with session() as s:
        vids = {v.id: v for v in s.query(Video).filter(Video.hook != "").all()}
        rev: dict[int, float] = defaultdict(float)
        for r in s.query(RevenueEntry).filter(RevenueEntry.video_id.is_not(None)).all():
            rev[r.video_id] += r.amount
        ret: dict[int, float] = {}
        for st in s.query(VideoStat).all():
            if st.views >= 100:
                ret[st.video_id] = max(ret.get(st.video_id, 0), st.avg_view_pct)
    ranked = sorted((v for v in vids.values() if v.campaign_id != exclude_campaign and (rev.get(v.id) or ret.get(v.id))),
                    key=lambda v: (rev.get(v.id, 0), ret.get(v.id, 0)), reverse=True)
    seen, out = set(), []
    for v in ranked:
        if v.hook.lower() not in seen:
            seen.add(v.hook.lower())
            out.append(v.hook)
        if len(out) == k:
            break
    return out
