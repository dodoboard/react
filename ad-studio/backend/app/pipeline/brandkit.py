"""Brand identity resolution: runtime defaults overridden by the campaign's brand."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import ImageFont

from ..config import config, paths
from ..models import Brand, Campaign, session
from .graphics import RGB, hex_rgb


@dataclass
class BrandStyle:
    brand_id: int | None
    name: str
    primary: RGB
    accent: RGB
    highlight_hex: str
    font_name: str  # ASS family name
    font_path: str | None  # Pillow
    voice_id: str
    cta: str
    disclosure: str
    hashtag: str
    logo: Path | None
    guidelines: str
    banned: list[str]
    must_say: str
    tone: str
    audience: str


def load_brand(brand_id: int | None) -> Brand | None:
    if not brand_id:
        return None
    with session() as s:
        return s.get(Brand, brand_id)


def _font_family(path: Path) -> str | None:
    try:
        return ImageFont.truetype(str(path), 20).getname()[0]
    except OSError:
        return None


def resolve(campaign: Campaign | None = None, brand: Brand | None = None) -> BrandStyle:
    cfg = config.get()
    b = brand or (load_brand(campaign.brand_id) if campaign else None)
    font_path, font_name = None, cfg.subtitle_font
    if b and b.font_file and (paths.fonts / b.font_file).exists():
        font_path = str(paths.fonts / b.font_file)
        font_name = _font_family(paths.fonts / b.font_file) or font_name
    logo = Path(b.logo_path) if b and b.logo_path and Path(b.logo_path).exists() else None
    accent_hex = (b.accent_color if b and b.accent_color else cfg.subtitle_highlight)
    return BrandStyle(
        brand_id=b.id if b else None,
        name=(b.name if b else cfg.brand_name),
        primary=hex_rgb(b.primary_color) if b else (124, 58, 237),
        accent=hex_rgb(accent_hex, (255, 212, 0)),
        highlight_hex=accent_hex,
        font_name=font_name,
        font_path=font_path,
        voice_id=(b.voice_id if b else "") or "",
        cta=(b.cta if b and b.cta else cfg.cta_default),
        disclosure=(b.ad_disclosure if b and b.ad_disclosure else cfg.ad_disclosure),
        hashtag=(b.hashtag.lstrip("#") if b else ""),
        logo=logo,
        guidelines=b.guidelines if b else "",
        banned=[w.strip().lower() for w in (b.banned_words if b else "").split(",") if w.strip()],
        must_say=b.must_say if b else "",
        tone=b.tone if b else "",
        audience=b.audience if b else "",
    )


def violations(text: str, banned: list[str]) -> list[str]:
    low = text.lower()
    return [w for w in banned if w and w in low]
