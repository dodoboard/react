"""Cinematography recipes: turn a scene description into a photographic prompt that reads as captured, not rendered."""
from __future__ import annotations

import hashlib

NEGATIVE = ("plastic skin, airbrushed, CGI, 3d render, illustration, painting, oversaturated, HDR look, overly smooth, "
            "perfect symmetry, glossy, waxy, uncanny, extra fingers, deformed hands, text, watermark, logo, frame, border")

CAMERAS = ["shot on Sony A7 IV", "shot on Canon EOS R5", "shot on Fujifilm X-T5", "shot on Leica Q2", "shot on ARRI Alexa Mini"]
FILM = ["Kodak Portra 400 color science", "Fujifilm Pro 400H tones", "subtle 35mm film grain", "natural color grading"]

AD = {
    "product_hero": "commercial product photograph, {lens}, softbox key light with gentle falloff, real tabletop surface texture, "
                    "micro reflections, shallow depth of field, {camera}",
    "product_in_use": "candid lifestyle photograph of real hands using the product, {lens}, natural window light, "
                      "lived-in home environment, slight motion blur, {camera}, {film}",
    "detail": "macro close-up photograph, 100mm macro lens, raking light revealing material texture, dust specks, {camera}",
    "lifestyle": "authentic lifestyle photo, {lens}, golden hour natural light, real people with natural skin texture and pores, "
                 "candid moment, {camera}, {film}",
    "presenter": "smartphone selfie video frame, front camera, natural indoor light, real skin texture, {film}",
}
DOC = {
    "establishing": "wide establishing shot, 24mm lens, atmospheric haze, natural light, documentary cinematography, {camera}, {film}",
    "detail": "documentary close-up, 85mm lens, shallow depth of field, practical light, tactile textures, {camera}, {film}",
    "aerial": "aerial drone photograph, high altitude, soft morning light, natural colors, slight haze",
    "archival": "authentic archival photograph, period-accurate, slight fading, film grain, imperfect exposure, museum scan",
    "reconstruction": "historically accurate documentary reconstruction still, natural light, real materials, {lens}, {camera}, {film}",
    "interview": "documentary interview frame, 50mm lens, soft key light from window, practical lamp in background, "
                 "shallow depth of field, {camera}, {film}",
}
CAMERA_MOVES = {
    "establishing": "slow aerial push-in, steady gimbal",
    "detail": "slow dolly in, subtle focus breathing",
    "aerial": "slow forward drone flight",
    "archival": "very slow pan across the photograph",
    "reconstruction": "slow lateral parallax track",
    "interview": "locked off camera, natural subtle movement",
    "product_hero": "slow orbit around the product",
    "product_in_use": "handheld, gentle natural sway",
    "lifestyle": "handheld, gentle natural sway",
}
LENSES = ["35mm lens f/2", "50mm lens f/1.8", "28mm lens f/2.8", "85mm lens f/1.8"]


def _pick(seq: list[str], key: str) -> str:
    h = int(hashlib.md5(key.encode()).hexdigest(), 16)
    return seq[h % len(seq)]


def doc_shot_type(prompt: str) -> str:
    p = prompt.lower()
    if any(w in p for w in ("aerial", "drone", "bird's eye", "from above")):
        return "aerial"
    if any(w in p for w in ("archival", "old photograph", "vintage photo", "historical photo", "engraving", "map")):
        return "archival"
    if any(w in p for w in ("close-up", "close up", "macro", "detail")):
        return "detail"
    if any(w in p for w in ("wide", "landscape", "establishing", "panorama", "skyline")):
        return "establishing"
    return "reconstruction"


def recipe(scene: str, shot: str, domain: str = "ad", key: str = "", style: str = "") -> str:
    """Full positive prompt: scene subject first, then camera language, then optional style."""
    table = DOC if domain == "doc" else AD
    kind = shot if shot in table else (doc_shot_type(scene) if domain == "doc" else "lifestyle")
    k = key or scene
    tail = table[kind].format(camera=_pick(CAMERAS, k), film=_pick(FILM, k + "f"), lens=_pick(LENSES, k + "l"))
    return ", ".join(x for x in (scene.strip().rstrip(","), tail, style) if x)


def motion(scene: str, shot: str, domain: str = "ad") -> str:
    kind = shot if shot in CAMERA_MOVES else (doc_shot_type(scene) if domain == "doc" else "lifestyle")
    return CAMERA_MOVES.get(kind, "slow cinematic camera move")


def negative(extra: str = "") -> str:
    return ", ".join(x for x in (NEGATIVE, extra) if x)


PRESENTER_BEHAVIOR = ("natural blinking, subtle head nods, small hand gestures while explaining, relaxed shoulders, "
                      "micro facial expressions, eyes looking into the lens")
