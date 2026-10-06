from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _env(name: str, default: str) -> str:
    return os.environ.get(f"STUDIO_{name}", default)


@dataclass(frozen=True)
class Settings:
    comfy_url: str = field(default_factory=lambda: _env("COMFY_URL", "http://127.0.0.1:8188"))
    data_dir: Path = field(default_factory=lambda: Path(_env("DATA_DIR", str(PROJECT_ROOT / "data"))))
    profile: str = field(default_factory=lambda: _env("PROFILE", "klein-4b"))
    host: str = field(default_factory=lambda: _env("HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(_env("PORT", "7860")))
    frontend_dist: Path = field(default_factory=lambda: PROJECT_ROOT / "frontend" / "dist")
