"""Optional YouTube Shorts upload (Data API v3, OAuth installed-app flow). pip install -r requirements-youtube.txt"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, HTTPException, UploadFile

from ..config import boot, config, paths
from ..pipeline.runner import load, update
from ..pipeline.script import AdScript

router = APIRouter(prefix="/api/youtube", tags=["youtube"])
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
SECRET = boot.data_dir / "youtube_client_secret.json"
TOKEN = boot.data_dir / "youtube_token.json"


def _creds():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError as e:
        raise HTTPException(501, "pip install -r requirements-youtube.txt") from e
    if not TOKEN.exists():
        return None
    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN.write_text(creds.to_json())
    return creds if creds.valid else None


@router.get("/status")
def status() -> dict:
    try:
        ok = _creds() is not None
        installed = True
    except HTTPException:
        ok, installed = False, False
    return {"installed": installed, "has_secret": SECRET.exists(), "connected": ok}


@router.post("/connect")
async def connect() -> dict:
    if not SECRET.exists():
        raise HTTPException(400, f"Google Cloud OAuth (Desktop) client JSON dosyasını {SECRET} konumuna koyun.")
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as e:
        raise HTTPException(501, "pip install -r requirements-youtube.txt") from e

    def flow():
        creds = InstalledAppFlow.from_client_secrets_file(str(SECRET), SCOPES).run_local_server(port=0, open_browser=True)
        TOKEN.write_text(creds.to_json())

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
    return f"https://youtube.com/shorts/{resp['id']}"


@router.post("/upload/{vid}")
async def upload(vid: int) -> dict:
    url = await asyncio.to_thread(upload_sync, vid)
    update(vid, published_at=datetime.now(), publish_url=url, platform="youtube")
    return {"url": url}


@router.post("/secret")
async def save_secret(file: UploadFile) -> dict:
    raw = await file.read()
    try:
        json.loads(raw)
    except ValueError as e:
        raise HTTPException(400, "Geçersiz JSON") from e
    SECRET.write_bytes(raw)
    return status()
