"""ASS subtitles: word-by-word highlighted captions + per-scene headline."""
from __future__ import annotations

from pathlib import Path

from ..providers.tts import Word

HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{cap_style}
Style: Head,{font},74,&H00FFFFFF,&H00FFFFFF,&H00000000,&HB4000000,-1,0,0,0,100,100,0,0,3,18,0,8,90,90,260,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def ass_color(hex_rgb: str) -> str:
    h = hex_rgb.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H00{b}{g}{r}".upper()


def ts(t: float) -> str:
    t = max(0.0, t)
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def esc(s: str) -> str:
    return s.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def upper(s: str, lang: str) -> str:
    if lang in ("tr", "az"):
        s = s.replace("i", "İ").replace("ı", "I")
    return s.upper()


# caption presets: (style line, highlight override tag, inactive word tag)
STYLES = {
    "bold_yellow": "Style: Cap,{font},92,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,7,4,2,80,80,1000,1",
    "white_box": "Style: Cap,{font},80,&H00111111,&H00111111,&H00FFFFFF,&H00FFFFFF,-1,0,0,0,100,100,0,0,3,14,0,2,90,90,1010,1",
    "gradient_pop": "Style: Cap,{font},96,&H00FFFFFF,&H00FFFFFF,&H00F65C8B,&H96000000,-1,0,0,0,100,100,0,0,1,9,0,2,80,80,1000,1",
}


def chunk(words: list[Word], max_words: int = 3, max_chars: int = 18, max_gap: float = 0.45) -> list[list[Word]]:
    out: list[list[Word]] = []
    cur: list[Word] = []
    for w in words:
        if cur and (len(cur) >= max_words or sum(len(x.text) + 1 for x in cur) + len(w.text) > max_chars
                    or w.start - cur[-1].end > max_gap or cur[-1].text[-1:] in ".!?"):
            out.append(cur)
            cur = []
        cur.append(w)
    if cur:
        out.append(cur)
    return out


def build(words: list[Word], headlines: list[tuple[float, float, str]], out: Path, font: str, highlight: str,
          lang: str = "tr", style: str = "bold_yellow", hook_until: float = 0.0) -> Path:
    hl = "&H" + ass_color(highlight)[4:] + "&"
    if style == "white_box":
        hl = "&H" + ass_color("#7C3AED")[4:] + "&"
    lines = [HEADER.format(font=font, cap_style=STYLES.get(style, STYLES["bold_yellow"]).format(font=font))]
    hook_words = [w for w in words if w.start < hook_until]
    groups = chunk(hook_words, max_words=2, max_chars=14) + chunk(words[len(hook_words):])
    for grp in groups:
        for i, w in enumerate(grp):
            start = w.start
            end = grp[i + 1].start if i + 1 < len(grp) else max(w.end, w.start + 0.25)
            parts = []
            for j, x in enumerate(grp):
                t = esc(upper(x.text, lang))
                parts.append(f"{{\\c{hl}\\fscx112\\fscy112}}{t}{{\\r}}" if j == i else t)
            pop = "{\\fad(40,0)}" if i == 0 else ""
            lines.append(f"Dialogue: 1,{ts(start)},{ts(end)},Cap,,0,0,0,,{pop}{' '.join(parts)}")
    for s, e, text in headlines:
        if text.strip():
            lines.append(f"Dialogue: 0,{ts(s)},{ts(e)},Head,,0,0,0,,{{\\fad(120,120)}}{esc(upper(text, lang))}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out
