import asyncio
import io
import json
import time
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.config import paths
from app.main import app
from app.media import probe


def wait_ep(c, cid, pred, timeout=300):
    t = time.time()
    while time.time() - t < timeout:
        eps = c.get(f"/api/docu/episodes?channel_id={cid}").json()
        if eps and pred(eps):
            return eps
        time.sleep(0.5)
    raise AssertionError(eps)


def avatar_png():
    img = Image.new("RGB", (600, 900), "white")
    d = ImageDraw.Draw(img)
    d.ellipse((200, 120, 400, 360), fill=(200, 160, 130))
    d.rectangle((150, 380, 450, 880), fill=(60, 80, 70))
    b = io.BytesIO(); img.save(b, "PNG")
    return b.getvalue()


def make_channel(c, **kw):
    a = c.post("/api/avatars", files={"file": ("host.png", avatar_png(), "image/png")}).json()
    p = c.post("/api/docu/characters/generate", json={"niche": "tarih gizemleri"}).json()
    ch = c.post("/api/docu/characters", json=p | {"avatar": a["name"]}).json()
    assert ch["avatar_url"]
    prev = c.post(f"/api/docu/characters/{ch['id']}/preview", json={}).json()
    assert prev["url"].endswith(".mp3")
    body = {"name": "Kayıp Tarih", "niche": "tarih gizemleri", "character_id": ch["id"], "format": "both",
            "target_minutes": 1.2, "min_quality": 7} | kw
    return c.post("/api/docu/channels", json=body).json()


def test_topics_sensitive_filter():
    with TestClient(app) as c:
        ch = make_channel(c, name="Konu testi")
        ts = c.post(f"/api/docu/channels/{ch['id']}/topics/generate?n=8").json()
        rejected = [t for t in ts if t["status"] == "rejected"]
        assert rejected and all(t["sensitive"] for t in rejected)  # "Diyet Tedavisi" stub is blocked
        r = c.patch(f"/api/docu/topics/{rejected[0]['id']}", json={"status": "approved"})
        assert r.status_code == 409
        again = c.post(f"/api/docu/channels/{ch['id']}/topics/generate?n=8").json()
        titles = [t["title"] for t in c.get(f"/api/docu/channels/{ch['id']}/topics").json()]
        assert len(titles) == len(set(titles)) and len(again) <= 8
        bad = c.post(f"/api/docu/channels/{ch['id']}/topics", json={"title": "Kripto ile zengin ol"}).json()
        assert bad["status"] == "rejected"


def test_long_episode_end_to_end_with_short_cut():
    with TestClient(app) as c:
        ch = make_channel(c)
        c.post(f"/api/docu/channels/{ch['id']}/topics/generate?n=4")
        ep = c.post(f"/api/docu/channels/{ch['id']}/episodes", json={"kind": "long"}).json()
        eps = wait_ep(c, ch["id"], lambda es: any(e["id"] == ep["id"] and e["status"] in ("ready", "failed") for e in es)
                      and any(e["parent_id"] == ep["id"] and e["status"] == "ready" for e in es))
        long_ = next(e for e in eps if e["id"] == ep["id"])
        assert long_["status"] == "ready", long_["error"]
        assert long_["quality_score"] >= 7
        d = c.get(f"/api/docu/episodes/{ep['id']}").json()
        assert len(d["script"]["chapters"]) >= 3
        assert any(s["kind"] == "presenter" for s in d["script"]["chapters"][0]["segments"])
        wd = paths.media / "episodes" / str(ep["id"])
        meta = asyncio.run(probe(wd / f"episode_{ep['id']}.mp4"))
        vs = next(s for s in meta["streams"] if s["codec_type"] == "video")
        assert (vs["width"], vs["height"]) == (1920, 1080)
        assert abs(float(meta["format"]["duration"]) - long_["duration"]) < 1.0
        assert (wd / "captions.srt").read_text().startswith("1\n00:00:0")
        assert "Bölümler\n00:00 " in d["description"] and "yapay zekâ" in d["description"]
        th = Image.open(wd / "thumbnail.jpg")
        assert th.size == (1280, 720)

        short = next(e for e in eps if e["parent_id"] == ep["id"])
        smeta = asyncio.run(probe(paths.media / "episodes" / str(short["id"]) / f"short_{short['id']}.mp4"))
        sv = next(s for s in smeta["streams"] if s["codec_type"] == "video")
        assert (sv["width"], sv["height"]) == (1080, 1920) and float(smeta["format"]["duration"]) <= 61
        assert short["title"].endswith("#Shorts")


def test_quality_gate_blocks_publication(monkeypatch):
    from app.pipeline.docu import script as ds

    calls = {"n": 0}

    async def low(sc):
        calls["n"] += 1
        return ds.Verdict(score=4, hook=4, flow=4, originality=3, accuracy_risk=8, issues=["tekrar", "kanıtsız iddia"],
                          rewrite_notes="daha temkinli yaz")

    monkeypatch.setattr(ds, "stub_judge", low)
    with TestClient(app) as c:
        ch = make_channel(c, name="Gate", format="long")
        c.post(f"/api/docu/channels/{ch['id']}/topics/generate?n=3")
        ep = c.post(f"/api/docu/channels/{ch['id']}/episodes", json={"kind": "long"}).json()
        eps = wait_ep(c, ch["id"], lambda es: any(e["id"] == ep["id"] and e["status"] in ("needs_review", "ready", "failed") for e in es))
        e = next(x for x in eps if x["id"] == ep["id"])
        assert e["status"] == "needs_review" and calls["n"] == 2 and "Kalite" in e["error"]
        assert e["video_path"] is None


def test_scheduler_and_youtube_upload(monkeypatch):
    from app.pipeline.docu import scheduler
    from app.pipeline.docu.runner import docu_runner
    from app.providers import yt

    calls = []

    class Req:
        def __init__(self, name, kw):
            self.name, self.kw = name, kw

        def next_chunk(self):
            calls.append((self.name, self.kw))
            return None, {"id": f"YT{len(calls):09d}"}

        def execute(self):
            calls.append((self.name, self.kw))
            return {}

    class Res:
        def __init__(self, name):
            self.name = name

        def insert(self, **kw):
            return Req(f"{self.name}.insert", kw)

        def set(self, **kw):
            return Req(f"{self.name}.set", kw)

    class Svc:
        def videos(self): return Res("videos")
        def thumbnails(self): return Res("thumbnails")
        def captions(self): return Res("captions")
        def playlistItems(self): return Res("playlistItems")

    monkeypatch.setattr(yt, "build", lambda api, ver, token: Svc())
    import googleapiclient.http as gh  # noqa: F401  (only if installed)
    monkeypatch.setattr(gh, "MediaFileUpload", lambda *a, **k: ("media", a[0]))

    with TestClient(app) as c:
        ch = make_channel(c, name="Otomatik", format="both", playlist_id="PL123", lead_days=3,
                          schedule_json=json.dumps({"long": [["*", 20]], "shorts": [["*", 13]]}), daily_cap=1, run_hour=0)
        yt.channel_token(ch["id"]).write_text("{}")
        now = datetime.now().replace(minute=0, second=0, microsecond=0)
        # plan: daily_cap=1 → exactly one long episode even though several slots are free
        created = asyncio.run(scheduler.plan(_ch(ch["id"]), now, docu_runner))
        assert len(created) == 1
        eps = wait_ep(c, ch["id"], lambda es: any(e["kind"] == "short" and e["status"] == "ready" for e in es)
                      and all(e["status"] in ("ready", "failed") for e in es))
        long_ = next(e for e in eps if e["kind"] == "long")
        assert long_["slot_at"]
        # a later tick gives the short cut a slot after the long episode and uploads both
        later = now + timedelta(minutes=1)
        asyncio.run(scheduler.plan(_ch(ch["id"]), later, docu_runner))
        used_before = yt.quota_used()
        asyncio.run(scheduler.publish(_ch(ch["id"]), later))
        eps = c.get(f"/api/docu/episodes?channel_id={ch['id']}").json()
        long_ = next(e for e in eps if e["kind"] == "long")
        assert long_["yt_id"].startswith("YT") and long_["status"] == "scheduled"
        ins = [kw for n, kw in calls if n == "videos.insert"]
        body = ins[0]["body"]
        assert body["status"]["containsSyntheticMedia"] is True and body["status"]["privacyStatus"] == "private"
        assert body["status"]["publishAt"].endswith("Z") and body["snippet"]["categoryId"] == "27"
        names = [n for n, _ in calls]
        assert {"thumbnails.set", "captions.insert", "playlistItems.insert"} <= set(names)
        short = next((e for e in eps if e["kind"] == "short"), None)
        if short and short["slot_at"]:
            assert datetime.fromisoformat(short["slot_at"]) > datetime.fromisoformat(long_["slot_at"])
            assert short["yt_id"] and "youtu.be/" + long_["yt_id"] in ins[1]["body"]["snippet"]["description"]
        assert yt.quota_used() - used_before >= yt.EPISODE_COST
        # past slot → published
        asyncio.run(scheduler.publish(_ch(ch["id"]), datetime.fromisoformat(long_["slot_at"]) + timedelta(minutes=1)))
        assert c.get(f"/api/docu/episodes/{long_['id']}").json()["status"] == "published"
        # quota exhausted → no upload
        monkeypatch.setattr(yt, "quota_left", lambda: 100)
        n_before = len(calls)
        asyncio.run(scheduler.publish(_ch(ch["id"]), later))
        assert len(calls) == n_before


def test_slots_and_chapters():
    from app.models import Channel
    from app.pipeline.docu.runner import chapter_lines
    from app.pipeline.docu.scheduler import slots
    c = Channel(name="x", schedule_json=json.dumps({"long": [["tue", 19], ["fri", 19]], "shorts": [["*", 12]]}))
    start = datetime(2026, 11, 23, 10, 0)  # Monday
    assert slots(c, "long", start, 6) == [datetime(2026, 11, 24, 19), datetime(2026, 11, 27, 19)]
    assert len(slots(c, "short", start, 2)) == 3
    assert chapter_lines([(0, "A"), (5, "B")]) == ""
    txt = chapter_lines([(0, "Giriş"), (30, "Orta"), (95, "Son")])
    assert txt.splitlines() == ["Bölümler", "00:00 Giriş", "00:30 Orta", "01:35 Son"]


def _ch(cid):
    from app.models import Channel, session
    with session() as s:
        return s.get(Channel, cid)
