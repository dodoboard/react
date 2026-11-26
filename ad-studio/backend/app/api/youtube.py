"""Optional YouTube Shorts upload (Data API v3, OAuth installed-app flow). pip install -r requirements-youtube.txt"""
from __future__ import annotations

import asyncio
import json
import re
from datetime import date, datetime, timedelta

from fastapi import APIRouter, HTTPException, UploadFile

from ..config import boot, config, paths
from ..models import Video, VideoStat, session
from ..providers import yt
from ..providers.yt import SCOPES
from ..pipeline.runner import load, update
from ..pipeline.script import AdScript

router = APIRouter(prefix="/api/youtube", tags=["youtube"])
SECRET = yt.SECRET
TOKEN = boot.data_dir / "youtube_token.json"


def _creds():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError as e:
        raise HTTPException(501, "pip install -r requirements-youtube.txt") from e
    if not TOKEN.exists():
        return None
    creds = Credentials.from_authorized_user_file(str(TOKEN))
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN.write_text(creds.to_json())
    return creds if creds.valid else None


@router.get("/status")
def status() -> dict:
    try:
        creds = _creds()
        installed = True
    except HTTPException:
        creds, installed = None, False
    granted = set(getattr(creds, "scopes", None) or [])
    return {"installed": installed, "has_secret": SECRET.exists(), "connected": creds is not None,
            "analytics": bool(creds) and SCOPES[2] in granted}


@router.post("/connect")
async def connect() -> dict:
    if not SECRET.exists():
        raise HTTPException(400, f"Google Cloud OAuth (Desktop) client JSON dosyasını {SECRET} konumuna koyun.")
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as e:
        raise HTTPException(501, "pip install -r requirements-youtube.txt") from e

    def flow():
        InstalledAppFlow  # noqa: B018  (import check above)
        yt.run_flow(TOKEN)

    await asyncio.to_thread(flow)
    return status()


def upload_sync(vid: int) -> str:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds = _creds()
    if not creds:
        raise HTTPException(400, "YouTube bağlı değil")
    v, _, _ = load(vid)
    if not v.video_path:
        raise HTTPException(400, "Video hazır değil")
    sc = AdScript.model_validate_json(v.script_json)
    caption = (paths.video_dir(vid) / "caption.txt").read_text(encoding="utf-8")
    body = {
        "snippet": {"title": (sc.title or sc.hook)[:95] + " #shorts", "description": caption[:4900],
                    "tags": sc.hashtags[:15], "categoryId": "22"},
        "status": {"privacyStatus": config.get().youtube_privacy, "selfDeclaredMadeForKids": False,
                   "containsSyntheticMedia": True},
    }
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload(v.video_path, chunksize=-1, resumable=True))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    return resp["id"]


@router.post("/upload/{vid}")
async def upload(vid: int) -> dict:
    yid = await asyncio.to_thread(upload_sync, vid)
    url = f"https://youtube.com/shorts/{yid}"
    update(vid, published_at=datetime.now(), publish_url=url, platform="youtube", yt_id=yid)
    return {"url": url}


def yt_id_from_url(url: str) -> str:
    m = re.search(r"(?:shorts/|v=|youtu\.be/)([A-Za-z0-9_-]{11})", url or "")
    return m.group(1) if m else ""


def analytics_sync_blocking(days: int = 28) -> int:
    """Pull per-day stats for every uploaded video into VideoStat. Returns rows written."""
    from googleapiclient.discovery import build

    creds = _creds()
    if not creds or SCOPES[2] not in set(creds.scopes or []):
        return 0
    with session() as s:
        vids = [(v.id, v.yt_id) for v in s.query(Video).filter(Video.yt_id != "").all()]
    if not vids:
        return 0
    yta = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)
    end = date.today()
    start = end - timedelta(days=days)
    written = 0
    for vid, yid in vids:
        resp = yta.reports().query(
            ids="channel==MINE", startDate=start.isoformat(), endDate=end.isoformat(), dimensions="day",
            metrics="views,averageViewDuration,averageViewPercentage,likes,shares,subscribersGained",
            filters=f"video=={yid}", sort="day").execute()
        written += store_rows(vid, resp)
    return written


def store_rows(vid: int, resp: dict) -> int:
    cols = [h["name"] for h in resp.get("columnHeaders", [])]
    rows = [dict(zip(cols, r)) for r in resp.get("rows", []) or []]
    with session() as s:
        for r in rows:
            day = date.fromisoformat(r["day"])
            st = s.query(VideoStat).filter(VideoStat.video_id == vid, VideoStat.day == day, VideoStat.source == "youtube").first() \
                or VideoStat(video_id=vid, day=day, source="youtube")
            st.views = int(r.get("views", 0))
            st.avg_view_duration = float(r.get("averageViewDuration", 0))
            st.avg_view_pct = float(r.get("averageViewPercentage", 0))
            st.likes = int(r.get("likes", 0))
            st.shares = int(r.get("shares", 0))
            st.subs_gained = int(r.get("subscribersGained", 0))
            s.add(st)
        s.commit()
    return len(rows)


@router.post("/analytics/sync")
async def analytics_sync() -> dict:
    try:
        n = await asyncio.to_thread(analytics_sync_blocking)
    except ImportError as e:
        raise HTTPException(501, "pip install -r requirements-youtube.txt") from e
    return {"rows": n}


@router.post("/secret")
async def save_secret(file: UploadFile) -> dict:
    raw = await file.read()
    try:
        json.loads(raw)
    except ValueError as e:
        raise HTTPException(400, "Geçersiz JSON") from e
    SECRET.write_bytes(raw)
    return status()
