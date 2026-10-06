"""Compiles a CharacterSpec into natural-language FLUX.2 prompts."""

from __future__ import annotations

import re

from .catalog import ATTRIBUTE_BY_ID, LEVELS, PHOTOGRAPHIC_STYLES, Angle
from .models import CharacterSpec

NEGATIVE = "blurry, low quality, deformed face, distorted features, extra fingers, watermark, text, logo"

_CONTENT_HEADERS = {
    "photo": "A photorealistic candid photograph",
    "cinematic": "A cinematic film still",
    "editorial": "A high-end editorial fashion photograph",
    "3d": "A high-quality 3D animated render",
    "anime": "An anime-style illustration",
    "painting": "A detailed digital painting",
}
_PRONOUNS = {"woman": ("She", "has"), "man": ("He", "has")}
_AN = re.compile(r"\ba (?=[aeiou])")


def _sentence(text: str) -> str:
    text = text.strip().rstrip(".")
    return f"{text[:1].upper()}{text[1:]}." if text else ""


def _phrases(spec: CharacterSpec, attr_id: str) -> list[str]:
    sel = spec.selections.get(attr_id)
    if not sel or not sel.values:
        return []
    attr = ATTRIBUTE_BY_ID[attr_id]
    word = attr.level_words[LEVELS.index(sel.level)] if attr.level_words else ""
    return [_AN.sub("an ", attr.option(v).phrase.replace("{lvl}", word)) for v in sel.values]


def _first(spec: CharacterSpec, attr_id: str) -> str | None:
    p = _phrases(spec, attr_id)
    return p[0] if p else None


def _selected_id(spec: CharacterSpec, attr_id: str) -> str | None:
    sel = spec.selections.get(attr_id)
    return sel.values[0] if sel and sel.values else None


def _article(noun: str) -> str:
    return "an" if noun[:1].lower() in "aeiou" else "a"


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"


def _style(spec: CharacterSpec) -> str:
    return _selected_id(spec, "render_style") or "photo"


def subject(spec: CharacterSpec) -> str:
    s = f"a {spec.age}-year-old {_first(spec, 'gender') or 'person'}"
    if origin := _first(spec, "origin"):
        s += f" of {origin} heritage"
    types = _phrases(spec, "character_type")
    if len(types) == 2:
        s += f", a hybrid being who is part {types[0]} and part {types[1]}"
    elif types and types[0] != "human":
        s += f", {_article(types[0])} {types[0]}"
    return s


def hair(spec: CharacterSpec) -> str | None:
    color, style = _first(spec, "hair_color"), _first(spec, "hair_style")
    if style:
        return style.replace("{color}", f"{color} " if color else "")
    return f"{color} hair" if color else None


def _feature_sentences(spec: CharacterSpec) -> list[str]:
    pronoun, has = _PRONOUNS.get(_selected_id(spec, "gender") or "", ("They", "have"))
    eyes = " ".join(filter(None, (_first(spec, "eye_shape"), _first(spec, "eye_color"))))
    face = [
        *_phrases(spec, "skin_tone"),
        *([f"{eyes} eyes"] if eyes else []),
        *_phrases(spec, "face_shape"),
        *_phrases(spec, "nose"),
        *_phrases(spec, "lips"),
        *_phrases(spec, "eyebrows"),
        *_phrases(spec, "skin_details"),
    ]
    body = [*_phrases(spec, "body_type"), *_phrases(spec, "proportions"), *_phrases(spec, "height")]
    out = [f"{pronoun} {has} {_join(group)}." for group in (face, body) if group]
    if h := hair(spec):
        out.append(f"{pronoun} {has} {h}.")
    if acc := _phrases(spec, "accessories"):
        out.append(f"Styling details: {_join(acc)}.")
    if spec.extra.strip():
        out.append(_sentence(spec.extra))
    return out


def _tail(spec: CharacterSpec) -> str:
    if _style(spec) in PHOTOGRAPHIC_STYLES:
        return "Natural skin texture with visible pores, realistic lighting, sharp focus."
    return "Clean, consistent character design."


def identity_lock(spec: CharacterSpec) -> str:
    who = subject(spec) + (f" with {h}" if (h := hair(spec)) else "")
    return (
        f"This is the exact same person as in the reference images: {who}. "
        "Keep the face, facial features, skin tone, eye color and hairstyle identical."
    )


def character_prompt(spec: CharacterSpec, *, with_face: bool = False) -> str:
    header = ATTRIBUTE_BY_ID["render_style"].option(_style(spec)).phrase
    parts = [f"{header} of {subject(spec)}.", *_feature_sentences(spec)]
    parts.append(
        "Head-and-shoulders framing facing the camera, relaxed neutral expression, "
        "plain light-grey studio backdrop, soft diffused key light."
    )
    parts.append(_tail(spec))
    prompt = " ".join(parts)
    if with_face:
        prompt = (
            "Keep the facial identity of the person in the reference image: same facial structure, "
            f"eyes, nose and mouth. Portray that person as described. {prompt}"
        )
    return prompt


def scene_prompt(spec: CharacterSpec, scene: str, extra: str = "") -> str:
    header = _CONTENT_HEADERS[_style(spec)]
    parts = [f"{header} of the person from the reference images, {scene.strip().rstrip('.')}."]
    if extra.strip():
        parts.append(_sentence(extra))
    parts += [identity_lock(spec), _tail(spec)]
    return " ".join(parts)


def angle_prompt(spec: CharacterSpec, angle: Angle) -> str:
    return scene_prompt(spec, angle.scene)
