import random
import sqlite3
from datetime import date, datetime

from PIL import Image, ImageChops, ImageDraw

from app.models import Campaign, engine, migrate
from app.pipeline import insights, product, script, timeline
from app.pipeline.script import AdScript, Scene
from app.providers.tts import Word


def test_migrate_adds_missing_columns(tmp_path):
    db = engine.url.database
    con = sqlite3.connect(db)
    con.execute('CREATE TABLE IF NOT EXISTS "legacy_probe" (id INTEGER PRIMARY KEY)')
    cols_before = {r[1] for r in con.execute('PRAGMA table_info("video")')}
    con.close()
    migrate()  # idempotent on an up-to-date schema
    con = sqlite3.connect(db)
    cols = {r[1] for r in con.execute('PRAGMA table_info("video")')}
    con.close()
    assert {"hook_score", "stage_done", "yt_id"} <= cols and cols_before <= cols


def test_migrate_on_old_schema(tmp_path, monkeypatch):
    from sqlmodel import SQLModel, create_engine
    import app.models as m
    old = tmp_path / "old.db"
    con = sqlite3.connect(old)
    con.execute('CREATE TABLE video (id INTEGER PRIMARY KEY, campaign_id INTEGER, hook VARCHAR)')
    con.execute("INSERT INTO video (campaign_id, hook) VALUES (1, 'x')")
    con.commit()
    con.close()
    eng = create_engine(f"sqlite:///{old}")
    monkeypatch.setattr(m, "engine", eng)
    m.migrate()
    con = sqlite3.connect(old)
    row = con.execute("SELECT stage_done, favorite FROM video").fetchone()
    con.close()
    assert row == ("", 0)


def _product_png(path, bg=(255, 255, 255)):
    img = Image.new("RGB", (400, 400), bg)
    ImageDraw.Draw(img).rectangle((120, 80, 280, 330), fill=(200, 30, 60))
    img.save(path)
    return path


def test_floodfill_cutout_and_composite_preserves_product(tmp_path):
    src = _product_png(tmp_path / "p.png")
    cut = product.make_cutout(src, tmp_path / "cut.png")
    c = Image.open(cut)
    assert c.mode == "RGBA" and abs(c.width - 161) <= 4 and abs(c.height - 251) <= 4
    bg = Image.new("RGB", (768, 1344), (40, 90, 140))
    bg.save(tmp_path / "bg.png")
    out = product.composite(tmp_path / "bg.png", cut, tmp_path / "o.png", "product_hero", 1)
    o = Image.open(out).convert("RGB")
    # center of the product must be the exact product color
    px = [o.getpixel((384, y)) for y in range(700, 900, 20)]
    assert sum(p == (200, 30, 60) for p in px) >= 8


def test_timeline_covers_audio_and_card():
    sc = AdScript(hook="bir iki üç", scenes=[Scene(voiceover="dört beş", visual_prompt="p"),
                                            Scene(voiceover="altı yedi sekiz", visual_prompt="p")],
                  cta="dokuz on", caption="", hashtags=[], title="")
    words = [Word(w, i * 0.5, i * 0.5 + 0.4) for i, w in enumerate("bir iki üç dört beş altı yedi sekiz dokuz on".split())]
    tl = timeline.build(sc, words, 5.0, 2.5)
    assert tl.starts[1] == 2.5 and tl.cta_start == 4.0
    assert abs(sum(tl.scene_durations) + tl.card_duration - tl.total) < 1e-6 and tl.total >= 5.0


def test_thompson_prefers_winning_angle():
    stats = {"deal": insights.AngleStat(clicks=1000, conversions=80), "pov": insights.AngleStat(clicks=1000, conversions=5)}
    wins = sum(insights.choose_angles(1, ["deal", "pov"], seed=i, stats=stats)[0] == "deal" for i in range(200))
    assert wins > 190


def test_tournament_select_best_per_slot():
    scored = [("pov", "a", 4), ("pov", "b", 9), ("deal", "c", 7), ("deal", "d", 8), ("pov", "e", 6)]
    out = script.select(["pov", "deal", "pov"], scored)
    assert [h for _, h, _ in out] == ["b", "d", "e"]


def test_autopilot_slots_and_product_pick():
    from app.api import autopilot
    start = datetime(2026, 11, 26, 18, 0)
    slots = autopilot.next_slots({datetime(2026, 11, 26, 19, 0)}, start, 3)
    assert [s.hour for s in slots] == [21, 12, 19] and slots[1].date() == date(2026, 11, 27)
    rng = random.Random(1)
    from app.models import Product
    pool = [Product(id=i, name=str(i)) for i in range(1, 6)]
    picked = autopilot.pick_products(pool, 3, rng)
    assert len({p.id for p in picked}) == 3


def test_yt_store_rows_and_url_parse():
    from app.api import youtube
    assert youtube.yt_id_from_url("https://youtube.com/shorts/abcdefghijk?x=1") == "abcdefghijk"
    from app.models import Product, Video, session
    with session() as s:
        p = Product(name="yt")
        s.add(p); s.commit(); s.refresh(p)
        c = Campaign(product_id=p.id, name="yt")
        s.add(c); s.commit(); s.refresh(c)
        v = Video(campaign_id=c.id, yt_id="abcdefghijk")
        s.add(v); s.commit(); s.refresh(v)
    resp = {"columnHeaders": [{"name": n} for n in ("day", "views", "averageViewDuration", "averageViewPercentage", "likes", "shares", "subscribersGained")],
            "rows": [["2026-11-20", 1200, 14.2, 61.5, 40, 3, 2], ["2026-11-21", 800, 12.0, 55.0, 20, 1, 0]]}
    assert youtube.store_rows(v.id, resp) == 2
    assert youtube.store_rows(v.id, resp) == 2  # upsert, no duplicates
    from app.models import VideoStat
    with session() as s:
        rows = s.query(VideoStat).filter(VideoStat.video_id == v.id).all()
    assert len(rows) == 2 and sum(r.views for r in rows) == 2000
