from __future__ import annotations

import html
import json
import re
import uuid
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel, Field

from ..config import boot, paths
from ..models import Campaign, Product, session
from ..providers import ollama

router = APIRouter(prefix="/api/products", tags=["products"])
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"


class ProductIn(BaseModel):
    name: str
    description: str = ""
    features: str = ""
    price: float | None = None
    currency: str = "TRY"
    affiliate_url: str = ""
    platform: str = ""
    commission_rate: float | None = None
    image_path: str | None = None


def out(p: Product) -> dict:
    d = p.model_dump()
    d["image_url"] = paths.url(p.image_path)
    return d


@router.get("")
def list_products() -> list[dict]:
    with session() as s:
        return [out(p) for p in s.query(Product).order_by(Product.created_at.desc()).all()]


@router.post("")
def create(body: ProductIn) -> dict:
    with session() as s:
        p = Product(**body.model_dump())
        s.add(p)
        s.commit()
        s.refresh(p)
        return out(p)


@router.put("/{pid}")
def edit(pid: int, body: ProductIn) -> dict:
    with session() as s:
        p = s.get(Product, pid) or _404()
        for k, v in body.model_dump().items():
            setattr(p, k, v)
        s.add(p)
        s.commit()
        s.refresh(p)
        return out(p)


@router.delete("/{pid}")
def delete(pid: int) -> dict:
    with session() as s:
        if s.query(Campaign).filter(Campaign.product_id == pid).count():
            raise HTTPException(409, "Bu ürüne bağlı kampanyalar var.")
        p = s.get(Product, pid) or _404()
        s.delete(p)
        s.commit()
    return {"ok": True}


@router.post("/{pid}/image")
async def upload_image(pid: int, file: UploadFile) -> dict:
    ext = Path(file.filename or "x.png").suffix.lower() or ".png"
    if ext not in (".png", ".jpg", ".jpeg", ".webp"):
        raise HTTPException(400, "Desteklenmeyen görsel türü")
    dst = paths.products / f"{pid}_{uuid.uuid4().hex[:8]}{ext}"
    dst.write_bytes(await file.read())
    with session() as s:
        p = s.get(Product, pid) or _404()
        p.image_path = str(dst)
        s.add(p)
        s.commit()
        s.refresh(p)
        return out(p)


class AutofillIn(BaseModel):
    url: str


class Extracted(BaseModel):
    name: str
    description: str = Field(description="2-3 cümlelik tarafsız ürün açıklaması, Türkçe")
    features: list[str] = Field(description="3-7 somut ürün özelliği, kısa, Türkçe")


def _meta(page: str, prop: str) -> str | None:
    m = re.search(rf'<meta[^>]+(?:property|name)=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']+)', page, re.I) or \
        re.search(rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']{re.escape(prop)}["\']', page, re.I)
    return html.unescape(m.group(1)).strip() if m else None


def _jsonld_product(page: str) -> dict:
    for block in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', page, re.S | re.I):
        try:
            data = json.loads(block.strip())
        except json.JSONDecodeError:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            d = stack.pop()
            if isinstance(d, dict):
                if d.get("@type") in ("Product", ["Product"]):
                    return d
                stack.extend(v for v in d.values() if isinstance(v, (dict, list)))
            elif isinstance(d, list):
                stack.extend(d)
    return {}


@router.post("/autofill")
async def autofill(body: AutofillIn) -> dict:
    async with httpx.AsyncClient(follow_redirects=True, timeout=20, headers={"User-Agent": UA, "Accept-Language": "tr-TR,tr;q=0.9"}) as c:
        try:
            r = await c.get(body.url)
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise HTTPException(502, f"Sayfa alınamadı: {e}") from e
        page = r.text
        ld = _jsonld_product(page)
        offers = ld.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        img = ld.get("image")
        img = (img[0] if isinstance(img, list) and img else img.get("url") if isinstance(img, dict) else img) or _meta(page, "og:image")
        title = ld.get("name") or _meta(page, "og:title") or (re.search(r"<title>(.*?)</title>", page, re.S | re.I) or [None, ""])[1]
        desc = ld.get("description") or _meta(page, "og:description") or _meta(page, "description") or ""
        price = offers.get("price") or offers.get("lowPrice") or _meta(page, "product:price:amount")
        currency = offers.get("priceCurrency") or _meta(page, "product:price:currency") or "TRY"
        result = {"name": html.unescape(str(title)).strip()[:160], "description": str(desc)[:1200], "features": "",
                  "price": _num(price), "currency": currency, "affiliate_url": body.url, "image_remote": img,
                  "platform": httpx.URL(str(r.url)).host.removeprefix("www.").split(".")[0].capitalize()}
        if not boot.dry_run and (title or desc):
            text = re.sub(r"<[^>]+>", " ", page)
            text = re.sub(r"\s+", " ", text)[:6000]
            try:
                ex = await ollama.chat_json(
                    "Ürün sayfası metninden yalnızca gerçek bilgileri çıkar. Uydurma yok.",
                    f"Başlık: {title}\nAçıklama: {desc}\nSayfa metni: {text}", Extracted, temperature=0.2)
                result |= {"name": ex.name or result["name"], "description": ex.description or result["description"],
                           "features": "\n".join(ex.features)}
            except Exception:
                pass
        if img:
            try:
                ir = await c.get(str(r.url.join(img)))
                ir.raise_for_status()
                ext = {"image/png": ".png", "image/webp": ".webp"}.get(ir.headers.get("content-type", "").split(";")[0], ".jpg")
                dst = paths.products / f"auto_{uuid.uuid4().hex[:10]}{ext}"
                dst.write_bytes(ir.content)
                result["image_path"] = str(dst)
                result["image_url"] = paths.url(dst)
            except httpx.HTTPError:
                pass
        return result


def _num(v) -> float | None:
    if v is None:
        return None
    try:
        s = str(v).strip().replace(" ", "")
        if "," in s and "." in s:
            s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
        elif "," in s:
            s = s.replace(",", ".")
        return float(s)
    except ValueError:
        return None


def _404():
    raise HTTPException(404, "Bulunamadı")
