"""Brands (clients): identity kit, billing accruals, review packages and monthly client reports."""
from __future__ import annotations

import base64
import html
import io
import uuid
import zipfile
from datetime import date, datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from PIL import Image
from pydantic import BaseModel

from ..config import paths
from ..models import Brand, BrandCharge, Campaign, Product, RevenueEntry, Video, VideoStat, VideoStatus, session
from .revenue import summary, video_cost

router = APIRouter(prefix="/api/brands", tags=["brands"])
APPROVAL = {"draft": "Taslak", "sent": "Onaya gönderildi", "approved": "Onaylandı", "revision": "Revizyon"}


class BrandIn(BaseModel):
    name: str
    primary_color: str = "#8B5CF6"
    accent_color: str = "#FFD400"
    font_file: str = ""
    voice_id: str = ""
    tone: str = ""
    audience: str = ""
    guidelines: str = ""
    banned_words: str = ""
    must_say: str = ""
    cta: str = ""
    ad_disclosure: str = ""
    hashtag: str = ""
    website: str = ""
    contact_name: str = ""
    contact_email: str = ""
    monthly_fee: float = 0
    per_video_fee: float = 0
    currency: str = "TRY"
    active: bool = True


def brand_out(b: Brand) -> dict:
    d = b.model_dump()
    d["logo_url"] = paths.url(b.logo_path)
    with session() as s:
        camps = [c.id for c in s.query(Campaign).filter(Campaign.brand_id == b.id).all()]
        d["products"] = s.query(Product).filter(Product.brand_id == b.id).count()
        d["campaigns"] = len(camps)
        vids = s.query(Video).filter(Video.campaign_id.in_(camps)).all() if camps else []
        d["videos"] = sum(v.status == VideoStatus.done for v in vids)
        d["pending_approval"] = sum(v.approval == "sent" for v in vids)
        period = date.today().strftime("%Y-%m")
        d["fees_month"] = sum(c.amount for c in s.query(BrandCharge).filter(BrandCharge.brand_id == b.id,
                                                                            BrandCharge.period == period).all())
        d["affiliate_total"] = sum(r.amount for r in s.query(RevenueEntry).filter(RevenueEntry.brand_id == b.id).all())
        d["cost_total"] = round(sum(video_cost(v) for v in vids), 2)
    return d


@router.get("")
def list_brands() -> list[dict]:
    with session() as s:
        return [brand_out(b) for b in s.query(Brand).order_by(Brand.active.desc(), Brand.name).all()]


@router.get("/{bid}")
def get_brand(bid: int) -> dict:
    with session() as s:
        return brand_out(s.get(Brand, bid) or _404())


@router.post("")
def create_brand(body: BrandIn) -> dict:
    with session() as s:
        b = Brand(**body.model_dump())
        s.add(b)
        s.commit()
        s.refresh(b)
    return brand_out(b)


@router.put("/{bid}")
def update_brand(bid: int, body: BrandIn) -> dict:
    with session() as s:
        b = s.get(Brand, bid) or _404()
        for k, v in body.model_dump().items():
            setattr(b, k, v)
        s.add(b)
        s.commit()
        s.refresh(b)
    return brand_out(b)


@router.delete("/{bid}")
def delete_brand(bid: int) -> dict:
    with session() as s:
        if s.query(Campaign).filter(Campaign.brand_id == bid).count():
            raise HTTPException(409, "Firmanın kampanyaları var — önce pasife alın veya kampanyaları silin.")
        for p in s.query(Product).filter(Product.brand_id == bid).all():
            p.brand_id = None
            s.add(p)
        for c in s.query(BrandCharge).filter(BrandCharge.brand_id == bid).all():
            s.delete(c)
        s.delete(s.get(Brand, bid) or _404())
        s.commit()
    return {"ok": True}


@router.post("/{bid}/logo")
async def upload_logo(bid: int, file: UploadFile) -> dict:
    ext = Path(file.filename or "logo.png").suffix.lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp"):
        raise HTTPException(400, "PNG/JPG/WEBP yükleyin (şeffaf PNG önerilir)")
    dst = paths.media / "brands" / f"{bid}_{uuid.uuid4().hex[:6]}{ext}"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(await file.read())
    Image.open(dst).verify()
    with session() as s:
        b = s.get(Brand, bid) or _404()
        b.logo_path = str(dst)
        s.add(b)
        s.commit()
        s.refresh(b)
    return brand_out(b)


@router.post("/{bid}/font")
async def upload_font(bid: int, file: UploadFile) -> dict:
    name = Path(file.filename or "font.ttf").name
    if Path(name).suffix.lower() not in (".ttf", ".otf"):
        raise HTTPException(400, ".ttf / .otf yükleyin")
    (paths.fonts / name).write_bytes(await file.read())
    with session() as s:
        b = s.get(Brand, bid) or _404()
        b.font_file = name
        s.add(b)
        s.commit()
        s.refresh(b)
    return brand_out(b)


@router.get("/{bid}/summary")
def brand_summary(bid: int, days: int = 30) -> dict:
    return summary(days, bid)


# ---------- billing ----------
class ChargeIn(BaseModel):
    period: str
    kind: str = "extra"
    quantity: int = 1
    amount: float
    note: str = ""


@router.get("/{bid}/charges")
def list_charges(bid: int) -> list[dict]:
    with session() as s:
        return [c.model_dump() for c in s.query(BrandCharge).filter(BrandCharge.brand_id == bid)
                .order_by(BrandCharge.period.desc(), BrandCharge.id).all()]


@router.post("/{bid}/charges")
def add_charge(bid: int, body: ChargeIn) -> dict:
    with session() as s:
        s.get(Brand, bid) or _404()
        c = BrandCharge(brand_id=bid, **body.model_dump())
        s.add(c)
        s.commit()
        s.refresh(c)
        return c.model_dump()


def videos_done_in(bid: int, period: str) -> list[Video]:
    y, m = map(int, period.split("-"))
    start = datetime(y, m, 1)
    end = datetime(y + (m == 12), m % 12 + 1, 1)
    with session() as s:
        camps = [c.id for c in s.query(Campaign).filter(Campaign.brand_id == bid).all()]
        if not camps:
            return []
        return s.query(Video).filter(Video.campaign_id.in_(camps), Video.status == VideoStatus.done,
                                     Video.updated_at >= start, Video.updated_at < end).all()


@router.post("/{bid}/charges/generate")
def generate_charges(bid: int, period: str | None = None) -> list[dict]:
    """Idempotent monthly accrual: monthly fee + per-video fee × videos finished in the period."""
    period = period or date.today().strftime("%Y-%m")
    with session() as s:
        b = s.get(Brand, bid) or _404()
        existing = {c.kind: c for c in s.query(BrandCharge).filter(BrandCharge.brand_id == bid, BrandCharge.period == period,
                                                                   BrandCharge.kind.in_(["monthly", "per_video"])).all()}
        n = len(videos_done_in(bid, period))
        wanted = {"monthly": (1, b.monthly_fee, "Aylık hizmet bedeli"),
                  "per_video": (n, n * b.per_video_fee, f"{n} video × {b.per_video_fee:g} {b.currency}")}
        for kind, (qty, amount, note) in wanted.items():
            c = existing.get(kind)
            if amount <= 0 and not c:
                continue
            if c and c.paid:
                continue  # never touch settled charges
            c = c or BrandCharge(brand_id=bid, period=period, kind=kind)
            c.quantity, c.amount, c.note = qty, round(amount, 2), note
            s.add(c)
        s.commit()
    return list_charges(bid)


@router.patch("/charges/{cid}")
def mark_charge(cid: int, paid: bool) -> dict:
    with session() as s:
        c = s.get(BrandCharge, cid) or _404()
        c.paid, c.paid_at = paid, datetime.now() if paid else None
        s.add(c)
        s.commit()
        s.refresh(c)
        return c.model_dump()


@router.delete("/charges/{cid}")
def delete_charge(cid: int) -> dict:
    with session() as s:
        s.delete(s.get(BrandCharge, cid) or _404())
        s.commit()
    return {"ok": True}


# ---------- client deliverables ----------
@router.get("/{bid}/review-package")
def review_package(bid: int, ids: str, mark_sent: bool = True) -> StreamingResponse:
    vid_ids = [int(x) for x in ids.split(",") if x.strip().isdigit()]
    with session() as s:
        b = s.get(Brand, bid) or _404()
        camps = {c.id for c in s.query(Campaign).filter(Campaign.brand_id == bid).all()}
        vids = [v for v in s.query(Video).filter(Video.id.in_(vid_ids)).all() if v.campaign_id in camps and v.video_path]
        if not vids:
            raise HTTPException(404, "Bu firmaya ait hazır video yok")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
            lines = [f"{b.name} — onay paketi ({date.today():%d.%m.%Y})", ""]
            for v in vids:
                d = paths.video_dir(v.id)
                z.write(v.video_path, f"{v.id}_{v.ab_label}.mp4")
                cap = (d / "caption.txt").read_text(encoding="utf-8") if (d / "caption.txt").exists() else v.caption
                lines += [f"#{v.id} {v.ab_label} — {v.hook}", cap, "-" * 40]
            z.writestr("aciklamalar.txt", "\n".join(lines))
        if mark_sent:
            for v in vids:
                if v.approval in ("draft", "revision"):
                    v.approval = "sent"
                    s.add(v)
            s.commit()
    buf.seek(0)
    safe = "".join(ch if ch.isalnum() else "_" for ch in b.name)[:30]
    return StreamingResponse(buf, media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="{safe}_onay.zip"'})


def _thumb_b64(p: str | None) -> str:
    if not p or not Path(p).exists():
        return ""
    im = Image.open(p).convert("RGB")
    im.thumbnail((90, 160))
    b = io.BytesIO()
    im.save(b, "JPEG", quality=70)
    return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()


def _n(v: int) -> str:
    return f"{v:,}".replace(",", ".")


def _money(v: float, cur: str) -> str:
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + f" {cur}"


@router.get("/{bid}/report", response_class=HTMLResponse)
def report(bid: int, period: str | None = None, download: bool = True) -> HTMLResponse:
    period = period or date.today().strftime("%Y-%m")
    y, m = map(int, period.split("-"))
    start, end = date(y, m, 1), date(y + (m == 12), m % 12 + 1, 1)
    with session() as s:
        b = s.get(Brand, bid) or _404()
        camps = {c.id: c for c in s.query(Campaign).filter(Campaign.brand_id == bid).all()}
        prods = {p.id: p for p in s.query(Product).all()}
        vids = [v for v in (s.query(Video).filter(Video.campaign_id.in_(list(camps))).all() if camps else [])
                if v.status == VideoStatus.done and v.updated_at and start <= v.updated_at.date() < end]
        ids = [v.id for v in vids]
        stats = s.query(VideoStat).filter(VideoStat.video_id.in_(ids), VideoStat.day >= start, VideoStat.day < end).all() if ids else []
        revs = [r for r in s.query(RevenueEntry).filter(RevenueEntry.day >= start, RevenueEntry.day < end).all()
                if r.brand_id == bid or r.video_id in ids]
        charges = s.query(BrandCharge).filter(BrandCharge.brand_id == bid, BrandCharge.period == period).all()

    per: dict[int, dict] = {v.id: {"views": 0, "ret": 0.0, "clicks": 0, "conv": 0, "rev": 0.0} for v in vids}
    for st in stats:
        per[st.video_id]["views"] += st.views
        per[st.video_id]["ret"] += st.avg_view_pct * st.views
    for r in revs:
        if r.video_id in per:
            per[r.video_id]["clicks"] += r.clicks
            per[r.video_id]["conv"] += r.conversions
            per[r.video_id]["rev"] += r.amount
    views = sum(x["views"] for x in per.values())
    ret = sum(x["ret"] for x in per.values()) / views if views else None
    clicks = sum(r.clicks for r in revs)
    conv = sum(r.conversions for r in revs)
    sales = sum(r.amount for r in revs)
    fees = sum(c.amount for c in charges)
    color = html.escape(b.primary_color or "#8B5CF6")
    e = html.escape

    rows = []
    for v in sorted(vids, key=lambda v: -per[v.id]["views"]):
        x = per[v.id]
        c = camps[v.campaign_id]
        pname = prods[c.product_id].name if c.product_id in prods else ""
        if c.kind == "collection":
            pname += " +"
        link = f'<a href="{e(v.publish_url)}">izle</a>' if v.publish_url else "—"
        thumb = _thumb_b64(v.thumb_path)
        img = f'<img src="{thumb}">' if thumb else ""
        rate = f'%{x["ret"] / x["views"]:.0f}' if x["views"] else "—"
        rows.append(
            f'<tr><td>{img}</td><td><b>{e(v.hook)}</b><div class="m">{e(pname)} · {e(v.platform or "-")} · '
            f'{APPROVAL.get(v.approval, v.approval)}</div></td><td>{_n(x["views"])}</td><td>{rate}</td>'
            f'<td>{_n(x["clicks"])}</td><td>{_n(x["conv"])}</td><td>{link}</td></tr>')
    charge_rows = "".join(f"<tr><td>{e(c.note or c.kind)}</td><td>{c.quantity}</td><td>{_money(c.amount, b.currency)}</td>"
                          f"<td>{'Ödendi' if c.paid else 'Bekliyor'}</td></tr>" for c in charges)
    logo = ""
    if b.logo_path and Path(b.logo_path).exists():
        im = Image.open(b.logo_path).convert("RGBA")
        im.thumbnail((240, 90))
        bb = io.BytesIO()
        im.save(bb, "PNG")
        logo = f'<img class="logo" src="data:image/png;base64,{base64.b64encode(bb.getvalue()).decode()}">'
    month = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"][m - 1]
    kpis = [("Yayınlanan video", str(len(vids))), ("İzlenme", _n(views)),
            ("Ort. izlenme oranı", f"%{ret:.0f}" if ret else "—"), ("Tıklama", _n(clicks)),
            ("Satış", _n(conv)), ("Ciro (affiliate)", _money(sales, b.currency))]
    doc = f"""<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(b.name)} — {month} {y} raporu</title><style>
:root{{--c:{color}}}*{{box-sizing:border-box}}body{{margin:0;font:15px/1.5 -apple-system,Segoe UI,Inter,Roboto,sans-serif;color:#15151c;background:#f4f4f8}}
.wrap{{max-width:960px;margin:0 auto;padding:32px 20px}}header{{display:flex;align-items:center;justify-content:space-between;gap:16px;
background:var(--c);color:#fff;border-radius:20px;padding:28px}}header h1{{margin:0;font-size:26px}}header p{{margin:4px 0 0;opacity:.85}}
.logo{{max-height:64px;background:#fff;border-radius:12px;padding:8px}}.k{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin:20px 0}}
.k div{{background:#fff;border-radius:16px;padding:16px;border:1px solid #e6e6ee}}.k b{{display:block;font-size:22px;margin-top:4px}}.k span{{color:#6b6b80;font-size:12px;text-transform:uppercase;letter-spacing:.06em}}
section{{background:#fff;border-radius:16px;border:1px solid #e6e6ee;padding:20px;margin-top:16px;overflow-x:auto}}h2{{margin:0 0 12px;font-size:17px}}
table{{width:100%;border-collapse:collapse}}td,th{{padding:10px 8px;border-bottom:1px solid #eee;text-align:left;vertical-align:middle}}th{{font-size:12px;color:#6b6b80;text-transform:uppercase}}
td img{{width:45px;height:80px;object-fit:cover;border-radius:8px}}.m{{color:#6b6b80;font-size:12px}}a{{color:var(--c)}}footer{{color:#8a8aa0;font-size:12px;text-align:center;margin-top:24px}}
</style></head><body><div class="wrap"><header><div><h1>{e(b.name)}</h1><p>{month} {y} performans raporu</p></div>{logo}</header>
<div class="k">{''.join(f'<div><span>{k}</span><b>{v}</b></div>' for k, v in kpis)}</div>
<section><h2>Videolar</h2><table><tr><th></th><th>Hook</th><th>İzlenme</th><th>İzlenme oranı</th><th>Tıklama</th><th>Satış</th><th></th></tr>
{''.join(rows) or '<tr><td colspan=7>Bu dönemde tamamlanan video yok.</td></tr>'}</table></section>
<section><h2>Hizmet bedeli</h2><table><tr><th>Kalem</th><th>Adet</th><th>Tutar</th><th>Durum</th></tr>{charge_rows or '<tr><td colspan=4>Tahakkuk yok.</td></tr>'}
<tr><td><b>Toplam</b></td><td></td><td><b>{_money(fees, b.currency)}</b></td><td></td></tr></table></section>
<footer>Oluşturulma: {datetime.now():%d.%m.%Y %H:%M}</footer></div></body></html>"""
    headers = {"Content-Disposition": f'attachment; filename="{"".join(ch if ch.isalnum() else "_" for ch in b.name)[:30]}_{period}_rapor.html"'} if download else {}
    return HTMLResponse(doc, headers=headers)


def _404():
    raise HTTPException(404, "Bulunamadı")
