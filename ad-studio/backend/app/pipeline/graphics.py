"""Pillow-rendered assets: stub scenes, end card, thumbnail."""
from __future__ import annotations

import re
from contextvars import ContextVar
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from ..media import bold_font

W, H = 1080, 1920
PALETTES = [((124, 58, 237), (236, 72, 153)), ((14, 165, 233), (99, 102, 241)), ((16, 185, 129), (6, 95, 70)),
            ((249, 115, 22), (225, 29, 72)), ((30, 41, 59), (124, 58, 237))]


FONT_OVERRIDE: ContextVar[str | None] = ContextVar("font_override", default=None)
RGB = tuple[int, int, int]


def hex_rgb(h: str, default: RGB = (139, 92, 246)) -> RGB:
    h = (h or "").lstrip("#")
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except (ValueError, IndexError):
        return default


def shade(c: RGB, f: float) -> RGB:
    """f<0 darker, f>0 lighter."""
    return tuple(int(v + (255 - v) * f) if f > 0 else int(v * (1 + f)) for v in c)  # type: ignore[return-value]


def ink(c: RGB) -> RGB:
    """Readable text color on c."""
    return (15, 15, 20) if (0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]) > 150 else (255, 255, 255)


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    f = FONT_OVERRIDE.get() or bold_font()
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


def _card_base(bg: Path | None, primary: RGB) -> Image.Image:
    base = _cover(Image.open(bg), (W, H)).filter(ImageFilter.GaussianBlur(28)) if bg and bg.exists() and bg.suffix != ".mp4" \
        else gradient((W, H), primary, shade(primary, -0.6))
    tint = gradient((W, H), shade(primary, -0.75), (10, 10, 18))
    return Image.blend(base, tint, 0.6).convert("RGBA")


def _logo(base: Image.Image, logo: Path | None, y: int = 110, max_size: tuple[int, int] = (360, 140)) -> int:
    if not logo or not logo.exists():
        return y
    lg = ImageOps.contain(Image.open(logo).convert("RGBA"), max_size, Image.LANCZOS)
    base.alpha_composite(lg, ((W - lg.width) // 2, y))
    return y + lg.height + 40


def _cta_button(base: Image.Image, d: ImageDraw.ImageDraw, cta: str, y: int, primary: RGB) -> int:
    f = font(54)
    bb = d.textbbox((0, 0), cta, font=f)
    cw, ch = bb[2] - bb[0] + 100, bb[3] - bb[1] + 60
    x0 = (W - cw) // 2
    base.alpha_composite(_rounded(gradient((cw, ch), primary, shade(primary, 0.25)), ch // 2), (x0, y))
    d.text((x0 + 50, y + 30 - bb[1]), cta, font=f, fill=ink(primary))
    return y + ch


def end_card(out: Path, bg: Path | None, product_img: Path | None, name: str, price: str, cta: str, brand: str,
             primary: RGB = (124, 58, 237), accent: RGB = (255, 212, 0), logo: Path | None = None) -> Path:
    cta = _EMOJI.sub("", cta).strip() or "Link profilde"
    base = _card_base(bg, primary)
    d = ImageDraw.Draw(base)
    y = max(300, _logo(base, logo))
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
        d.rounded_rectangle((x0, y + 20, x0 + pw, y + 20 + ph), ph // 2, fill=accent)
        d.text((x0 + 40, y + 20 + 25 - bb[1]), price, font=f, fill=ink(accent))
        y += ph + 70
    _cta_button(base, d, cta, y + 10, primary)
    if brand and not logo:
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


def cover_copy(src: Path, out: Path, size: tuple[int, int] = (768, 1344)) -> Path:
    _cover(Image.open(src), size).save(out)
    return out


def collection_card(out: Path, bg: Path | None, items: list[tuple[Path | None, str, str]], title: str, cta: str,
                    brand: str, primary: RGB = (124, 58, 237), accent: RGB = (255, 212, 0), logo: Path | None = None) -> Path:
    """Grid of 2-6 products (image, name, price) + CTA."""
    cta = _EMOJI.sub("", cta).strip() or "Tüm ürünler profilde"
    base = _card_base(bg, primary)
    d = ImageDraw.Draw(base)
    y = _logo(base, logo, 90, (300, 110))
    n = len(items)
    cols = 2 if n <= 4 else 3
    rows = -(-n // cols)
    gap = 28
    cw = (W - 120 - gap * (cols - 1)) // cols
    chh = min(int(cw * 1.25), (H - y - 520 - gap * (rows - 1)) // rows)
    block = 150 + rows * (chh + gap) + 150  # title + grid + button
    y = max(y, (H - block) // 2)
    y = _center_text(d, title, y, 60, 24) + 30
    fs, fp = font(30), font(36)
    for i, (img, name, price) in enumerate(items):
        r, c = divmod(i, cols)
        x0 = 60 + c * (cw + gap) + (((cols - (n - r * cols)) * (cw + gap)) // 2 if r == rows - 1 and n % cols else 0)
        y0 = y + r * (chh + gap)
        card = Image.new("RGBA", (cw, chh), (255, 255, 255, 255))
        cd = ImageDraw.Draw(card)
        img_h = int(chh * 0.7)
        if img and img.exists():
            pim = ImageOps.contain(Image.open(img).convert("RGBA"), (cw - 40, img_h - 30), Image.LANCZOS)
            card.alpha_composite(pim, ((cw - pim.width) // 2, 15 + (img_h - 30 - pim.height) // 2))
        label = _fit(cd, name, fs, cw - 30)
        bb = cd.textbbox((0, 0), label, font=fs)
        cd.text(((cw - (bb[2] - bb[0])) / 2, img_h + 4), label, font=fs, fill=(30, 30, 40))
        if price:
            pb = cd.textbbox((0, 0), price, font=fp)
            pw = pb[2] - pb[0] + 40
            py = min(chh - 70, img_h + 56)
            cd.rounded_rectangle(((cw - pw) / 2, py, (cw + pw) / 2, py + 52), 26, fill=accent)
            cd.text(((cw - (pb[2] - pb[0])) / 2, py + 6 - pb[1] + 6), price, font=fp, fill=ink(accent))
        badge_r = 34
        cd.ellipse((12, 12, 12 + badge_r * 2, 12 + badge_r * 2), fill=primary)
        nb = cd.textbbox((0, 0), str(i + 1), font=fp)
        cd.text((12 + badge_r - (nb[2] - nb[0]) / 2, 12 + badge_r - (nb[3] - nb[1]) / 2 - nb[1]), str(i + 1), font=fp, fill=ink(primary))
        base.alpha_composite(_rounded(card.convert("RGB"), 32), (x0, y0))
    y = y + rows * (chh + gap) + 30
    _cta_button(base, d, cta, y, primary)
    if brand and not logo:
        _center_text(d, brand, H - 200, 36, 40, fill=(220, 220, 230))
    base.convert("RGB").save(out, quality=95)
    return out


def _fit(d: ImageDraw.ImageDraw, text: str, f, max_w: int) -> str:
    if d.textlength(text, font=f) <= max_w:
        return text
    while text and d.textlength(text + "…", font=f) > max_w:
        text = text[:-1]
    return text.rstrip() + "…"


def logo_watermark(out: Path, logo: Path, width: int = 180) -> Path:
    lg = Image.open(logo).convert("RGBA")
    lg = lg.resize((width, int(lg.height * width / lg.width)), Image.LANCZOS)
    a = lg.getchannel("A").point(lambda v: int(v * 0.85))
    lg.putalpha(a)
    lg.save(out)
    return out


def price_badge(out: Path, price: str, label: str = "", accent: RGB = (255, 212, 0)) -> Path:
    """Rounded sticker with price; overlaid on the product hero scene."""
    f, fs = font(76), font(34)
    tmp = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    pb = tmp.textbbox((0, 0), price, font=f)
    lb = tmp.textbbox((0, 0), label, font=fs) if label else (0, 0, 0, 0)
    w = max(pb[2] - pb[0], lb[2] - lb[0]) + 90
    h = (pb[3] - pb[1]) + (lb[3] - lb[1] + 16 if label else 0) + 70
    img = Image.new("RGBA", (w + 40, h + 40), (0, 0, 0, 0))
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((20, 28, w + 20, h + 28), 36, fill=(0, 0, 0, 140))
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(10)))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((20, 20, w + 20, h + 20), 36, fill=accent, outline=(255, 255, 255), width=5)
    y = 20 + 35
    if label:
        d.text((20 + (w - (lb[2] - lb[0])) / 2, y - lb[1]), label, font=fs, fill=shade(ink(accent), 0.15))
        y += lb[3] - lb[1] + 16
    d.text((20 + (w - (pb[2] - pb[0])) / 2, y - pb[1]), price, font=f, fill=ink(accent))
    img.rotate(-6, resample=Image.BICUBIC, expand=True).save(out)
    return out
