"""Subtitle cues: short phrases with word timings, for burned-in Reels/TikTok captions.

Scripted speech already knows when each chunk plays (meta.segments, from the TTS joins); words
inside a chunk get time in proportion to their syllables. Turkish has exactly one vowel per
syllable, so vowel counts of the spoken form ("%30" → "yüzde otuz") are a good syllable count.
Recordings get word timings from speech recognition instead (meta.words).
"""

from __future__ import annotations

import re

from .turkish import normalize

MAX_WORDS = 4  # Reels-style captions: a few words at a time, large
MAX_CHARS = 24
MAX_GAP = 0.6  # seconds of silence that end a cue
_VOWELS = set("aeıioöuüâêîôûäëïAEIİOÖUÜÂÊÎÔÛÄËÏ" + "аеёиоуыэюяАЕЁИОУЫЭЮЯ" + "αεηιουωάέήίόύώ")
_BREAK_AFTER = re.compile(r"[.!?…:;]$|,$")


def _syllables(word: str, language: str) -> int:
    spoken = normalize(word) if language == "tr" else word
    vowels = sum(ch in _VOWELS for ch in spoken)
    return max(1, vowels or len(re.sub(r"\W", "", spoken)) // 2)


def words_from_segments(segments: list[dict], language: str = "tr") -> list[dict]:
    """Spread each segment's time over its written words, weighted by syllables."""
    words: list[dict] = []
    for seg in segments:
        tokens = seg["text"].split()
        if not tokens:
            continue
        weights = [_syllables(t, language) for t in tokens]
        span, total, t = seg["end"] - seg["start"], sum(weights), seg["start"]
        for token, weight in zip(tokens, weights):
            end = t + span * weight / total
            words.append({"text": token, "start": round(t, 3), "end": round(end, 3)})
            t = end
    return words


def cues_from_words(words: list[dict], max_words: int = MAX_WORDS, max_chars: int = MAX_CHARS,
                    max_gap: float = MAX_GAP) -> list[dict]:
    """Group words into cues: a few words, broken at punctuation and pauses."""
    cues: list[dict] = []
    current: list[dict] = []

    def flush() -> None:
        if current:
            cues.append({"start": current[0]["start"], "end": current[-1]["end"],
                         "text": " ".join(w["text"] for w in current), "words": list(current)})
            current.clear()

    for word in words:
        if current:
            chars = sum(len(w["text"]) + 1 for w in current) + len(word["text"])
            if len(current) >= max_words or chars > max_chars or word["start"] - current[-1]["end"] > max_gap:
                flush()
        current.append(word)
        if _BREAK_AFTER.search(word["text"]) and (len(current) >= 2 or word["text"][-1] in ".!?…"):
            flush()
    flush()
    return cues


def retime(cue: dict, text: str, language: str = "tr") -> dict:
    """A cue whose text was edited: keep its start/end, spread the new words over it."""
    words = words_from_segments([{"start": cue["start"], "end": cue["end"], "text": text}], language)
    return {"start": cue["start"], "end": cue["end"], "text": " ".join(w["text"] for w in words), "words": words}


def clip_cues(clip: dict, language: str = "tr") -> list[dict]:
    """Edited cues, else cues from recognized words, else from scripted segments."""
    meta = clip.get("meta") or {}
    if meta.get("cues"):
        return meta["cues"]
    if meta.get("words"):
        return cues_from_words(meta["words"])
    if meta.get("segments"):
        return cues_from_words(words_from_segments(meta["segments"], meta.get("language", language)))
    return []


def window(cues: list[dict], start: float, end: float, offset: float) -> list[dict]:
    """Cues inside [start, end) of a clip, moved to `offset` on an export timeline."""
    shift = offset - start
    out = []
    for cue in cues:
        if cue["end"] <= start or cue["start"] >= end:
            continue
        words = [{**w, "start": max(w["start"], start) + shift, "end": min(w["end"], end) + shift}
                 for w in cue["words"] if w["end"] > start and w["start"] < end]
        if words:
            out.append({"start": max(cue["start"], start) + shift, "end": min(cue["end"], end) + shift,
                        "text": " ".join(w["text"] for w in words), "words": words})
    return out
