"""YouTube Data API helpers shared by ad uploads and the documentary channels (per-channel OAuth tokens + quota)."""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from ..config import boot, config
from ..models import ApiQuota, session

SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly",
          "https://www.googleapis.com/auth/yt-analytics.readonly", "https://www.googleapis.com/auth/youtube.force-ssl"]
SECRET = boot.data_dir / "youtube_client_secret.json"
TOKENS = boot.data_dir / "youtube_tokens"
COST = {"insert": 1600, "thumbnail": 50, "caption": 400, "playlist": 50}
EPISODE_COST = COST["insert"] + COST["thumbnail"] + COST["caption"] + COST["playlist"]


class YTError(RuntimeError):
    pass


def channel_token(channel_id: int) -> Path:
    TOKENS.mkdir(parents=True, exist_ok=True)
    return TOKENS / f"channel_{channel_id}.json"


def creds(token: Path):
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError as e:
        raise YTError("pip install -r requirements-youtube.txt") from e
    if not token.exists():
        return None
    c = Credentials.from_authorized_user_file(str(token))
    if c.expired and c.refresh_token:
        c.refresh(Request())
        token.write_text(c.to_json())
    return c if c.valid else None


def run_flow(token: Path) -> None:
    if not SECRET.exists():
        raise YTError(f"OAuth client JSON yok: {SECRET}")
    from google_auth_oauthlib.flow import InstalledAppFlow
    c = InstalledAppFlow.from_client_secrets_file(str(SECRET), SCOPES).run_local_server(port=0, open_browser=True)
    token.write_text(c.to_json())


def build(api: str, version: str, token: Path):
    from googleapiclient.discovery import build as _build
    c = creds(token)
    if not c:
        raise YTError("YouTube hesabı bağlı değil")
    return _build(api, version, credentials=c, cache_discovery=False)


# ---------- quota ----------
def quota_used(day: date | None = None) -> int:
    with session() as s:
        q = s.query(ApiQuota).filter(ApiQuota.day == (day or date.today())).first()
        return q.units if q else 0


def quota_add(units: int) -> None:
    with session() as s:
        q = s.query(ApiQuota).filter(ApiQuota.day == date.today()).first() or ApiQuota(day=date.today())
        q.units += units
        s.add(q)
        s.commit()


def quota_left() -> int:
    return config.get().youtube_daily_quota - quota_used()


# ---------- upload ----------
def _rfc3339(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def upload_episode(token: Path, video: Path, title: str, description: str, tags: list[str], category: str,
                   privacy: str, publish_at: datetime | None, thumb: Path | None, srt: Path | None,
                   language: str, playlist: str = "") -> str:
    """videos.insert → thumbnails.set → captions.insert → playlistItems.insert. Returns the YouTube video id."""
    from googleapiclient.http import MediaFileUpload

    if quota_left() < EPISODE_COST:
        raise YTError("Günlük YouTube API kotası yetersiz — yarın yeniden denenecek")
    yt = build("youtube", "v3", token)
    status = {"selfDeclaredMadeForKids": False, "containsSyntheticMedia": True, "privacyStatus": privacy}
    if publish_at and publish_at > datetime.now():
        status |= {"privacyStatus": "private", "publishAt": _rfc3339(publish_at)}
    body = {"snippet": {"title": title[:100], "description": description[:4900], "tags": tags[:30],
                        "categoryId": category, "defaultLanguage": language, "defaultAudioLanguage": language},
            "status": status}
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(str(video), chunksize=-1, resumable=True))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    quota_add(COST["insert"])
    vid = resp["id"]
    if thumb and thumb.exists():
        try:
            yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(str(thumb))).execute()
        finally:
            quota_add(COST["thumbnail"])
    if srt and srt.exists():
        try:
            yt.captions().insert(part="snippet", body={"snippet": {"videoId": vid, "language": language, "name": "",
                                                                    "isDraft": False}},
                                 media_body=MediaFileUpload(str(srt), mimetype="application/octet-stream")).execute()
        finally:
            quota_add(COST["caption"])
    if playlist:
        try:
            yt.playlistItems().insert(part="snippet", body={"snippet": {"playlistId": playlist, "resourceId": {
                "kind": "youtube#video", "videoId": vid}}}).execute()
        finally:
            quota_add(COST["playlist"])
    return vid


def channel_info(token: Path) -> dict:
    yt = build("youtube", "v3", token)
    r = yt.channels().list(part="snippet,statistics", mine=True).execute()
    items = r.get("items") or []
    if not items:
        return {}
    it = items[0]
    return {"id": it["id"], "title": it["snippet"]["title"], "thumbnail": it["snippet"]["thumbnails"]["default"]["url"],
            "subscribers": int(it.get("statistics", {}).get("subscriberCount", 0) or 0)}
