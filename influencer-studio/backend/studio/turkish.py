"""Turkish text normalization and chunking for TTS.

TTS models read digits and symbols unreliably, so numbers, ordinals, decimals, percentages,
times, currencies and common abbreviations are spelled out before synthesis:

    "%25 indirim, 1.250 TL"  → "yüzde yirmi beş indirim, bin iki yüz elli lira"
    "3. gün saat 14:30'da"   → "üçüncü gün saat on dört otuzda"
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

_ONES = ["", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz"]
_TENS = ["", "on", "yirmi", "otuz", "kırk", "elli", "altmış", "yetmiş", "seksen", "doksan"]
_SCALES = [(10**12, "trilyon"), (10**9, "milyar"), (10**6, "milyon"), (10**3, "bin")]


def _below_thousand(n: int) -> list[str]:
    hundreds, rest = divmod(n, 100)
    words = []
    if hundreds:
        words += ([] if hundreds == 1 else [_ONES[hundreds]]) + ["yüz"]  # "yüz", not "bir yüz"
    tens, ones = divmod(rest, 10)
    return [w for w in words + [_TENS[tens], _ONES[ones]] if w]


def number_to_words(n: int) -> str:
    if n < 0:
        return "eksi " + number_to_words(-n)
    if n == 0:
        return "sıfır"
    words: list[str] = []
    for value, name in _SCALES:
        count, n = divmod(n, value)
        if count:
            # "bin", not "bir bin" — but "bir milyon"
            words += ([] if count == 1 and value == 1000 else number_to_words(count).split()) + [name]
    return " ".join(words + _below_thousand(n))


_ORDINAL_SUFFIX = {"a": "ıncı", "ı": "ıncı", "e": "inci", "i": "inci", "o": "uncu", "u": "uncu", "ö": "üncü", "ü": "üncü"}


def ordinal_to_words(n: int) -> str:
    words = number_to_words(n)
    last_vowel = next(c for c in reversed(words) if c in _ORDINAL_SUFFIX)
    suffix = _ORDINAL_SUFFIX[last_vowel]
    if words[-1] in _ORDINAL_SUFFIX:  # ends with a vowel: "iki" → "ikinci"
        return words + suffix[1:]
    if words.endswith("dört"):  # consonant softening: dört → dördüncü
        words = words[:-1] + "d"
    return words + suffix


def _int(text: str) -> int:
    return int(text.replace(".", ""))


_ABBREVIATIONS = {
    "Dr.": "doktor", "Prof.": "profesör", "Doç.": "doçent", "Av.": "avukat", "Sn.": "sayın",
    "vb.": "ve benzeri", "vs.": "vesaire", "örn.": "örneğin", "bkz.": "bakınız", "yy.": "yüzyıl",
}
_CURRENCY = {"₺": "lira", "TL": "lira", "$": "dolar", "USD": "dolar", "€": "avro", "EUR": "avro", "£": "sterlin"}
_SUBUNIT = {"lira": "kuruş", "dolar": "sent", "avro": "sent", "sterlin": "peni"}
_UNITS = {"km": "kilometre", "kg": "kilogram", "cm": "santimetre", "mm": "milimetre", "m": "metre", "gr": "gram", "lt": "litre"}

# 1.250.000 (thousands dots) or plain digits
_NUM = r"\d{1,3}(?:\.\d{3})+|\d+"
_LETTER = "a-zA-ZçğıöşüÇĞİÖŞÜ"


def _time(m: re.Match) -> str:
    hour, minute = int(m[1]), m[2]
    if minute == "00":
        return number_to_words(hour)
    return f"{number_to_words(hour)} {'sıfır ' if minute[0] == '0' else ''}{number_to_words(int(minute))}"


def normalize(text: str) -> str:
    t = text.replace("\u2019", "'")
    for abbr, full in _ABBREVIATIONS.items():
        t = re.sub(rf"(?<![{_LETTER}]){re.escape(abbr)}", full, t)
    t = re.sub(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", _time, t)  # 14:30 → "on dört otuz"
    # %25 / % 25,5 → "yüzde yirmi beş (virgül beş)"
    t = re.sub(rf"%\s?({_NUM})(?:,(\d+))?", lambda m: "yüzde " + _spell(m[1], m[2]), t)
    # money: ₺49,90 / $20 / 1.500 TL / 49,90 TL → "kırk dokuz lira doksan kuruş"
    t = re.sub(rf"([₺$€£])\s?({_NUM})(?:,(\d{{1,2}}))?(?!\d)", lambda m: _money(m[2], m[3], m[1]), t)
    t = re.sub(rf"(?<![\d.,])({_NUM})(?:,(\d{{1,2}}))?\s?(TL|USD|EUR)\b", lambda m: _money(m[1], m[2], m[3]), t)
    # ordinals: "3. gün", "21. yüzyıl" (number + dot + lowercase word)
    t = re.sub(r"(?<![\d.,])(\d+)\.(?=\s+[a-zçğıöşü])", lambda m: ordinal_to_words(int(m[1])), t)
    # integers (1.250.000 grouped) and comma decimals
    t = re.sub(rf"(?<![\d.,])({_NUM})(?:,(\d+))?(?!\d)", lambda m: _spell(m[1], m[2]), t)
    # units / currency codes after a spelled number: "5 km", "100 TL"
    after = {**_UNITS, **{k: v for k, v in _CURRENCY.items() if k.isalpha()}}
    pattern = "|".join(sorted(map(re.escape, after), key=len, reverse=True))
    t = re.sub(rf"(?<=[{_LETTER}]) ({pattern})\b", lambda m: " " + after[m[1]], t)
    # suffixes written after an apostrophe belong to the spoken word: "altı'da" → "altıda"
    t = re.sub(rf"(?<=[{_LETTER}])'(?=[{_LETTER}])", "", t)
    return re.sub(r"\s+", " ", t.replace("&", " ve ")).strip()


def _money(integer: str, cents: str | None, symbol: str) -> str:
    unit = _CURRENCY[symbol]
    words = f"{number_to_words(_int(integer))} {unit}"
    if cents and int(cents):
        words += f" {number_to_words(int(cents.ljust(2, '0')))} {_SUBUNIT[unit]}"
    return words


def _decimals(digits: str) -> str:
    # leading zeros are read one by one: 0,05 → "sıfır virgül sıfır beş"
    zeros = len(digits) - len(digits.lstrip("0"))
    rest = digits.lstrip("0")
    return " ".join(["sıfır"] * zeros + ([number_to_words(int(rest))] if rest else []))


def _spell(integer: str, decimals: str | None) -> str:
    words = number_to_words(_int(integer))
    return f"{words} virgül {_decimals(decimals)}" if decimals else words


PAUSES = {"paragraph": 0.6, "sentence": 0.35, "clause": 0.15, "cut": 0.05}  # seconds after a chunk
_BOUNDARY = re.compile(r"[.!?…]+[\"'”’»)]*\s+")


@dataclass(frozen=True)
class Chunk:
    spoken: str  # what the TTS reads (normalized)
    display: str  # the script as written, for subtitles
    pause: float  # silence to insert after this chunk


def _sentences(paragraph: str) -> list[str]:
    """Split at sentence ends, but not inside "21. yüzyıl", "vb. gibi" or "Dr. Ayşe"."""
    out, start = [], 0
    for m in _BOUNDARY.finditer(paragraph):
        rest = paragraph[m.end():]
        word = paragraph[start:m.end()].split()[-1]
        if rest[:1].islower() or word in _ABBREVIATIONS:
            continue
        out.append(paragraph[start:m.end()].strip())
        start = m.end()
    return out + ([paragraph[start:].strip()] if paragraph[start:].strip() else [])


def _pieces(sentence: str, max_chars: int, speak: Callable[[str], str]) -> list[tuple[str, str]]:
    """(display, spoken) pieces of one sentence whose spoken form fits in `max_chars`."""
    budget = max_chars
    while True:  # normalization lengthens text ("1.250.000" → 30 chars), so shrink until it fits
        parts = [sentence] if len(sentence) <= budget else _split_long(sentence, budget)
        pairs = [(part, speak(part)) for part in parts]
        if budget < 20 or all(len(spoken) <= max_chars for _, spoken in pairs):
            return [(d, s) for d, s in pairs if s]
        budget = int(budget * 0.7)


def _pause_after(display: str) -> float:
    end = display.rstrip("\"'”’»)")[-1:]
    return PAUSES["sentence"] if end in ".!?…" else PAUSES["clause"] if end in ",;:" else PAUSES["cut"]


def chunk(text: str, max_chars: int = 250, speak: Callable[[str], str] = normalize) -> list[Chunk]:
    """Split a script into TTS-sized chunks at paragraph, sentence, then clause boundaries.

    Each sentence is normalized on its own, so the written text of every chunk is kept for
    subtitles. Pauses follow the punctuation the chunk ends with.
    """
    chunks: list[Chunk] = []
    for paragraph in filter(None, (p.strip() for p in re.split(r"\n\s*\n", text))):
        current: list[tuple[str, str]] = []

        def flush(pause: float | None = None) -> None:
            if current:
                display = " ".join(d for d, _ in current)
                spoken = " ".join(s for _, s in current)
                chunks.append(Chunk(spoken, display, _pause_after(display) if pause is None else pause))
                current.clear()

        for sentence in _sentences(paragraph.replace("\n", " ")):
            for display, spoken in _pieces(sentence, max_chars, speak):
                if current and sum(len(s) + 1 for _, s in current) + len(spoken) > max_chars:
                    flush()
                current.append((display, spoken))
        flush(PAUSES["paragraph"])
    return chunks


def _split_long(sentence: str, max_chars: int) -> list[str]:
    parts, current = [], ""
    for clause in re.split(r"(?<=[,;:])\s+", sentence):
        while len(clause) > max_chars:  # no punctuation to break at: cut at the last space
            cut = clause.rfind(" ", 0, max_chars)
            cut = cut if cut > 0 else max_chars
            parts.append(clause[:cut])
            clause = clause[cut:].strip()
        if current and len(current) + 1 + len(clause) > max_chars:
            parts.append(current)
            current = clause
        else:
            current = f"{current} {clause}".strip()
    return parts + ([current] if current else [])
