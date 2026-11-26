"""FFmpeg helpers, encoder detection, font resolution."""
from __future__ import annotations

import asyncio
import json
import platform
import shutil
from functools import lru_cache
from pathlib import Path

from .config import config, paths

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"


class FFmpegError(RuntimeError):
    pass


async def _exec(*args: str) -> tuple[int, bytes, bytes]:
    p = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await p.communicate()
    return p.returncode or 0, out, err


async def run_ffmpeg(args: list[str]) -> None:
    code, _, err = await _exec(FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *args)
    if code:
        raise FFmpegError(err.decode(errors="ignore")[-1500:])


async def probe_duration(p: Path) -> float:
    code, out, err = await _exec(FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(p))
    if code:
        raise FFmpegError(err.decode(errors="ignore"))
    return float(json.loads(out)["format"]["duration"])


async def probe(p: Path) -> dict:
    _, out, _ = await _exec(FFPROBE, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(p))
    return json.loads(out or b"{}")


_encoder: str | None = None


async def video_encoder() -> str:
    global _encoder
    pref = config.get().video_encoder
    if pref != "auto":
        return pref
    if _encoder is None:
        code, _, _ = await _exec(FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                                 "color=c=black:s=256x256:d=0.1", "-c:v", "h264_nvenc", "-f", "null", "-")
        _encoder = "h264_nvenc" if code == 0 else "libx264"
    return _encoder


def encoder_args(enc: str, quality: str = "final") -> list[str]:
    if enc == "h264_nvenc":
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-tune", "hq", "-rc", "vbr", "-cq", "20" if quality == "final" else "18",
                "-b:v", "0", "-pix_fmt", "yuv420p"]
    return ["-c:v", "libx264", "-preset", "medium" if quality == "final" else "veryfast", "-crf", "19" if quality == "final" else "17",
            "-pix_fmt", "yuv420p"]


_FONT_CANDIDATES = [
    "Montserrat-ExtraBold.ttf", "Montserrat-Black.ttf", "Poppins-ExtraBold.ttf", "Inter-ExtraBold.ttf",
    "C:/Windows/Fonts/seguibl.ttf", "C:/Windows/Fonts/ariblk.ttf", "C:/Windows/Fonts/arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]


@lru_cache
def bold_font() -> str | None:
    for c in _FONT_CANDIDATES:
        p = Path(c) if Path(c).is_absolute() else paths.fonts / c
        if p.exists():
            return str(p)
    found = sorted(paths.fonts.glob("*.ttf")) + sorted(paths.fonts.glob("*.otf"))
    return str(found[0]) if found else None


def ass_fonts_dir() -> str:
    """libass fontsdir param; escape for filtergraph (Windows drive colon)."""
    d = paths.fonts.resolve().as_posix()
    if platform.system() == "Windows":
        d = d.replace(":", "\\:")
    return d


def filter_path(p: Path) -> str:
    s = p.resolve().as_posix()
    return s.replace(":", "\\:").replace("'", "\\'")
