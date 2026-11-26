"""Pillow-rendered assets: stub scenes, end card, thumbnail."""
from __future__ import annotations

import re
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from ..media import bold_font

W, H = 1080, 1920
PALETTES = [((124, 58, 237), (236, 72, 153)), ((14, 165, 233), (99, 102, 241)), ((16, 185, 129), (6, 95, 70)),
            ((249, 115, 22), (225, 29, 72)), ((30, 41, 59), (124, 58, 237))]


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    f = bold_font()
    return ImageFont.truetype(f, size) if f else ImageFont.load_default(size=size)


def gradient(size: tuple[int, int], a: tuple[int, int, int], b: tuple[int, int, int]) -> Image.Image:
    g = Image.linear_gradient("L").resize(size)
    return Image.composite(Image.new("RGB", size, b), Image.new("RGB", size, a), g)


def _center_text(d: ImageDraw.ImageDraw, text: str, y: int, size: int, width_chars: int, fill=(255, 255, 255)) -> int:
    f = font(size)
    for line in textwrap.wrap(text, width_chars):
        bb = d.textbbox((0, 0), line, font=f, stroke_width=4)
        d.text(((W - (bb[2] - bb[0])) / 2, y), line, font=f, fill=fill, stroke_width=4, stroke_fill=(0, 0, 0, 160))
        y += int((bb[3] - bb[1]) * 1.2)
    return y


def stub_scene(out: Path, idx: int, title: str, subtitle: str) -> Path:
    a, b = PALETTES[idx % len(PALETTES)]
    img = gradient((W, H), a, b)
    d = ImageDraw.Draw(img)
    for r in range(6):
        cx, cy = (W * (0.2 + 0.15 * r)) % W, H * (0.15 + 0.13 * r)
        d.ellipse((cx - 160, cy - 160, cx + 160, cy + 160), outline=(255, 255, 255), width=3)
    _center_text(d, title.upper(), int(H * 0.42), 72, 18)
    _center_text(d, subtitle, int(H * 0.56), 36, 40, fill=(235, 235, 245))
    img.save(out)
    return out


def _cover(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    return ImageOps.fit(img.convert("RGB"), size, Image.LANCZOS)


def _rounded(img: Image.Image, radius: int) -> Image.Image:
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, *img.size), radius, fill=255)
    out = img.convert("RGBA")
    out.putalpha(mask)
    return out


_EMOJI = re.compile(r"[\U00010000-\U0010FFFF\u2600-\u27BF\uFE0F]")


def end_card(out: Path, bg: Path | None, product_img: Path | None, name: str, price: str, cta: str, brand: str) -> Path:
    cta = _EMOJI.sub("", cta).strip() or "Link profilde"
    base = _cover(Image.open(bg), (W, H)).filter(ImageFilter.GaussianBlur(28)) if bg and bg.exists() and bg.suffix != ".mp4" \
        else gradient((W, H), *PALETTES[0])
    shade = gradient((W, H), (10, 10, 18), (10, 10, 18))
    base = Image.blend(base, shade, 0.55).convert("RGBA")
    d = ImageDraw.Draw(base)
    y = 300
    if product_img and product_img.exists():
        p = ImageOps.contain(Image.open(product_img).convert("RGB"), (760, 760), Image.LANCZOS)
        card = Image.new("RGB", (p.width + 60, p.height + 60), (255, 255, 255))
        card.paste(p, (30, 30))
        card = _rounded(card, 48)
        shadow = Image.new("RGBA", (card.width + 80, card.height + 80), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle((40, 56, card.width + 40, card.height + 56), 48, fill=(0, 0, 0, 150))
        shadow = shadow.filter(ImageFilter.GaussianBlur(24))
        x = (W - card.width) // 2
        base.alpha_composite(shadow, (x - 40, y - 40))
        base.alpha_composite(card, (x, y))
        y += card.height + 70
    else:
        y = 700
    y = _center_text(d, name, y, 64, 22)
    if price:
        f = font(60)
        bb = d.textbbox((0, 0), price, font=f)
        pw, ph = bb[2] - bb[0] + 80, bb[3] - bb[1] + 50
        x0 = (W - pw) // 2
        d.rounded_rectangle((x0, y + 20, x0 + pw, y + 20 + ph), ph // 2, fill=(255, 212, 0))
        d.text((x0 + 40, y + 20 + 25 - bb[1]), price, font=f, fill=(15, 15, 20))
        y += ph + 70
    f = font(54)
    bb = d.textbbox((0, 0), cta, font=f)
    cw, ch = bb[2] - bb[0] + 100, bb[3] - bb[1] + 60
    x0 = (W - cw) // 2
    btn = gradient((cw, ch), (124, 58, 237), (236, 72, 153))
    base.alpha_composite(_rounded(btn, ch // 2), (x0, y + 10))
    d.text((x0 + 50, y + 10 + 30 - bb[1]), cta, font=f, fill=(255, 255, 255))
    if brand:
        _center_text(d, brand, H - 220, 36, 40, fill=(220, 220, 230))
    base.convert("RGB").save(out, quality=95)
    return out


def thumbnail(out: Path, bg: Path, hook: str) -> Path:
    img = _cover(Image.open(bg), (W, H))
    img = Image.blend(img, Image.new("RGB", (W, H), (0, 0, 0)), 0.25)
    d = ImageDraw.Draw(img)
    _center_text(d, hook.upper(), int(H * 0.36), 84, 16)
    img.resize((540, 960), Image.LANCZOS).save(out, quality=88)
    return out
