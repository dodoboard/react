"""ASS subtitles: word-by-word highlighted captions + per-scene headline."""
from __future__ import annotations

from pathlib import Path

from ..providers.tts import Word

HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {resx}
PlayResY: {resy}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{cap_style}
{head_style}

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


HEAD = "Style: Head,{font},74,&H00FFFFFF,&H00FFFFFF,&H00000000,&HB4000000,-1,0,0,0,100,100,0,0,3,18,0,8,90,90,260,1"
# 16:9 documentary: understated captions, lower-third headlines (bottom-left, boxed)
DOC_CAP = "Style: Cap,{font},48,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,3,10,0,2,160,160,60,1"
DOC_HEAD = "Style: Head,{font},54,&H00FFFFFF,&H00FFFFFF,&H00141414,&HC8141414,-1,0,0,0,100,100,1,0,3,16,0,1,90,90,150,1"


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
          lang: str = "tr", style: str = "bold_yellow", hook_until: float = 0.0,
          res: tuple[int, int] = (1080, 1920), karaoke: bool = True) -> Path:
    hl = "&H" + ass_color(highlight)[4:] + "&"
    if style == "white_box":
        hl = "&H" + ass_color("#7C3AED")[4:] + "&"
    wide = res[0] > res[1]
    cap = (DOC_CAP if wide else STYLES.get(style, STYLES["bold_yellow"])).format(font=font)
    head = (DOC_HEAD if wide else HEAD).format(font=font)
    lines = [HEADER.format(font=font, cap_style=cap, head_style=head, resx=res[0], resy=res[1])]
    hook_words = [w for w in words if w.start < hook_until]
    if wide:
        groups = chunk(words, max_words=8, max_chars=46, max_gap=0.8)
    else:
        groups = chunk(hook_words, max_words=2, max_chars=14) + chunk(words[len(hook_words):])
    for grp in groups:
        if not karaoke or wide:
            end = max(grp[-1].end, grp[0].start + 0.6)
            lines.append(f"Dialogue: 1,{ts(grp[0].start)},{ts(end)},Cap,,0,0,0,,{esc(' '.join(w.text for w in grp))}")
            continue
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


def srt_ts(t: float) -> str:
    ms = int(round(max(0.0, t) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_srt(words: list[Word], out: Path, max_words: int = 9, max_chars: int = 48) -> Path:
    blocks = []
    for i, grp in enumerate(chunk(words, max_words=max_words, max_chars=max_chars, max_gap=0.8), 1):
        end = max(grp[-1].end, grp[0].start + 0.6)
        blocks.append(f"{i}\n{srt_ts(grp[0].start)} --> {srt_ts(end)}\n{' '.join(w.text for w in grp)}\n")
    out.write_text("\n".join(blocks), encoding="utf-8")
    return out
