from __future__ import annotations

import csv
import io
import re
from collections import defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel

from ..config import config
from ..models import Brand, BrandCharge, Campaign, Product, RevenueEntry, Video, VideoStat, VideoStatus, session

router = APIRouter(prefix="/api", tags=["revenue"])


class RevenueIn(BaseModel):
    day: date = date.today()
    video_id: int | None = None
    campaign_id: int | None = None
    subid: str | None = None
    product_id: int | None = None
    brand_id: int | None = None
    kind: str = "affiliate"
    platform: str = ""
    amount: float = 0
    clicks: int = 0
    conversions: int = 0
    views: int = 0
    note: str = ""


SUBID = re.compile(r"^(af[0-9a-f]{8})(?:p(\d+))?$")


def _resolve(s, body: RevenueIn) -> RevenueEntry:
    """Link a revenue row to video / product / campaign / brand. subid 'afxxxxxxxx' or 'afxxxxxxxxp<product_id>'."""
    d = body.model_dump(exclude={"subid"})
    if body.subid and not body.video_id:
        m = SUBID.match(body.subid.strip().lower())
        if m:
            v = s.query(Video).filter(Video.subid == m.group(1)).first()
            if v:
                d["video_id"] = v.id
            if m.group(2) and not d["product_id"]:
                d["product_id"] = int(m.group(2)) if s.get(Product, int(m.group(2))) else None
    if d["video_id"] and not d["campaign_id"]:
        v = s.get(Video, d["video_id"])
        d["campaign_id"] = v.campaign_id if v else None
    if d["campaign_id"]:
        c = s.get(Campaign, d["campaign_id"])
        if c:
            d["product_id"] = d["product_id"] or c.product_id
            d["brand_id"] = d["brand_id"] or c.brand_id
    if d["product_id"] and not d["brand_id"]:
        pr = s.get(Product, d["product_id"])
        d["brand_id"] = pr.brand_id if pr else None
    return RevenueEntry(**d)


@router.get("/revenue")
def list_revenue(limit: int = 500, brand_id: int | None = None) -> list[dict]:
    with session() as s:
        q = s.query(RevenueEntry)
        if brand_id:
            q = q.filter(RevenueEntry.brand_id == brand_id)
        rows = q.order_by(RevenueEntry.day.desc(), RevenueEntry.id.desc()).limit(limit).all()
        vids = {v.id: v for v in s.query(Video).filter(Video.id.in_({r.video_id for r in rows if r.video_id})).all()}
        camps = {c.id: c for c in s.query(Campaign).all()}
        prods = {p.id: p for p in s.query(Product).all()}
        brands = {b.id: b for b in s.query(Brand).all()}
        return [r.model_dump() | {"video_label": f"#{r.video_id} {vids[r.video_id].ab_label}" if r.video_id in vids else None,
                                  "campaign_name": camps[r.campaign_id].name if r.campaign_id in camps else None,
                                  "product_name": prods[r.product_id].name if r.product_id in prods else None,
                                  "brand_name": brands[r.brand_id].name if r.brand_id in brands else None}
                for r in rows]


@router.post("/revenue")
def add_revenue(body: RevenueIn) -> dict:
    with session() as s:
        r = _resolve(s, body)
        s.add(r)
        s.commit()
        s.refresh(r)
        return r.model_dump()


@router.delete("/revenue/{rid}")
def delete_revenue(rid: int) -> dict:
    with session() as s:
        r = s.get(RevenueEntry, rid)
        if not r:
            raise HTTPException(404)
        s.delete(r)
        s.commit()
    return {"ok": True}


@router.post("/revenue/import")
async def import_csv(file: UploadFile) -> dict:
    """Columns (header, any order): date|day, subid, amount|commission|revenue, clicks, conversions|orders, views, platform, note."""
    text = (await file.read()).decode("utf-8-sig", errors="ignore")
    sample = text[:2048]
    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t") if sample else csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    alias = {"date": "day", "tarih": "day", "commission": "amount", "revenue": "amount", "kazanç": "amount",
             "komisyon": "amount", "orders": "conversions", "sipariş": "conversions", "tıklama": "clicks",
             "izlenme": "views", "sub_id": "subid", "subid1": "subid"}
    added, matched = 0, 0
    with session() as s:
        for raw in reader:
            row = {alias.get(k.strip().lower(), k.strip().lower()): (v or "").strip() for k, v in raw.items() if k}
            try:
                body = RevenueIn(
                    day=_date(row.get("day")) or date.today(), subid=row.get("subid") or None,
                    amount=_f(row.get("amount")), clicks=int(_f(row.get("clicks"))), conversions=int(_f(row.get("conversions"))),
                    views=int(_f(row.get("views"))), platform=row.get("platform", ""), note=row.get("note", ""))
            except ValueError:
                continue
            r = _resolve(s, body)
            matched += bool(r.video_id)
            s.add(r)
            added += 1
        s.commit()
    return {"added": added, "matched": matched}


def _f(v: str | None) -> float:
    if not v:
        return 0.0
    v = v.replace(" ", "").replace("₺", "").replace("$", "").replace("€", "")
    if "," in v and "." in v:
        v = v.replace(".", "").replace(",", ".") if v.rfind(",") > v.rfind(".") else v.replace(",", "")
    return float(v.replace(",", "."))


def _date(v: str | None) -> date | None:
    if not v:
        return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            from datetime import datetime
            return datetime.strptime(v[:10], fmt).date()
        except ValueError:
            pass
    return None


def video_cost(v: Video) -> float:
    cfg = config.get()
    return v.tts_chars / 1000 * cfg.tts_cost_per_1k_chars + v.render_seconds / 3600 * cfg.gpu_watts / 1000 * cfg.kwh_price


@router.get("/analytics/summary")
def summary(days: int = 30, brand_id: int | None = None) -> dict:
    today = date.today()
    start = today - timedelta(days=days - 1)
    month_start = today.replace(day=1)
    with session() as s:
        vids = s.query(Video).all()
        revs = s.query(RevenueEntry).all()
        camps = {c.id: c for c in s.query(Campaign).all()}
        prods = {p.id: p for p in s.query(Product).all()}
        stats = s.query(VideoStat).all()
        brands = {b.id: b for b in s.query(Brand).all()}
        charges = s.query(BrandCharge).all()
    all_vids, all_revs = vids, revs
    if brand_id:
        camps = {k: c for k, c in camps.items() if c.brand_id == brand_id}
        vids = [v for v in vids if v.campaign_id in camps]
        vid_ids = {v.id for v in vids}
        revs = [r for r in revs if r.brand_id == brand_id or r.campaign_id in camps or r.video_id in vid_ids]
        stats = [st for st in stats if st.video_id in vid_ids]
        charges = [c for c in charges if c.brand_id == brand_id]
    period = today.strftime("%Y-%m")
    fees_month = sum(c.amount for c in charges if c.period == period)
    fees_total = sum(c.amount for c in charges)
    fees_unpaid = sum(c.amount for c in charges if not c.paid)

    series = {start + timedelta(days=i): {"revenue": 0.0, "cost": 0.0, "videos": 0, "views": 0} for i in range(days)}
    vstats: dict[int, dict] = defaultdict(lambda: {"views": 0, "ret_w": 0.0})
    for st in stats:
        if st.day in series:
            series[st.day]["views"] += st.views
        vs = vstats[st.video_id]
        vs["views"] += st.views
        vs["ret_w"] += st.avg_view_pct * st.views
    for r in revs:
        if r.day in series:
            series[r.day]["revenue"] += r.amount
    for v in vids:
        d = v.created_at.date()
        if d in series:
            series[d]["cost"] += video_cost(v)
            series[d]["videos"] += v.status == VideoStatus.done

    by_video: dict[int, dict] = defaultdict(lambda: {"revenue": 0.0, "clicks": 0, "conversions": 0, "views": 0})
    by_camp: dict[int, float] = defaultdict(float)
    by_platform: dict[str, float] = defaultdict(float)
    for r in revs:
        if r.video_id:
            b = by_video[r.video_id]
            b["revenue"] += r.amount
            b["clicks"] += r.clicks
            b["conversions"] += r.conversions
            b["views"] += r.views
        if r.campaign_id:
            by_camp[r.campaign_id] += r.amount
        by_platform[r.platform or "diğer"] += r.amount

    vmap = {v.id: v for v in vids}
    for vid, vs in vstats.items():
        by_video[vid]["views"] = max(by_video[vid]["views"], vs["views"]) if vid in by_video else vs["views"]
    retention = {vid: round(vs["ret_w"] / vs["views"], 1) for vid, vs in vstats.items() if vs["views"]}
    total_views = sum(vs["views"] for vs in vstats.values())
    hook_ret = sorted(({"id": vid, "hook": vmap[vid].hook, "retention": r, "score": vmap[vid].hook_score}
                       for vid, r in retention.items() if vid in vmap), key=lambda x: -x["retention"])[:8]
    top = sorted(by_video.items(), key=lambda kv: kv[1]["revenue"], reverse=True)[:8]
    angle_rev: dict[str, list[float]] = defaultdict(list)
    for vid, b in by_video.items():
        if vid in vmap:
            angle_rev[vmap[vid].angle].append(b["revenue"])

    camp_rows = []
    for cid, c in camps.items():
        cv = [v for v in vids if v.campaign_id == cid]
        cost = sum(video_cost(v) for v in cv)
        rev = by_camp.get(cid, 0.0)
        camp_rows.append({"id": cid, "name": c.name, "product": prods[c.product_id].name if c.product_id in prods else "",
                          "videos": len(cv), "revenue": round(rev, 2), "cost": round(cost, 2),
                          "roi": round((rev - cost) / cost * 100, 1) if cost >= 1 else None})

    total_cost = sum(video_cost(v) for v in vids)
    total_rev = sum(r.amount for r in revs)
    month_rev = sum(r.amount for r in revs if r.day >= month_start)
    return {
        "currency": config.get().currency,
        "kpi": {
            "month_revenue": round(month_rev, 2), "total_revenue": round(total_rev, 2), "total_cost": round(total_cost, 2),
            "roi": round((total_rev - total_cost) / total_cost * 100, 1) if total_cost >= 1 else None,
            "videos_done": sum(v.status == VideoStatus.done for v in vids),
            "videos_active": sum(v.status not in (VideoStatus.done, VideoStatus.failed, VideoStatus.cancelled, VideoStatus.scripted) for v in vids),
            "published": sum(bool(v.published_at) for v in vids),
            "scheduled": sum(bool(v.scheduled_at and not v.published_at) for v in vids),
            "clicks": sum(r.clicks for r in revs), "conversions": sum(r.conversions for r in revs),
            "views": total_views,
            "avg_retention": round(sum(vs["ret_w"] for vs in vstats.values()) / total_views, 1) if total_views else None,
            "rpm": round(total_rev / total_views * 1000, 2) if total_views else None,
        },
        "hook_retention": hook_ret,
        "fees": {"month": round(fees_month, 2), "total": round(fees_total, 2), "unpaid": round(fees_unpaid, 2)},
        "profit": round(total_rev + fees_total - total_cost, 2),
        "by_brand": brand_rows(brands, all_vids, all_revs),
        "series": [{"day": d.isoformat(), **{k: round(x, 2) if isinstance(x, float) else x for k, x in val.items()}}
                   for d, val in series.items()],
        "top_videos": [{"id": vid, "hook": vmap[vid].hook, "label": vmap[vid].ab_label, "angle": vmap[vid].angle,
                        "thumb": vmap[vid].thumb_path and f"/media/renders/{vid}/thumb.jpg",
                        "retention": retention.get(vid), **b}
                       for vid, b in top if vid in vmap],
        "angles": sorted([{"angle": a, "avg": round(sum(x) / len(x), 2), "videos": len(x)} for a, x in angle_rev.items()],
                         key=lambda r: r["avg"], reverse=True),
        "platforms": [{"platform": k, "revenue": round(v, 2)} for k, v in sorted(by_platform.items(), key=lambda kv: -kv[1])],
        "campaigns": sorted(camp_rows, key=lambda r: r["revenue"], reverse=True),
    }


def brand_rows(brands: dict, vids: list, revs: list) -> list[dict]:
    with session() as s:
        camp_brand = {c.id: c.brand_id for c in s.query(Campaign).all()}
        all_charges = s.query(BrandCharge).all()
    out = []
    for bid, b in brands.items():
        bv = [v for v in vids if camp_brand.get(v.campaign_id) == bid]
        aff = sum(r.amount for r in revs if r.brand_id == bid)
        fees = sum(c.amount for c in all_charges if c.brand_id == bid)
        cost = sum(video_cost(v) for v in bv)
        out.append({"id": bid, "name": b.name, "color": b.primary_color, "videos": len(bv), "affiliate": round(aff, 2),
                    "fees": round(fees, 2), "cost": round(cost, 2), "profit": round(aff + fees - cost, 2)})
    return sorted(out, key=lambda r: -r["profit"])
