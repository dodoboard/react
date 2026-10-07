from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .catalog import ANGLE_BY_ID, ASPECTS, ATTRIBUTE_BY_ID, MAX_AGE, MIN_AGE, PRESET_BY_ID, Level


class Selection(BaseModel):
    values: list[str] = Field(default_factory=list)
    level: Level = "average"


class CharacterSpec(BaseModel):
    selections: dict[str, Selection] = Field(default_factory=dict)
    age: int = Field(25, ge=MIN_AGE, le=MAX_AGE)
    extra: str = Field("", max_length=500)

    @model_validator(mode="after")
    def _validate_selections(self) -> CharacterSpec:
        for attr_id, sel in self.selections.items():
            attr = ATTRIBUTE_BY_ID.get(attr_id)
            if attr is None:
                raise ValueError(f"unknown attribute: {attr_id}")
            sel.values = list(dict.fromkeys(sel.values))
            if len(sel.values) > attr.max_select:
                raise ValueError(f"{attr_id}: at most {attr.max_select} value(s)")
            valid = {o.id for o in attr.options}
            if bad := [v for v in sel.values if v not in valid]:
                raise ValueError(f"{attr_id}: unknown option(s) {bad}")
        return self


def _check_aspect(v: str) -> str:
    if v not in ASPECTS:
        raise ValueError(f"aspect must be one of {list(ASPECTS)}")
    return v


class BuilderRequest(BaseModel):
    spec: CharacterSpec
    face_image_id: str | None = None
    consent: bool = False
    count: int = Field(2, ge=1, le=4)
    aspect: str = "1:1"
    seed: int | None = Field(None, ge=0, le=2**53)

    check_aspect = field_validator("aspect")(_check_aspect)


class PromptPreviewRequest(BaseModel):
    spec: CharacterSpec
    with_face: bool = False


class CreateCharacterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    spec: CharacterSpec
    image_id: str


class UpdateCharacterRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=60)
    reference_ids: list[str] | None = None
    lora: str | None = Field(None, max_length=200)  # "" removes the LoRA
    lora_strength: float | None = Field(None, ge=0, le=2)
    voice_id: str | None = None  # "" removes the voice


class IdentityPackRequest(BaseModel):
    angles: list[str] = Field(min_length=1, max_length=8)

    @field_validator("angles")
    @classmethod
    def _known(cls, v: list[str]) -> list[str]:
        if bad := [a for a in v if a not in ANGLE_BY_ID]:
            raise ValueError(f"unknown angle(s) {bad}")
        return list(dict.fromkeys(v))


class ContentRequest(BaseModel):
    preset_id: str | None = None
    prompt: str = Field("", max_length=1000)
    count: int = Field(2, ge=1, le=4)
    aspect: str = "4:5"
    seed: int | None = Field(None, ge=0, le=2**53)

    check_aspect = field_validator("aspect")(_check_aspect)

    @model_validator(mode="after")
    def _scene_required(self) -> ContentRequest:
        if self.preset_id is not None and self.preset_id not in PRESET_BY_ID:
            raise ValueError(f"unknown preset: {self.preset_id}")
        if not self.preset_id and not self.prompt.strip():
            raise ValueError("choose a preset or write a prompt")
        return self


# ── Motion studio ────────────────────────────────────────────────────────────
MAX_DANCE_SECONDS = 20
MAX_MUSIC_SECONDS = 30


class MotionBase(BaseModel):
    source_image_id: str
    resolution: Literal["480p", "720p"] = "480p"
    orientation: Literal["auto", "portrait", "landscape", "square"] = "auto"
    smooth: bool = False  # FILM interpolation to double the frame rate
    seed: int | None = Field(None, ge=0, le=2**53)


class DanceRequest(MotionBase):
    driver_id: str
    start: float = Field(0.0, ge=0)
    seconds: float = Field(5.0, ge=1, le=MAX_DANCE_SECONDS)
    pose_strength: float = Field(1.0, ge=0.5, le=1.5)
    keep_audio: bool = True


class MusicDanceRequest(MotionBase):
    music_id: str
    start: float = Field(0.0, ge=0)
    seconds: int = Field(10, ge=5, le=MAX_MUSIC_SECONDS)
    style: Literal["kpop", "street", "latin", "tap", "classical"] = "kpop"
    energy: Literal["low", "medium", "high", "max"] = "medium"
    quality: bool = False  # 25-step global pass instead of the 6-step lightx2v one

    @field_validator("seconds")
    @classmethod
    def _five_second_segments(cls, v: int) -> int:
        if v % 5:
            raise ValueError("seconds must be a multiple of 5")
        return v


class MotionPresetRequest(MotionBase):
    preset_id: str | None = None
    prompt: str = Field("", max_length=500)

    @model_validator(mode="after")
    def _action_required(self) -> MotionPresetRequest:
        from .video import MOTION_PRESET_BY_ID

        if self.preset_id is not None and self.preset_id not in MOTION_PRESET_BY_ID:
            raise ValueError(f"unknown motion preset: {self.preset_id}")
        if not self.preset_id and not self.prompt.strip():
            raise ValueError("choose a motion preset or describe the movement")
        return self


# ── Voice studio ─────────────────────────────────────────────────────────────
class VoiceSettings(BaseModel):
    text: str = Field("", max_length=1500)
    language: str = "tr"
    voice_id: str | None = None  # defaults to the character's voice, then the built-in one
    exaggeration: float = Field(0.5, ge=0.25, le=1.5)  # expressiveness
    cfg_weight: float = Field(0.5, ge=0.0, le=1.0)  # lower = slower, more deliberate delivery
    temperature: float = Field(0.8, ge=0.3, le=1.5)
    seed: int | None = Field(None, ge=0, le=2**31)

    @field_validator("language")
    @classmethod
    def _known_language(cls, v: str) -> str:
        from .voice import LANGUAGES

        if v not in LANGUAGES:
            raise ValueError(f"unsupported language: {v}")
        return v


class SpeakRequest(VoiceSettings):
    character_id: str | None = None

    @model_validator(mode="after")
    def _text_required(self) -> SpeakRequest:
        if not self.text.strip():
            raise ValueError("write the script to speak")
        return self


class TalkRequest(VoiceSettings, MotionBase):
    resolution: Literal["480p"] = "480p"  # InfiniteTalk runs on the 480p Wan 2.1 model
    speech_id: str | None = None  # an existing speech clip instead of `text`
    prompt: str = Field("", max_length=300)  # expression / setting

    @model_validator(mode="after")
    def _one_audio_source(self) -> TalkRequest:
        if bool(self.text.strip()) == bool(self.speech_id):
            raise ValueError("provide either a script or a speech clip")
        return self
