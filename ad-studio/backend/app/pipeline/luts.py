"""Procedural 3D LUTs (.cube) for a filmic grade — no external assets, ffmpeg lut3d compatible."""
from __future__ import annotations

from pathlib import Path

from ..config import paths

SIZE = 17
PRESETS = ("neutral", "warm_film", "cool_doc", "teal_orange")


def _smooth(x: float, k: float) -> float:
    """Soft S-curve; k=0 identity, k>0 more contrast."""
    s = x * x * (3 - 2 * x)
    return (1 - k) * x + k * s


def _grade(r: float, g: float, b: float, preset: str) -> tuple[float, float, float]:
    luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
    if preset == "neutral":
        r, g, b = (_smooth(c, 0.15) for c in (r, g, b))
    elif preset == "warm_film":
        sat = 0.88
        r, g, b = (luma + (c - luma) * sat for c in (r, g, b))
        r, g, b = r * 1.03 + 0.012, g * 1.0 + 0.006, b * 0.94 + 0.02  # warm mids, lifted blacks
        r, g, b = (_smooth(c, 0.25) for c in (r, g, b))
    elif preset == "cool_doc":
        sat = 0.8
        r, g, b = (luma + (c - luma) * sat for c in (r, g, b))
        r, g, b = r * 0.97 + 0.015, g * 0.99 + 0.018, b * 1.03 + 0.025
        r, g, b = (_smooth(c, 0.3) for c in (r, g, b))
    elif preset == "teal_orange":
        w = max(0.0, min(1.0, (luma - 0.35) * 2.2))  # highlights warm, shadows teal
        r, g, b = r + 0.05 * w - 0.03 * (1 - w), g + 0.01 * w + 0.01 * (1 - w), b - 0.05 * w + 0.04 * (1 - w)
        r, g, b = (_smooth(c, 0.25) for c in (r, g, b))
    clamp = lambda v: min(1.0, max(0.0, v))  # noqa: E731
    return clamp(r), clamp(g), clamp(b)


def cube_text(preset: str, size: int = SIZE) -> str:
    lines = [f'TITLE "adforge_{preset}"', f"LUT_3D_SIZE {size}", "DOMAIN_MIN 0.0 0.0 0.0", "DOMAIN_MAX 1.0 1.0 1.0"]
    n = size - 1
    for bi in range(size):  # .cube order: red fastest, then green, then blue
        for gi in range(size):
            for ri in range(size):
                r, g, b = _grade(ri / n, gi / n, bi / n, preset)
                lines.append(f"{r:.6f} {g:.6f} {b:.6f}")
    return "\n".join(lines) + "\n"


def lut_path(preset: str) -> Path | None:
    if not preset or preset == "none":
        return None
    if preset not in PRESETS:
        custom = paths.root / "luts" / preset
        return custom if custom.exists() else None
    d = paths.root / "luts"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{preset}.cube"
    if not p.exists():
        p.write_text(cube_text(preset))
    return p
