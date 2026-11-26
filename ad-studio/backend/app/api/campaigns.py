from __future__ import annotations

import io
import json
import shutil
import zipfile
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..config import paths
from ..models import ACTIVE, Brand, Campaign, CampaignProduct, Product, RevenueEntry, Video, VideoStat, VideoStatus, session
from ..pipeline import insights, script as script_mod
from ..pipeline.runner import (STAGES, campaign_products, load, new_subid, product_subid, runner, tracking_url, update,
                               video_dict)

router = APIRouter(prefix="/api", tags=["campaigns"])


class CampaignIn(BaseModel):
    product_id: int = 0
    product_ids: list[int] = []  # collection (ordered); product_id used when empty
    kind: str = "single"
    collection_type: str = "top_list"
    brand_id: int | None = None
    name: str = ""
    language: str = "tr"
    tone: str = "enerjik"
    audience: str = ""
    angle_notes: str = ""
    visual_style: str = ""
    voice_id: str = ""
    variants: int = Field(3, ge=1, le=20)
    scenes: int = Field(4, ge=2, le=8)
    use_i2v: bool = False
    i2v_mode: str = "off"
    format: str = "broll"
    avatar: str = ""
    music: str = ""
    target_platform: str = "tiktok"
    angles: list[str] = []
    auto_render: bool = False


def campaign_dict(c: Campaign, s) -> dict:
    vids = s.query(Video).filter(Video.campaign_id == c.id).all()
    p = s.get(Product, c.product_id)
    b = s.get(Brand, c.brand_id) if c.brand_id else None
    rev = sum(r.amount for r in s.query(RevenueEntry).filter(
        (RevenueEntry.campaign_id == c.id) | (RevenueEntry.video_id.in_([v.id for v in vids]))).all()) if vids else 0
    return c.model_dump() | {
        "product": {"id": p.id, "name": p.name, "image_url": paths.url(p.image_path)} if p else None,
        "products": [{"id": x.id, "name": x.name, "image_url": paths.url(x.image_path)} for x in campaign_products(c)],
        "brand": {"id": b.id, "name": b.name, "logo_url": paths.url(b.logo_path), "color": b.primary_color} if b else None,
        "counts": {st.value: sum(1 for v in vids if v.status == st) for st in VideoStatus},
        "total": len(vids), "revenue": rev,
        "thumb_url": next((paths.url(v.thumb_path) for v in vids if v.thumb_path), None),
    }


@router.get("/campaigns")
def list_campaigns(brand_id: int | None = None) -> list[dict]:
    with session() as s:
        q = s.query(Campaign)
        if brand_id:
            q = q.filter(Campaign.brand_id == brand_id)
        return [campaign_dict(c, s) for c in q.order_by(Campaign.created_at.desc()).all()]


@router.get("/campaigns/{cid}")
def get_campaign(cid: int) -> dict:
    with session() as s:
        c = s.get(Campaign, cid) or _404()
        vids = s.query(Video).filter(Video.campaign_id == cid).order_by(Video.variant_index).all()
        return campaign_dict(c, s) | {"videos": [video_dict(v) for v in vids]}


@router.post("/campaigns")
def create_campaign(body: CampaignIn) -> dict:
    return get_campaign(create_campaign_service(body))


def create_campaign_service(body: CampaignIn, autopilot_id: int | None = None) -> int:
    if body.format not in ("broll", "avatar_hook", "avatar_full"):
        raise HTTPException(422, "Geçersiz format")
    if body.format != "broll" and not body.avatar:
        raise HTTPException(422, "Avatar formatı için persona seçin")
    ids_in = list(dict.fromkeys(body.product_ids or [body.product_id]))
    if body.kind == "collection" and not 2 <= len(ids_in) <= 6:
        raise HTTPException(422, "Çok ürünlü video için 2-6 ürün seçin")
    if body.kind != "collection":
        ids_in = ids_in[:1]
    with session() as s:
        prods = [s.get(Product, i) for i in ids_in]
        if not prods or not all(prods):
            _404()
        p = prods[0]
        brand_id = body.brand_id or p.brand_id
        b = s.get(Brand, brand_id) if brand_id else None
        data = body.model_dump(exclude={"angles", "auto_render", "product_ids", "product_id", "brand_id"})
        if b:  # brand defaults fill empty campaign fields
            if b.tone and body.tone in ("", "enerjik"):  # "enerjik" is the form default
                data["tone"] = b.tone
            data["audience"] = data["audience"] or b.audience
            data["voice_id"] = data["voice_id"] or b.voice_id
        c = Campaign(**data, product_id=p.id, brand_id=brand_id, autopilot_id=autopilot_id)
        if c.kind == "collection":
            c.scenes = len(prods)
        label = p.name if c.kind != "collection" else f"{len(prods)} ürün ({b.name if b else p.name})"
        c.name = c.name or f"{label} · {datetime.now():%d.%m %H:%M}"
        s.add(c)
        s.commit()
        s.refresh(c)
        for pos, x in enumerate(prods):
            s.add(CampaignProduct(campaign_id=c.id, product_id=x.id, position=pos))
        s.commit()
        known = {a[0] for a in script_mod.ANGLES}
        chosen = [a for a in body.angles if a in known]
        angles = [chosen[i % len(chosen)] for i in range(body.variants)] if chosen \
            else insights.choose_angles(body.variants, [a[0] for a in script_mod.ANGLES], seed=c.id)
        ids = []
        for i, a in enumerate(angles):
            v = Video(campaign_id=c.id, variant_index=i, angle=a, subid=new_subid(), ab_label=chr(65 + i % 26),
                      platform=body.target_platform)
            s.add(v)
            s.commit()
            s.refresh(v)
            ids.append(v.id)
    runner.enqueue(ids, STAGES if body.auto_render else ("script",))
    return c.id


@router.post("/campaigns/{cid}/render")
def render_campaign(cid: int) -> dict:
    with session() as s:
        ids = [v.id for v in s.query(Video).filter(Video.campaign_id == cid, Video.status.in_(
            [VideoStatus.scripted.value, VideoStatus.failed.value])).all()]
    if ids:
        runner.enqueue(ids, STAGES)  # script stage is a no-op for already-scripted videos
    return {"queued": ids}


@router.delete("/campaigns/{cid}")
def delete_campaign(cid: int) -> dict:
    with session() as s:
        vids = s.query(Video).filter(Video.campaign_id == cid).all()
        if any(v.status in ACTIVE for v in vids):
            raise HTTPException(409, "Kampanyada çalışan işler var.")
        for v in vids:
            _drop_video(s, v)
        for l in s.query(CampaignProduct).filter(CampaignProduct.campaign_id == cid).all():
            s.delete(l)
        s.delete(s.get(Campaign, cid) or _404())
        s.commit()
    return {"ok": True}


# ---------- videos ----------
@router.get("/videos")
def list_videos(status: str | None = None, campaign_id: int | None = None, brand_id: int | None = None,
                approval: str | None = None, limit: int = 200) -> list[dict]:
    with session() as s:
        q = s.query(Video)
        if brand_id:
            q = q.filter(Video.campaign_id.in_([c.id for c in s.query(Campaign).filter(Campaign.brand_id == brand_id).all()]))
        if approval:
            q = q.filter(Video.approval.in_(approval.split(",")))
        if status:
            q = q.filter(Video.status.in_(status.split(",")))
        if campaign_id:
            q = q.filter(Video.campaign_id == campaign_id)
        vids = q.order_by(Video.updated_at.desc()).limit(limit).all()
        camps = {c.id: c for c in s.query(Campaign).filter(Campaign.id.in_({v.campaign_id for v in vids})).all()}
        prods = {p.id: p for p in s.query(Product).filter(Product.id.in_({c.product_id for c in camps.values()})).all()}
        views: dict[int, int] = {}
        for st in s.query(VideoStat).filter(VideoStat.video_id.in_([v.id for v in vids])).all():
            views[st.video_id] = views.get(st.video_id, 0) + st.views
        brands = {b.id: b for b in s.query(Brand).all()}
    out = []
    for v in vids:
        c = camps[v.campaign_id]
        b = brands.get(c.brand_id)
        out.append(video_dict(v) | {
            "views": views.get(v.id), "campaign_name": c.name, "product_name": prods[c.product_id].name,
            "tracking_url": tracking_url(prods[c.product_id], v.subid) if c.kind != "collection" else "",
            "kind": c.kind, "product_count": len(campaign_products(c)) if c.kind == "collection" else 1,
            "brand": {"id": b.id, "name": b.name, "logo_url": paths.url(b.logo_path), "color": b.primary_color} if b else None})
    return out


@router.get("/videos/{vid}")
def get_video(vid: int) -> dict:
    v, c, p = load(vid)
    return video_dict(v) | {"campaign_name": c.name, "product_name": p.name, "tracking_url": tracking_url(p, v.subid),
                            "links": video_links(v, c)}


def video_links(v: Video, c: Campaign) -> list[dict]:
    prods = campaign_products(c)
    multi = c.kind == "collection" and len(prods) > 1
    return [{"product_id": x.id, "name": x.name, "url": tracking_url(x, product_subid(v.subid, x, multi))} for x in prods]


@router.put("/videos/{vid}/script")
def edit_script(vid: int, body: script_mod.AdScript) -> dict:
    v, _, _ = load(vid)
    if v.status in ACTIVE:
        raise HTTPException(409, "Video işleniyor.")
    return video_dict(update(vid, script_json=body.model_dump_json(), hook=body.hook,
                             caption=script_mod.full_caption(body)))


@router.post("/videos/{vid}/render")
def render_video(vid: int, full: bool = False) -> dict:
    """failed/cancelled → resume from last good stage; done/scripted → regenerate voice, visuals, compose."""
    v, _, _ = load(vid)
    if v.status in ACTIVE:
        raise HTTPException(409, "Zaten işleniyor.")
    if full or v.status in (VideoStatus.done, VideoStatus.scripted):
        stages = STAGES[1:] if v.script_json else STAGES
    else:
        stages = runner.resume_stages(vid)
    runner.enqueue([vid], stages)
    return {"ok": True, "stages": stages}


@router.post("/videos/{vid}/rescript")
def rescript(vid: int, render: bool = False) -> dict:
    v, _, _ = load(vid)
    if v.status in ACTIVE:
        raise HTTPException(409, "Zaten işleniyor.")
    update(vid, script_json="", hook="")
    runner.enqueue([vid], STAGES if render else ("script",))
    return {"ok": True}


@router.post("/videos/{vid}/revoice")
def revoice(vid: int) -> dict:
    v, c, _ = load(vid)
    if v.status in ACTIVE or not v.script_json:
        raise HTTPException(409, "Video işleniyor veya senaryosu yok.")
    # clip lengths / lip-sync depend on the voice timeline
    needs_visuals = c.format != "broll" or c.i2v_mode != "off" or c.use_i2v
    runner.enqueue([vid], ("voice", "visuals", "compose") if needs_visuals else ("voice", "compose"))
    return {"ok": True}


@router.post("/videos/{vid}/cancel")
def cancel(vid: int) -> dict:
    update(vid, status=VideoStatus.cancelled, step="İptal edildi")
    return {"ok": True}


class VideoPatch(BaseModel):
    ab_label: str | None = None
    approval: str | None = None
    approval_note: str | None = None
    favorite: bool | None = None
    platform: str | None = None
    scheduled_at: datetime | None = None
    published_at: datetime | None = None
    publish_url: str | None = None
    caption: str | None = None
    clear_schedule: bool = False


@router.patch("/videos/{vid}")
def patch_video(vid: int, body: VideoPatch) -> dict:
    if body.approval is not None and body.approval not in ("draft", "sent", "approved", "revision"):
        raise HTTPException(422, "Geçersiz onay durumu")
    kw = body.model_dump(exclude_none=True, exclude={"clear_schedule"})
    if body.publish_url is not None:
        from .youtube import yt_id_from_url
        kw["yt_id"] = yt_id_from_url(body.publish_url)
    if body.clear_schedule:
        kw["scheduled_at"] = None
    return video_dict(update(vid, **kw))


@router.delete("/videos/{vid}")
def delete_video(vid: int) -> dict:
    with session() as s:
        v = s.get(Video, vid) or _404()
        if v.status in ACTIVE:
            raise HTTPException(409, "Video işleniyor.")
        _drop_video(s, v)
        s.commit()
    return {"ok": True}


@router.get("/videos/{vid}/package")
def package(vid: int) -> StreamingResponse:
    v, c, p = load(vid)
    if not v.video_path:
        raise HTTPException(404, "Video henüz hazır değil")
    d = paths.video_dir(vid)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        z.write(v.video_path, f"{_slug(p.name)}_{v.ab_label}.mp4")
        for name in ("caption.txt", "thumb.jpg", "links.txt"):
            if (d / name).exists():
                z.write(d / name, name)
        if v.script_json:
            z.writestr("script.json", json.dumps(json.loads(v.script_json), ensure_ascii=False, indent=2))
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="adforge_{vid}.zip"'})


def _drop_video(s, v: Video) -> None:
    for r in s.query(RevenueEntry).filter(RevenueEntry.video_id == v.id).all():
        r.video_id = None
        s.add(r)
    shutil.rmtree(paths.renders / str(v.id), ignore_errors=True)
    s.delete(v)


def _slug(s: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in s.lower())[:40].strip("_") or "video"


def _404():
    raise HTTPException(404, "Bulunamadı")
