from __future__ import annotations

from datetime import date, datetime

from pydantic import NaiveDatetime
from enum import Enum

from sqlmodel import Field, Session, SQLModel, create_engine

from .config import paths


def now() -> datetime:
    return datetime.now()


class VideoStatus(str, Enum):
    queued = "queued"
    scripting = "scripting"
    scripted = "scripted"  # waiting for review / render
    visuals = "visuals"
    voice = "voice"
    composing = "composing"
    done = "done"
    failed = "failed"
    cancelled = "cancelled"


ACTIVE = {VideoStatus.queued, VideoStatus.scripting, VideoStatus.visuals, VideoStatus.voice, VideoStatus.composing}


class Product(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    description: str = ""
    features: str = ""  # newline separated
    price: float | None = None
    currency: str = "TRY"
    affiliate_url: str = ""  # may contain {subid}
    platform: str = ""  # Trendyol, Amazon, Hepsiburada...
    commission_rate: float | None = None  # %
    image_path: str | None = None
    created_at: NaiveDatetime = Field(default_factory=now)


class Campaign(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="product.id", index=True)
    name: str
    language: str = "tr"
    tone: str = "enerjik"
    audience: str = ""
    angle_notes: str = ""
    visual_style: str = ""
    voice_id: str = ""
    variants: int = 3
    scenes: int = 4
    use_i2v: bool = False
    music: str = ""  # filename in data/music, "" = random, "none" = off
    target_platform: str = "tiktok"
    created_at: NaiveDatetime = Field(default_factory=now)


class Video(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    campaign_id: int = Field(foreign_key="campaign.id", index=True)
    variant_index: int = 0
    angle: str = ""
    hook: str = ""
    script_json: str = ""
    caption: str = ""
    status: VideoStatus = VideoStatus.queued
    step: str = ""
    progress: float = 0
    error: str = ""
    video_path: str | None = None
    thumb_path: str | None = None
    duration: float | None = None
    tts_chars: int = 0
    render_seconds: float = 0
    subid: str = Field(default="", index=True)
    ab_label: str = ""
    favorite: bool = False
    platform: str = ""
    scheduled_at: NaiveDatetime | None = None
    published_at: NaiveDatetime | None = None
    publish_url: str = ""
    created_at: NaiveDatetime = Field(default_factory=now)
    updated_at: NaiveDatetime = Field(default_factory=now)


class RevenueEntry(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    day: date = Field(default_factory=date.today, index=True)
    video_id: int | None = Field(default=None, foreign_key="video.id", index=True)
    campaign_id: int | None = Field(default=None, foreign_key="campaign.id", index=True)
    platform: str = ""
    amount: float = 0
    clicks: int = 0
    conversions: int = 0
    views: int = 0
    note: str = ""


engine = create_engine(f"sqlite:///{paths.db}", connect_args={"check_same_thread": False})


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def session() -> Session:
    return Session(engine, expire_on_commit=False)
