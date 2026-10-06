import pytest
from pydantic import ValidationError

from studio.catalog import ATTRIBUTES, LEVELS, PRESETS
from studio.models import CharacterSpec, ContentRequest
from studio.prompting import character_prompt, identity_lock, scene_prompt


def spec(age: int = 26, **selections) -> CharacterSpec:
    return CharacterSpec.model_validate({
        "age": age,
        "selections": {k: v if isinstance(v, dict) else {"values": v} for k, v in selections.items()},
    })


def test_full_character_prompt_reads_naturally():
    s = spec(
        gender=["woman"], origin=["turkish"], skin_tone=["olive"],
        eye_shape=["almond"], eye_color={"values": ["green"], "level": "notable"},
        body_type=["athletic"], lips={"values": ["gap"], "level": "extreme"},
        hair_style=["long_wavy"], hair_color=["copper"],
    )
    p = character_prompt(s)
    assert p.startswith("A photorealistic portrait photograph of a 26-year-old woman of Turkish heritage.")
    assert "almond-shaped vivid green eyes" in p
    assert "an athletic build" in p and "an extremely visible gap" in p
    assert "She has long wavy copper red hair." in p
    assert "visible pores" in p


def test_levels_change_wording():
    words = [character_prompt(spec(face_shape={"values": ["square"], "level": lvl})) for lvl in LEVELS]
    assert "a square face" in words[0]
    assert "a noticeably square face" in words[1]
    assert "an extremely square face" in words[2]


def test_hybrid_non_photo_and_face_reference():
    p = character_prompt(spec(character_type=["human", "elf"], gender=["man"], render_style=["anime"]), with_face=True)
    assert p.startswith("Keep the facial identity of the person in the reference image")
    assert "part human and part elf with pointed ears" in p
    assert "visible pores" not in p


def test_neutral_pronoun_when_gender_unset():
    assert "They have a round face." in character_prompt(spec(face_shape=["round"]))


def test_every_option_compiles_at_every_level():
    for attr in ATTRIBUTES:
        for option in attr.options:
            for level in LEVELS if attr.leveled else ("average",):
                p = character_prompt(spec(**{attr.id: {"values": [option.id], "level": level}}))
                assert "{" not in p and "  " not in p, (attr.id, option.id, level, p)


def test_scene_prompt_locks_identity():
    s = spec(gender=["woman"], hair_style=["bob"], hair_color=["black"])
    p = scene_prompt(s, PRESETS[0].scene, "wearing a beige trench coat")
    assert "Wearing a beige trench coat." in p
    assert identity_lock(s) in p and "with a sleek jet-black bob" in p


@pytest.mark.parametrize("payload", [
    {"selections": {"nope": {"values": ["x"]}}},
    {"selections": {"gender": {"values": ["dragon"]}}},
    {"selections": {"gender": {"values": ["woman", "man"]}}},
    {"age": 16},
])
def test_invalid_specs_rejected(payload):
    with pytest.raises(ValidationError):
        CharacterSpec.model_validate(payload)


def test_content_requires_scene():
    with pytest.raises(ValidationError):
        ContentRequest(prompt="  ")
    assert ContentRequest(preset_id="gym").preset_id == "gym"
