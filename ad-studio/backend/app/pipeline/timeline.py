"""Map spoken words onto scene segments: [hook+scene0], scene1..n-1, end card (CTA)."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from ..providers.tts import Word
from .script import AdScript

MIN_SEG = 0.6


@dataclass
class Timeline:
    starts: list[float]  # scene i spans starts[i]..starts[i+1]; starts[-1] == cta_start
    cta_start: float
    total: float
    audio: float

    @property
    def scene_durations(self) -> list[float]:
        return [max(MIN_SEG, b - a) for a, b in zip(self.starts, self.starts[1:])]

    @property
    def card_duration(self) -> float:
        return max(MIN_SEG, self.total - sum(self.scene_durations))

    def scene_span(self, i: int) -> tuple[float, float]:
        return self.starts[i], self.starts[i + 1]

    def save(self, p: Path) -> None:
        p.write_text(json.dumps(asdict(self)))

    @classmethod
    def load(cls, p: Path) -> Timeline:
        return cls(**json.loads(p.read_text()))


def build(sc: AdScript, words: list[Word], audio_dur: float, end_card: float) -> Timeline:
    counts = [len(sc.hook.split()) + len(sc.scenes[0].voiceover.split()),
              *(len(s.voiceover.split()) for s in sc.scenes[1:])]
    total_words = sum(counts) + len(sc.cta.split())

    def t_at(idx: int) -> float:
        if not words:
            return audio_dur * idx / max(total_words, 1)
        i = idx if len(words) == total_words else int(idx * len(words) / total_words)
        return words[min(i, len(words) - 1)].start

    starts, acc = [0.0], 0
    for c in counts:
        acc += c
        starts.append(t_at(acc))
    cta = starts[-1]
    return Timeline(starts=starts, cta_start=cta, total=max(audio_dur + 0.35, cta + end_card), audio=audio_dur)
