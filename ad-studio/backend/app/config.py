"""Two layers: boot settings from env (.env, ADF_ prefix) and user-editable runtime config (data/config.json)."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class BootSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_prefix="ADF_", extra="ignore")

    data_dir: Path = ROOT / "data"
    host: str = "127.0.0.1"
    port: int = 8000
    dry_run: bool = False  # stub providers: no GPU / API key required


boot = BootSettings()


class RuntimeConfig(BaseModel):
    # LLM
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:14b"
    ollama_temperature: float = 0.85
    # Image / video
    comfy_url: str = "http://127.0.0.1:8188"
    image_workflow: str = "flux_t2i"
    video_workflow: str = "wan22_i2v"
    use_i2v: bool = False  # legacy; campaigns use i2v_mode
    i2v_mode: Literal["off", "hook", "all"] = "off"
    product_mode: Literal["composite", "kontext", "off"] = "composite"
    kontext_workflow: str = "kontext_product"
    avatar_workflow: str = "wan22_s2v"
    image_steps: int = 20
    negative_prompt: str = "text, watermark, logo, blurry, deformed hands, extra fingers, low quality, jpeg artifacts"
    style_suffix: str = "cinematic commercial product photography, soft studio lighting, shallow depth of field, ultra detailed, 9:16 vertical composition"
    # Voice
    tts_provider: Literal["elevenlabs", "chatterbox"] = "elevenlabs"
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "EXAVITQu4vr4xnSDxMaL"
    elevenlabs_model: str = "eleven_multilingual_v2"
    chatterbox_voice: str = ""  # reference wav name in data/voices
    whisper_model: str = "small"
    # Composition
    video_encoder: Literal["auto", "h264_nvenc", "libx264"] = "auto"
    subtitle_font: str = "Montserrat ExtraBold"
    subtitle_highlight: str = "#FFD400"
    caption_style: Literal["bold_yellow", "white_box", "gradient_pop"] = "bold_yellow"
    music_volume: float = 0.18
    sfx_volume: float = 0.35
    progress_bar: bool = True
    hook_punch: bool = True
    price_badge: bool = True
    end_card_seconds: float = 2.5
    # Brand / compliance
    brand_name: str = ""
    cta_default: str = "Link profilde 👆"
    ad_disclosure: str = "#reklam #işbirliği"
    ai_label: bool = True
    # Economics
    currency: str = "TRY"
    tts_cost_per_1k_chars: float = 10.0
    gpu_watts: float = 360
    kwh_price: float = 3.0
    # Learning
    hook_tournament: bool = True
    hooks_per_slot: int = 3
    # YouTube
    youtube_privacy: Literal["private", "unlisted", "public"] = "private"
    youtube_auto_upload: bool = False


class ConfigStore:
    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.Lock()
        self._cfg = RuntimeConfig.model_validate(json.loads(path.read_text())) if path.exists() else RuntimeConfig()

    def get(self) -> RuntimeConfig:
        return self._cfg

    def update(self, patch: dict) -> RuntimeConfig:
        with self._lock:
            self._cfg = RuntimeConfig.model_validate({**self._cfg.model_dump(), **patch})
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(self._cfg.model_dump(), indent=2, ensure_ascii=False))
            return self._cfg


class Paths(BaseModel):
    root: Path = Field(default_factory=lambda: boot.data_dir)

    @property
    def db(self) -> Path: return self.root / "adforge.db"
    @property
    def media(self) -> Path: return self.root / "media"
    @property
    def products(self) -> Path: return self.media / "products"
    @property
    def renders(self) -> Path: return self.media / "renders"
    @property
    def music(self) -> Path: return self.root / "music"
    @property
    def voices(self) -> Path: return self.root / "voices"
    @property
    def fonts(self) -> Path: return self.root / "fonts"
    @property
    def avatars(self) -> Path: return self.media / "avatars"

    def ensure(self) -> None:
        for p in (self.media, self.products, self.renders, self.music, self.voices, self.fonts, self.avatars):
            p.mkdir(parents=True, exist_ok=True)

    def video_dir(self, video_id: int) -> Path:
        d = self.renders / str(video_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def url(self, p: Path | str | None) -> str | None:
        if not p:
            return None
        return "/media/" + Path(p).resolve().relative_to(self.media.resolve()).as_posix()


paths = Paths()
paths.ensure()
config = ConfigStore(boot.data_dir / "config.json")
WORKFLOWS_DIR = Path(__file__).resolve().parents[1] / "workflows"
