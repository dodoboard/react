from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import NaiveDatetime
from sqlalchemy import text
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


class Brand(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    logo_path: str | None = None
    primary_color: str = "#8B5CF6"
    accent_color: str = "#FFD400"
    font_file: str = ""  # file in data/fonts
    voice_id: str = ""
    tone: str = ""
    audience: str = ""
    guidelines: str = ""
    banned_words: str = ""  # comma separated
    must_say: str = ""
    cta: str = ""
    ad_disclosure: str = ""
    hashtag: str = ""
    website: str = ""
    contact_name: str = ""
    contact_email: str = ""
    monthly_fee: float = 0
    per_video_fee: float = 0
    currency: str = "TRY"
    active: bool = True
    created_at: NaiveDatetime = Field(default_factory=now)


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
    brand_id: int | None = Field(default=None, foreign_key="brand.id", index=True)
    image_path: str | None = None
    cutout_path: str | None = None
    active: bool = True  # autopilot pool
    created_at: NaiveDatetime = Field(default_factory=now)


class Campaign(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="product.id", index=True)  # first product (back-compat)
    brand_id: int | None = Field(default=None, foreign_key="brand.id", index=True)
    kind: str = "single"  # single | collection
    collection_type: str = ""  # top_list | bundle | comparison | sale | gift_guide
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
    i2v_mode: str = "off"  # off | hook | all
    format: str = "broll"  # broll | avatar_hook | avatar_full
    avatar: str = ""  # file in data/avatars
    autopilot_id: int | None = None
    music: str = ""  # filename in data/music, "" = random, "none" = off
    target_platform: str = "tiktok"
    created_at: NaiveDatetime = Field(default_factory=now)


class Video(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    campaign_id: int = Field(foreign_key="campaign.id", index=True)
    variant_index: int = 0
    angle: str = ""
    hook: str = ""
    hook_score: float | None = None
    stage_done: str = ""  # last completed stage, for resume
    yt_id: str = ""
    approval: str = "draft"  # draft | sent | approved | revision
    approval_note: str = ""
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
    product_id: int | None = Field(default=None, foreign_key="product.id", index=True)
    brand_id: int | None = Field(default=None, foreign_key="brand.id", index=True)
    kind: str = "affiliate"  # affiliate | fee
    platform: str = ""
    amount: float = 0
    clicks: int = 0
    conversions: int = 0
    views: int = 0
    note: str = ""


class CampaignProduct(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    campaign_id: int = Field(foreign_key="campaign.id", index=True)
    product_id: int = Field(foreign_key="product.id", index=True)
    position: int = 0


class BrandCharge(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    brand_id: int = Field(foreign_key="brand.id", index=True)
    period: str = Field(index=True)  # YYYY-MM
    kind: str = "monthly"  # monthly | per_video | extra
    quantity: int = 1
    amount: float = 0
    paid: bool = False
    paid_at: NaiveDatetime | None = None
    note: str = ""
    created_at: NaiveDatetime = Field(default_factory=now)


class VideoStat(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    video_id: int = Field(foreign_key="video.id", index=True)
    day: date = Field(index=True)
    source: str = "youtube"
    views: int = 0
    avg_view_duration: float = 0
    avg_view_pct: float = 0
    likes: int = 0
    shares: int = 0
    subs_gained: int = 0


class AutopilotRule(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = "Otopilot"
    enabled: bool = True
    brand_id: int | None = None
    kind: str = "single"
    collection_type: str = "top_list"
    products_per_video: int = 3
    product_ids: str = ""  # comma separated; empty = all active products
    videos_per_day: int = 3
    run_hour: int = 2  # local hour to start production
    platform: str = "tiktok"
    language: str = "tr"
    format: str = "broll"
    avatar: str = ""
    i2v_mode: str = "off"
    auto_schedule: bool = True
    last_run: date | None = None
    created_at: NaiveDatetime = Field(default_factory=now)


class Character(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    persona: str = ""
    speaking_style: str = ""
    catchphrases: str = ""
    opening_line: str = ""
    closing_line: str = ""
    look_prompt: str = ""
    avatar: str = ""  # file in media/avatars
    voice_id: str = ""
    voice_settings: str = ""  # json: stability, similarity_boost, style, speed | exaggeration, cfg_weight
    language: str = "tr"
    created_at: NaiveDatetime = Field(default_factory=now)


class Channel(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    niche: str = ""
    language: str = "tr"
    character_id: int | None = Field(default=None, foreign_key="character.id")
    format: str = "both"  # long | shorts | both
    target_minutes: float = 8
    visual_style: str = "cinematic documentary photography, natural light, rich detail, 35mm film look"
    music: str = ""
    privacy: str = "public"
    category_id: str = "27"
    default_tags: str = ""
    playlist_id: str = ""
    schedule_json: str = '{"long": [["tue", 19], ["fri", 19]], "shorts": [["*", 12]]}'
    lead_days: int = 2
    daily_cap: int = 3
    min_quality: float = 7.0
    paused: bool = False
    run_hour: int = 1
    created_at: NaiveDatetime = Field(default_factory=now)


class Topic(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    channel_id: int = Field(foreign_key="channel.id", index=True)
    title: str
    angle: str = ""
    hook: str = ""
    score: float = 0
    sensitive: bool = False
    sensitive_reason: str = ""
    status: str = "idea"  # idea | approved | rejected | used
    created_at: NaiveDatetime = Field(default_factory=now)


class Episode(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    channel_id: int = Field(foreign_key="channel.id", index=True)
    topic_id: int | None = Field(default=None, foreign_key="topic.id")
    kind: str = "long"  # long | short
    parent_id: int | None = None
    status: str = "queued"
    progress: float = 0
    step: str = ""
    error: str = ""
    stage_done: str = ""
    outline_json: str = ""
    script_json: str = ""
    quality_json: str = ""
    quality_score: float | None = None
    title: str = ""
    description: str = ""
    tags: str = ""
    chapters_json: str = ""
    video_path: str | None = None
    thumb_path: str | None = None
    srt_path: str | None = None
    duration: float | None = None
    slot_at: NaiveDatetime | None = None
    yt_id: str = ""
    published_at: NaiveDatetime | None = None
    render_seconds: float = 0
    created_at: NaiveDatetime = Field(default_factory=now)
    updated_at: NaiveDatetime = Field(default_factory=now)


class EpisodeStat(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    episode_id: int = Field(foreign_key="episode.id", index=True)
    day: date = Field(index=True)
    views: int = 0
    avg_view_duration: float = 0
    avg_view_pct: float = 0
    likes: int = 0
    subs_gained: int = 0


class ApiQuota(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    day: date = Field(index=True, unique=True)
    units: int = 0


engine = create_engine(f"sqlite:///{paths.db}", connect_args={"check_same_thread": False})


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    migrate()


def migrate() -> None:
    """Add columns introduced after a table was created (SQLite ADD COLUMN only)."""
    with engine.begin() as conn:
        for table in SQLModel.metadata.sorted_tables:
            have = {r[1] for r in conn.execute(text(f'PRAGMA table_info("{table.name}")'))}
            if not have:  # table missing entirely: create_all handles it
                continue
            for col in table.columns:
                if col.name in have:
                    continue
                ddl = col.type.compile(engine.dialect)
                default = col.default.arg if col.default is not None and not callable(col.default.arg) else None
                dflt = "" if default is None else f" DEFAULT {int(default) if isinstance(default, bool) else repr(default.value if isinstance(default, Enum) else default)}"
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {ddl}{dflt}'))


def session() -> Session:
    return Session(engine, expire_on_commit=False)
