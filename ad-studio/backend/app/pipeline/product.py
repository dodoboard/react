"""Real product in every product shot: background removal + compositing (pixel-exact) or Kontext reference."""
from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

from ..config import paths
from ..models import Product, session

_SESSION = None
_MAGIC = (255, 0, 254)


def rembg_available() -> bool:
    return importlib.util.find_spec("rembg") is not None


def _rembg(img: Image.Image) -> Image.Image:
    global _SESSION
    from rembg import new_session, remove

    if _SESSION is None:
        _SESSION = new_session("birefnet-general")
    return remove(img, session=_SESSION)


def _floodfill_cutout(img: Image.Image, thresh: int = 28) -> Image.Image:
    """Dependency-free fallback for studio shots on plain light backgrounds: flood fill from the borders."""
    rgb = img.convert("RGB")
    w, h = rgb.size
    work = rgb.copy()
    step = max(1, min(w, h) // 24)
    seeds = [(x, 0) for x in range(0, w, step)] + [(x, h - 1) for x in range(0, w, step)] + \
            [(0, y) for y in range(0, h, step)] + [(w - 1, y) for y in range(0, h, step)]
    for sx, sy in seeds:
        if work.getpixel((sx, sy)) != _MAGIC and sum(work.getpixel((sx, sy))) > 3 * 170:
            ImageDraw.floodfill(work, (sx, sy), _MAGIC, thresh=thresh)
    bg = ImageChops.difference(work, Image.new("RGB", (w, h), _MAGIC)).convert("L").point(lambda v: 0 if v < 2 else 255)
    alpha = bg.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(1.2))
    out = rgb.convert("RGBA")
    out.putalpha(alpha)
    return out


def make_cutout(src: Path, dst: Path) -> Path:
    img = ImageOps.exif_transpose(Image.open(src))
    if img.mode == "RGBA" and img.getextrema()[3][0] < 250:
        cut = img
    elif rembg_available():
        cut = _rembg(img.convert("RGB"))
    else:
        cut = _floodfill_cutout(img)
    bbox = cut.getchannel("A").point(lambda v: 255 if v > 16 else 0).getbbox()
    if not bbox:
        raise ValueError("Ürün görselinden kesim yapılamadı")
    cut.crop(bbox).save(dst)
    return dst


async def cutout(product: Product, force: bool = False) -> Path | None:
    if not product.image_path or not Path(product.image_path).exists():
        return None
    if product.cutout_path and Path(product.cutout_path).exists() and not force:
        return Path(product.cutout_path)
    dst = paths.products / f"{product.id}_cutout.png"
    await asyncio.to_thread(make_cutout, Path(product.image_path), dst)
    with session() as s:
        p = s.get(Product, product.id)
        p.cutout_path = str(dst)
        s.add(p)
        s.commit()
    product.cutout_path = str(dst)
    return dst


# placement: (width fraction, bottom y fraction, x center fraction)
PLACEMENT = {
    "product_hero": (0.52, 0.84, 0.5),
    "product_in_use": (0.46, 0.86, 0.56),
    "detail": (0.74, 0.84, 0.5),
}


def composite(bg_path: Path, cut_path: Path, out: Path, shot: str, idx: int = 0) -> Path:
    bg = Image.open(bg_path).convert("RGBA")
    W, H = bg.size
    cut = Image.open(cut_path).convert("RGBA")
    wf, bottom, cx = PLACEMENT.get(shot, PLACEMENT["product_hero"])
    cx += (-0.04, 0.0, 0.04)[idx % 3]
    tw = int(W * wf)
    th = int(cut.height * tw / cut.width)
    max_h = int(H * 0.38)  # keep the upper half free for headline + captions
    if th > max_h:
        th, tw = max_h, int(cut.width * max_h / cut.height)
    cut = cut.resize((tw, th), Image.LANCZOS)
    x = int(W * cx - tw / 2)
    y = int(H * bottom - th)
    alpha = cut.getchannel("A")

    # contact shadow (ellipse at the base) + soft drop shadow following the silhouette
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.ellipse((x + tw * 0.08, y + th - th * 0.05, x + tw * 0.92, y + th + th * 0.07), fill=(0, 0, 0, 150))
    layer = layer.filter(ImageFilter.GaussianBlur(max(6, tw // 28)))
    drop = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    drop.putalpha(alpha.point(lambda v: int(v * 0.35)))
    layer.alpha_composite(drop.filter(ImageFilter.GaussianBlur(max(8, tw // 20))), (x + tw // 40, y + th // 30))
    if shot == "product_hero":  # faint floor reflection
        refl = ImageOps.flip(cut)
        fade = ImageOps.invert(Image.linear_gradient("L").resize((tw, th))).point(lambda v: int(v * 0.18))
        refl.putalpha(ImageChops.multiply(ImageOps.flip(alpha), fade))
        layer.alpha_composite(refl.crop((0, 0, tw, min(th, H - (y + th)))), (x, y + th))
    bg.alpha_composite(layer)
    bg.alpha_composite(cut, (x, y))  # product pixels untouched
    bg.convert("RGB").save(out, quality=95)
    return out


def kontext_canvas(cut_path: Path, out: Path, size: tuple[int, int]) -> Path:
    """Product on neutral canvas in target aspect — Kontext reference input."""
    W, H = size
    canvas = Image.new("RGB", size, (236, 236, 240))
    cut = Image.open(cut_path).convert("RGBA")
    cut = ImageOps.contain(cut, (int(W * 0.7), int(H * 0.5)), Image.LANCZOS)
    canvas.paste(cut, ((W - cut.width) // 2, int(H * 0.72) - cut.height), cut)
    canvas.save(out)
    return out
