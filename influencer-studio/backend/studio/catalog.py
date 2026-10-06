"""Builder catalog: the single source of truth for attributes, presets and aspect ratios.

The frontend renders the builder from `public_catalog()`, and `prompting` turns a
selection into a FLUX.2 prompt. Option phrases may contain `{lvl}`, which is replaced
by the attribute's intensity word (Average / Notable / Extreme).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Level = Literal["average", "notable", "extreme"]
LEVELS: tuple[Level, ...] = ("average", "notable", "extreme")
Group = Literal["base", "face", "body", "style"]

DEFAULT_LEVEL_WORDS = ("", "noticeably ", "extremely ")
MIN_AGE, MAX_AGE = 18, 80


@dataclass(frozen=True)
class Option:
    id: str
    label: str
    phrase: str


@dataclass(frozen=True)
class Attribute:
    id: str
    label: str
    group: Group
    options: tuple[Option, ...]
    max_select: int = 1
    level_words: tuple[str, str, str] | None = DEFAULT_LEVEL_WORDS  # None → no intensity control

    @property
    def leveled(self) -> bool:
        return self.level_words is not None

    def option(self, option_id: str) -> Option:
        for o in self.options:
            if o.id == option_id:
                return o
        raise KeyError(option_id)


def _opts(*items: tuple[str, str, str]) -> tuple[Option, ...]:
    return tuple(Option(*i) for i in items)


ATTRIBUTES: tuple[Attribute, ...] = (
    # ── Base identity ────────────────────────────────────────────────────────
    Attribute("character_type", "Character type", "base", _opts(
        ("human", "Human", "human"),
        ("elf", "Elf", "elf with pointed ears"),
        ("alien", "Alien", "humanoid alien with otherworldly features"),
        ("android", "Android", "android with subtle synthetic panel seams on the skin"),
        ("vampire", "Vampire", "pale vampire with faintly visible fangs"),
        ("demon", "Demon-blooded", "demon-blooded humanoid with small curved horns"),
        ("feline", "Feline hybrid", "feline humanoid with cat ears and fur-textured skin"),
        ("reptilian", "Reptilian", "reptilian humanoid with fine scales on the skin"),
        ("merfolk", "Merfolk", "merfolk humanoid with iridescent fin-like ears"),
    ), max_select=2, level_words=None),
    Attribute("gender", "Gender", "base", _opts(
        ("woman", "Woman", "woman"),
        ("man", "Man", "man"),
        ("androgynous", "Androgynous", "androgynous person"),
    ), level_words=None),
    Attribute("origin", "Ethnicity / origin", "base", _opts(
        ("east_asian", "East Asian", "East Asian"),
        ("south_asian", "South Asian", "South Asian"),
        ("southeast_asian", "Southeast Asian", "Southeast Asian"),
        ("middle_eastern", "Middle Eastern", "Middle Eastern"),
        ("turkish", "Turkish", "Turkish"),
        ("mediterranean", "Mediterranean", "Mediterranean"),
        ("northern_european", "Northern European", "Northern European"),
        ("eastern_european", "Eastern European", "Eastern European"),
        ("west_african", "West African", "West African"),
        ("east_african", "East African", "East African"),
        ("latin_american", "Latin American", "Latin American"),
        ("indigenous_american", "Indigenous American", "Indigenous American"),
        ("pacific_islander", "Pacific Islander", "Pacific Islander"),
        ("mixed", "Mixed heritage", "mixed"),
    ), level_words=None),
    Attribute("skin_tone", "Skin color", "base", _opts(
        ("porcelain", "Porcelain", "porcelain skin"),
        ("fair", "Fair", "fair skin"),
        ("light", "Light", "light skin"),
        ("olive", "Olive", "olive skin"),
        ("golden", "Golden tan", "golden tan skin"),
        ("brown", "Brown", "brown skin"),
        ("deep", "Deep brown", "deep brown skin"),
        ("ebony", "Ebony", "ebony skin"),
        ("pale_blue", "Pale blue", "pale blue skin"),
        ("emerald", "Emerald", "emerald green skin"),
        ("lavender", "Lavender", "lavender skin"),
        ("silver", "Metallic silver", "metallic silver skin"),
    ), level_words=None),
    Attribute("eye_color", "Eye color", "base", _opts(
        ("brown", "Brown", "{lvl}brown"),
        ("hazel", "Hazel", "{lvl}hazel"),
        ("amber", "Amber", "{lvl}amber"),
        ("green", "Green", "{lvl}green"),
        ("blue", "Blue", "{lvl}blue"),
        ("grey", "Grey", "{lvl}grey"),
        ("black", "Black", "{lvl}black"),
        ("violet", "Violet", "{lvl}violet"),
        ("gold", "Gold", "{lvl}gold"),
        ("heterochromia", "Heterochromia", "{lvl}heterochromatic blue-and-brown"),
    ), level_words=("", "vivid ", "strikingly luminous ")),
    Attribute("skin_details", "Skin conditions", "base", _opts(
        ("freckles", "Freckles", "{lvl}freckles"),
        ("beauty_marks", "Beauty marks", "{lvl}beauty marks"),
        ("scar", "Scar", "a {lvl}scar across one cheek"),
        ("birthmark", "Birthmark", "a {lvl}birthmark on the neck"),
        ("vitiligo", "Vitiligo", "{lvl}vitiligo patches"),
        ("albinism", "Albinism", "albinism with white eyelashes"),
        ("rosacea", "Rosy cheeks", "{lvl}rosy flushed cheeks"),
    ), max_select=4, level_words=("", "prominent ", "extensive ")),
    # ── Face ────────────────────────────────────────────────────────────────
    Attribute("face_shape", "Face shape", "face", _opts(
        ("oval", "Oval", "a {lvl}oval face"),
        ("round", "Round", "a {lvl}round face"),
        ("square", "Square", "a {lvl}square face with a strong jaw"),
        ("heart", "Heart", "a {lvl}heart-shaped face"),
        ("diamond", "Diamond", "a {lvl}diamond-shaped face with high cheekbones"),
        ("long", "Long", "a {lvl}long face"),
    )),
    Attribute("eye_shape", "Eyes", "face", _opts(
        ("almond", "Almond", "{lvl}almond-shaped"),
        ("round", "Round", "{lvl}round"),
        ("hooded", "Hooded", "{lvl}hooded"),
        ("monolid", "Monolid", "{lvl}monolid"),
        ("upturned", "Upturned", "{lvl}upturned"),
        ("downturned", "Downturned", "{lvl}downturned"),
        ("deep_set", "Deep-set", "{lvl}deep-set"),
    )),
    Attribute("nose", "Nose", "face", _opts(
        ("straight", "Straight", "a {lvl}straight nose"),
        ("button", "Button", "a {lvl}small button nose"),
        ("aquiline", "Aquiline", "a {lvl}aquiline nose"),
        ("wide", "Wide", "a {lvl}wide nose"),
        ("narrow", "Narrow", "a {lvl}narrow nose"),
        ("upturned", "Upturned", "a {lvl}upturned nose"),
    )),
    Attribute("lips", "Mouth & lips", "face", _opts(
        ("full", "Full", "{lvl}full lips"),
        ("thin", "Thin", "{lvl}thin lips"),
        ("cupid", "Cupid's bow", "lips with a {lvl}defined cupid's bow"),
        ("wide", "Wide smile", "a {lvl}wide mouth"),
        ("gap", "Tooth gap", "a {lvl}visible gap between the front teeth"),
    )),
    Attribute("eyebrows", "Eyebrows", "face", _opts(
        ("thick", "Thick", "{lvl}thick eyebrows"),
        ("thin", "Thin", "{lvl}thin eyebrows"),
        ("arched", "Arched", "{lvl}arched eyebrows"),
        ("straight", "Straight", "{lvl}straight eyebrows"),
        ("bushy", "Bushy", "{lvl}bushy eyebrows"),
    )),
    # ── Body ────────────────────────────────────────────────────────────────
    Attribute("body_type", "Body type", "body", _opts(
        ("slim", "Slim", "a {lvl}slim build"),
        ("athletic", "Athletic", "a {lvl}athletic build"),
        ("curvy", "Curvy", "a {lvl}curvy build"),
        ("muscular", "Muscular", "a {lvl}muscular build"),
        ("petite", "Petite", "a {lvl}petite build"),
        ("plus", "Plus-size", "a {lvl}plus-size build"),
    )),
    Attribute("height", "Height", "body", _opts(
        ("short", "Short", "{lvl}short stature"),
        ("average", "Average", "average height"),
        ("tall", "Tall", "{lvl}tall stature"),
    )),
    Attribute("proportions", "Proportions", "body", _opts(
        ("long_legs", "Long legs", "{lvl}long legs"),
        ("broad_shoulders", "Broad shoulders", "{lvl}broad shoulders"),
        ("narrow_waist", "Narrow waist", "a {lvl}narrow waist"),
        ("wide_hips", "Wide hips", "{lvl}wide hips"),
        ("long_neck", "Long neck", "a {lvl}long neck"),
    ), max_select=3),
    # ── Style ───────────────────────────────────────────────────────────────
    Attribute("hair_style", "Hair", "style", _opts(
        ("long_straight", "Long straight", "long straight {color}hair"),
        ("long_wavy", "Long wavy", "long wavy {color}hair"),
        ("curly", "Curly", "voluminous curly {color}hair"),
        ("braids", "Braids", "{color}hair in box braids"),
        ("bob", "Bob", "a sleek {color}bob"),
        ("pixie", "Pixie", "a {color}pixie cut"),
        ("ponytail", "Ponytail", "{color}hair in a high ponytail"),
        ("bun", "Bun", "{color}hair in a messy bun"),
        ("afro", "Afro", "a full {color}afro"),
        ("locs", "Locs", "long {color}locs"),
        ("undercut", "Undercut", "a {color}undercut"),
        ("buzz", "Buzz cut", "a {color}buzz cut"),
        ("bald", "Bald", "a shaved bald head"),
    ), level_words=None),
    Attribute("hair_color", "Hair color", "style", _opts(
        ("black", "Black", "{lvl}jet-black"),
        ("dark_brown", "Dark brown", "{lvl}dark brown"),
        ("chestnut", "Chestnut", "{lvl}chestnut"),
        ("auburn", "Auburn", "{lvl}auburn"),
        ("copper", "Copper red", "{lvl}copper red"),
        ("blonde", "Blonde", "{lvl}golden blonde"),
        ("platinum", "Platinum", "{lvl}platinum blonde"),
        ("silver", "Silver", "{lvl}silver grey"),
        ("pink", "Pastel pink", "{lvl}pastel pink"),
        ("blue", "Electric blue", "{lvl}electric blue"),
        ("white", "White", "{lvl}snow white"),
    ), level_words=("", "vivid ", "intensely saturated ")),
    Attribute("accessories", "Accessories", "style", _opts(
        ("glasses", "Glasses", "thin-framed glasses"),
        ("hoops", "Hoop earrings", "gold hoop earrings"),
        ("nose_ring", "Nose ring", "a small nose ring"),
        ("septum", "Septum ring", "a septum ring"),
        ("choker", "Choker", "a black choker necklace"),
        ("tattoos", "Tattoos", "{lvl}fine-line tattoos on the arms"),
        ("headscarf", "Headscarf", "a silk headscarf"),
        ("beanie", "Beanie", "a knit beanie"),
    ), max_select=4, level_words=("", "prominent ", "full-sleeve ")),
    Attribute("render_style", "Rendering style", "style", _opts(
        ("photo", "Photorealistic", "A photorealistic portrait photograph"),
        ("cinematic", "Cinematic", "A cinematic film still portrait, 35mm film, shallow depth of field"),
        ("editorial", "Editorial", "A high-end editorial fashion portrait photograph"),
        ("3d", "3D animated", "A high-quality 3D animated character render"),
        ("anime", "Anime", "An anime-style character illustration with clean line art"),
        ("painting", "Digital painting", "A detailed digital painting portrait"),
    ), level_words=None),
)

ATTRIBUTE_BY_ID: dict[str, Attribute] = {a.id: a for a in ATTRIBUTES}
PHOTOGRAPHIC_STYLES = frozenset({"photo", "cinematic", "editorial"})


@dataclass(frozen=True)
class Preset:
    id: str
    label: str
    category: str
    scene: str
    aspect: str = "4:5"


PRESETS: tuple[Preset, ...] = (
    Preset("coffee", "Morning coffee", "Lifestyle", "sitting by a sunlit café window holding a latte, candid smile, warm morning light"),
    Preset("mirror", "Mirror selfie", "Lifestyle", "taking a mirror selfie with a smartphone in a minimalist bedroom, casual outfit, natural daylight", "9:16"),
    Preset("cozy", "Cozy home", "Lifestyle", "relaxing on a sofa with a book in a cozy living room, warm lamp light"),
    Preset("city_night", "City night", "Street", "walking down a neon-lit city street at night in a stylish jacket, cinematic bokeh", "9:16"),
    Preset("istanbul", "Bosphorus ferry", "Travel", "on a ferry crossing the Bosphorus in Istanbul, seagulls and mosque silhouettes in the background, golden hour"),
    Preset("beach", "Beach sunset", "Travel", "standing on a beach at golden hour in a linen summer outfit, wind in the hair"),
    Preset("hiking", "Mountain trail", "Travel", "on a mountain trail in outdoor gear, epic valley landscape behind", "16:9"),
    Preset("gym", "Gym session", "Fitness", "working out in a modern gym in athletic wear, dramatic overhead lighting"),
    Preset("yoga", "Sunrise yoga", "Fitness", "doing a yoga pose on a rooftop at sunrise, calm atmosphere", "16:9"),
    Preset("editorial", "Studio editorial", "Fashion", "high-fashion studio editorial in a bold outfit, seamless colored backdrop, softbox lighting"),
    Preset("street_style", "Street style", "Fashion", "street-style fashion shot crossing a city street, oversized coat, candid stride", "9:16"),
    Preset("red_carpet", "Red carpet", "Fashion", "posing on a red carpet in elegant evening wear, camera flashes"),
    Preset("product", "Product hold", "UGC", "holding a product up toward the camera with a friendly expression, clean bright background, UGC style"),
    Preset("podcast", "Podcast", "UGC", "speaking into a podcast microphone in a home studio with headphones, soft key light", "16:9"),
    Preset("unboxing", "Unboxing", "UGC", "unboxing a package at a desk with an excited expression, top-down soft daylight"),
)
PRESET_BY_ID: dict[str, Preset] = {p.id: p for p in PRESETS}


@dataclass(frozen=True)
class Angle:
    id: str
    label: str
    scene: str


# Identity pack: multi-angle reference set built from the canonical portrait ("Soul ID").
ANGLES: tuple[Angle, ...] = (
    Angle("front", "Front", "front-facing head-and-shoulders portrait, neutral expression, plain light-grey backdrop, soft even light"),
    Angle("three_quarter_left", "3/4 left", "three-quarter view with the head turned to the left, plain light-grey backdrop"),
    Angle("three_quarter_right", "3/4 right", "three-quarter view with the head turned to the right, plain light-grey backdrop"),
    Angle("profile", "Profile", "side profile view facing right, plain light-grey backdrop"),
    Angle("smile", "Smiling", "close-up portrait with a warm genuine smile showing teeth"),
    Angle("serious", "Serious", "close-up portrait with a serious expression and dramatic side lighting"),
    Angle("full_body", "Full body", "full-body shot standing in a simple casual outfit, plain light-grey studio"),
    Angle("outdoor", "Outdoor", "waist-up portrait outdoors in soft overcast daylight"),
)
ANGLE_BY_ID: dict[str, Angle] = {a.id: a for a in ANGLES}

# All sizes are multiples of 16 and close to 1 MP, FLUX.2's sweet spot.
ASPECTS: dict[str, tuple[int, int]] = {
    "1:1": (1024, 1024),
    "4:5": (896, 1120),
    "3:4": (880, 1184),
    "9:16": (768, 1344),
    "16:9": (1344, 768),
}


def public_catalog() -> dict:
    return {
        "levels": list(LEVELS),
        "age": {"min": MIN_AGE, "max": MAX_AGE, "default": 25},
        "groups": [
            {"id": "base", "label": "Base identity"},
            {"id": "face", "label": "Face"},
            {"id": "body", "label": "Body"},
            {"id": "style", "label": "Style"},
        ],
        "attributes": [
            {
                "id": a.id,
                "label": a.label,
                "group": a.group,
                "max_select": a.max_select,
                "leveled": a.leveled,
                "options": [{"id": o.id, "label": o.label} for o in a.options],
            }
            for a in ATTRIBUTES
        ],
        "presets": [vars(p) for p in PRESETS],
        "angles": [{"id": a.id, "label": a.label} for a in ANGLES],
        "aspects": {k: {"width": w, "height": h} for k, (w, h) in ASPECTS.items()},
    }
