"""Text preparation for natural TTS: number/abbreviation normalization, v3 audio tags, pause planning.

Subtitles keep the script's original spelling; only the text sent to TTS is normalized. Word counts used for
timeline alignment are computed on the *spoken* text so boundaries stay correct.
"""
from __future__ import annotations

import re

ONES = ["", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz"]
TENS = ["", "on", "yirmi", "otuz", "kırk", "elli", "altmış", "yetmiş", "seksen", "doksan"]
SCALES = [(10 ** 12, "trilyon"), (10 ** 9, "milyar"), (10 ** 6, "milyon"), (1000, "bin")]
ORDINAL_SUFFIX = {"bir": "birinci", "iki": "ikinci", "üç": "üçüncü", "dört": "dördüncü", "beş": "beşinci",
                  "altı": "altıncı", "yedi": "yedinci", "sekiz": "sekizinci", "dokuz": "dokuzuncu", "on": "onuncu",
                  "yirmi": "yirminci", "otuz": "otuzuncu", "kırk": "kırkıncı", "elli": "ellinci", "altmış": "altmışıncı",
                  "yetmiş": "yetmişinci", "seksen": "sekseninci", "doksan": "doksanıncı", "yüz": "yüzüncü", "bin": "bininci"}
ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
ABBR_TR = [
    (r"\bMÖ\b", "milattan önce"), (r"\bM\.Ö\.", "milattan önce"), (r"\bMS\b", "milattan sonra"), (r"\bM\.S\.", "milattan sonra"),
    (r"\byy\.", "yüzyıl"), (r"\bvb\.", "ve benzeri"), (r"\bvs\.", "vesaire"), (r"\bkm\b", "kilometre"), (r"\bkg\b", "kilogram"),
    (r"\bcm\b", "santimetre"), (r"\bmm\b", "milimetre"), (r"\bm²", "metrekare"), (r"\b°C\b", "santigrat derece"),
    (r"\bDr\.", "Doktor"), (r"\bProf\.", "Profesör"), (r"\börn\.", "örneğin"), (r"\bTL\b", "lira"), (r"₺", " lira"),
    (r"\$", " dolar"), (r"€", " avro"),
]
TAG_RE = re.compile(r"\[[a-zA-Z ]{2,24}\]")
V3_TAGS = ["thoughtful", "whispers", "sighs", "excited", "curious", "serious", "softly", "pause"]


def tr_int(n: int) -> str:
    if n == 0:
        return "sıfır"
    if n < 0:
        return "eksi " + tr_int(-n)
    parts: list[str] = []
    for value, name in SCALES:
        q, n = divmod(n, value)
        if q:
            parts.append(name if (q == 1 and value == 1000) else f"{tr_int(q)} {name}")
    h, rest = divmod(n, 100)
    if h:
        parts.append("yüz" if h == 1 else f"{ONES[h]} yüz")
    t, o = divmod(rest, 10)
    if t:
        parts.append(TENS[t])
    if o:
        parts.append(ONES[o])
    return " ".join(parts)


def tr_ordinal(n: int) -> str:
    words = tr_int(n).split()
    last = words[-1]
    words[-1] = ORDINAL_SUFFIX.get(last, last + "inci")
    return " ".join(words)


def roman_to_int(s: str) -> int | None:
    if not re.fullmatch(r"M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})", s) or not s:
        return None
    total, prev = 0, 0
    for ch in reversed(s):
        v = ROMAN[ch]
        total = total - v if v < prev else total + v
        prev = max(prev, v)
    return total


def _num(m: re.Match) -> str:
    raw = m.group(0)
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", raw):  # 1.250.000 (TR thousands)
        return tr_int(int(raw.replace(".", "")))
    if "," in raw:  # 3,5 → üç virgül beş
        a, b = raw.split(",", 1)
        return f"{tr_int(int(a))} virgül {' '.join(tr_int(int(d)) for d in b) if b.startswith('0') else tr_int(int(b))}"
    return tr_int(int(raw))


def normalize_tr(text: str) -> str:
    t = text
    for pat, rep in ABBR_TR:
        t = re.sub(pat, rep, t)
    # Roman-numeral centuries: "XV. yüzyıl" → "on beşinci yüzyıl"
    t = re.sub(r"\b([IVXLCDM]{1,6})\.\s*(yüzyıl|yy)", lambda m: (tr_ordinal(roman_to_int(m.group(1))) + " " + m.group(2))
               if roman_to_int(m.group(1)) else m.group(0), t)
    # percentages: %40 / 40% → yüzde kırk
    t = re.sub(r"%\s?(\d+(?:,\d+)?)", lambda m: "yüzde " + _num(re.match(r".+", m.group(1))), t)
    t = re.sub(r"(\d+(?:,\d+)?)\s?%", lambda m: "yüzde " + _num(re.match(r".+", m.group(1))), t)
    # ordinals "3." before a word: 3. bölüm → üçüncü bölüm (not at sentence end)
    t = re.sub(r"\b(\d{1,4})\.(?=\s+[a-zçğıöşü])", lambda m: tr_ordinal(int(m.group(1))), t)
    # ranges 1914-1918 → bin dokuz yüz on dört ile bin dokuz yüz on sekiz arası (keep simple: "ile")
    t = re.sub(r"\b(\d{3,4})\s?[-–]\s?(\d{3,4})\b", lambda m: f"{tr_int(int(m.group(1)))} ile {tr_int(int(m.group(2)))}", t)
    t = re.sub(r"\d{1,3}(?:\.\d{3})+|\d+,\d+|\d+", _num, t)
    return re.sub(r"\s{2,}", " ", t).strip()


EN_ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
EN_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def en_int(n: int) -> str:
    if n < 20:
        return EN_ONES[n]
    if n < 100:
        return EN_TENS[n // 10] + ("-" + EN_ONES[n % 10] if n % 10 else "")
    if n < 1000:
        return EN_ONES[n // 100] + " hundred" + (" " + en_int(n % 100) if n % 100 else "")
    for v, name in ((10 ** 9, "billion"), (10 ** 6, "million"), (1000, "thousand")):
        if n >= v:
            return en_int(n // v) + f" {name}" + (" " + en_int(n % v) if n % v else "")
    return str(n)


def normalize_en(text: str) -> str:
    def year(m: re.Match) -> str:
        n = int(m.group(0))
        if 1100 <= n <= 1999 and n % 100:
            return f"{en_int(n // 100)} {en_int(n % 100) if n % 100 >= 10 else 'oh ' + en_int(n % 100)}"
        return en_int(n)
    t = re.sub(r"(\d+)%", lambda m: en_int(int(m.group(1))) + " percent", text)
    t = re.sub(r"\b\d{1,3}(?:,\d{3})+\b", lambda m: en_int(int(m.group(0).replace(",", ""))), t)
    t = re.sub(r"\b\d{1,9}\b", year, t)
    return t


def strip_tags(text: str) -> str:
    return re.sub(r"\s{2,}", " ", TAG_RE.sub("", text)).strip()


def spoken(text: str, lang: str, keep_tags: bool = False) -> str:
    """Text as the TTS should read it."""
    base = text if keep_tags else strip_tags(text)
    if lang in ("tr", "az"):
        return normalize_tr(base)
    if lang == "en":
        return normalize_en(base)
    return base


def word_count(text: str, lang: str) -> int:
    """Words the TTS will actually produce (for timeline alignment)."""
    return len(spoken(text, lang).split())


def pause_after(text: str, kind: str = "narration", chapter_end: bool = False) -> float:
    """Deterministic breath length after a segment."""
    if chapter_end:
        return 0.9
    t = text.rstrip()
    if t.endswith(("?", "!")):
        return 0.55
    if t.endswith(("…", "...")):
        return 0.7
    if kind == "presenter":
        return 0.35
    return 0.25 if t.endswith(",") else 0.4


NOISE_RE = re.compile(r"^(\[[^\]]*\]|<break|time=.*|/>|\.\.\.)$")


def clean_words(words: list) -> list:
    """Drop audio-tag / break-tag tokens that TTS alignment may return as 'words'."""
    return [w for w in words if not NOISE_RE.match(w.text.strip()) and TAG_RE.sub("", w.text).strip()]


def remap(words: list, original: list[str], spoken_parts: list[str]) -> list:
    """Map timings of spoken (normalized) words back onto the script's original tokens, segment by segment.

    words: TTS word timings for " ".join(spoken_parts); original/spoken_parts: per-segment texts.
    Returns objects of the same type as `words` (needs .text/.start/.end) carrying original spelling.
    """
    if not words:
        return words
    cls = type(words[0])
    out, i = [], 0
    total_spoken = sum(len(p.split()) for p in spoken_parts)
    scale = len(words) / total_spoken if total_spoken else 1.0
    for orig, sp in zip(original, spoken_parts):
        n_sp = len(sp.split())
        start_i = min(int(round(i * scale)), len(words) - 1)
        end_i = min(max(start_i + 1, int(round((i + n_sp) * scale))), len(words))
        chunk = words[start_i:end_i] or [words[start_i]]
        toks = strip_tags(orig).split()
        if not toks:
            i += n_sp
            continue
        if len(toks) == len(chunk):
            out += [cls(t, w.start, w.end) for t, w in zip(toks, chunk)]
        else:  # e.g. "1922" → 4 spoken words: spread original tokens over the chunk's time span
            a, b = chunk[0].start, chunk[-1].end
            step = (b - a) / len(toks)
            for k, t in enumerate(toks):
                j = min(int(k * len(chunk) / len(toks)), len(chunk) - 1)
                s0 = max(chunk[j].start, a + k * step)
                out.append(cls(t, s0, min(b, s0 + step * 0.95)))
        i += n_sp
    return out


def join_with_breaks(parts: list[str], kinds: list[str] | None, model: str, provider: str) -> str:
    """Natural pauses between segments. ElevenLabs v2-family understands <break time="x.xs"/>;
    v3 prefers punctuation/ellipses; local TTS gets plain text."""
    if provider != "elevenlabs" or len(parts) < 2:
        return " ".join(parts)
    kinds = kinds or ["narration"] * len(parts)
    out = []
    for k, (p, kind) in enumerate(zip(parts, kinds)):
        out.append(p)
        if k < len(parts) - 1:
            pause = pause_after(p, kind)
            out.append("..." if model.startswith("eleven_v3") and pause >= 0.5 else
                       (f'<break time="{pause:.1f}s" />' if not model.startswith("eleven_v3") else ""))
    return " ".join(x for x in out if x)
