import io
import time
from datetime import date

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.config import paths
from app.main import app
from app.media import probe


def png(color, bg="white", size=400):
    img = Image.new("RGB", (size, size), bg)
    ImageDraw.Draw(img).rectangle((100, 80, 300, 330), fill=color)
    b = io.BytesIO()
    img.save(b, "PNG")
    return b.getvalue()


def wait(c, cid, statuses, timeout=240):
    t = time.time()
    while time.time() - t < timeout:
        vids = c.get(f"/api/campaigns/{cid}").json()["videos"]
        if vids and all(v["status"] in statuses for v in vids):
            return vids
        time.sleep(0.5)
    raise AssertionError(vids)


def test_brand_collection_flow():
    with TestClient(app) as c:
        b = c.post("/api/brands", json={"name": "Acme Ev", "primary_color": "#0E7490", "accent_color": "#22C55E",
                                         "banned_words": "ucuz", "hashtag": "acmeev", "ad_disclosure": "#reklam #acme",
                                         "monthly_fee": 5000, "per_video_fee": 250, "cta": "Acme'de keşfet"}).json()
        logo = Image.new("RGBA", (300, 100), (0, 0, 0, 0))
        ImageDraw.Draw(logo).rectangle((0, 0, 300, 100), fill=(14, 116, 144, 255))
        buf = io.BytesIO(); logo.save(buf, "PNG")
        b = c.post(f"/api/brands/{b['id']}/logo", files={"file": ("l.png", buf.getvalue(), "image/png")}).json()
        assert b["logo_url"]

        colors = [(200, 30, 60), (30, 160, 80), (40, 60, 200)]
        pids = []
        for i, col in enumerate(colors):
            p = c.post("/api/products", json={"name": f"Ürün {i}", "features": "Özellik", "price": 100 + i,
                                              "brand_id": b["id"], "affiliate_url": "https://x.com/p?s={subid}"}).json()
            c.post(f"/api/products/{p['id']}/image", files={"file": ("p.png", png(col), "image/png")})
            pids.append(p["id"])
        assert len(c.get(f"/api/products?brand_id={b['id']}").json()) == 3

        bad = c.post("/api/campaigns", json={"product_ids": pids[:1], "kind": "collection"})
        assert bad.status_code == 422

        camp = c.post("/api/campaigns", json={"product_ids": pids, "kind": "collection", "collection_type": "top_list",
                                              "variants": 1, "auto_render": True}).json()
        assert camp["brand"]["id"] == b["id"] and [x["id"] for x in camp["products"]] == pids and camp["scenes"] == 3
        vids = wait(c, camp["id"], {"done", "failed"})
        v = vids[0]
        assert v["status"] == "done", v["error"]
        sc = v["script"]["scenes"]
        assert [x["product_ref"] for x in sc] == [0, 1, 2]

        d = paths.video_dir(v["id"])
        for i in range(3):
            assert (d / f"badge_{i}.png").exists()
        assert (d / "logo.png").exists()
        # each product scene shows its own product colour (pixel-exact composite)
        for i, col in enumerate(colors):
            im = Image.open(d / f"scene_{i}.png").convert("RGB")
            assert col in {im.getpixel((x, y)) for x in range(300, 470, 10) for y in range(950, 1200, 10)}
        # end card uses brand primary-derived button colour; grid card exists
        assert (d / "endcard.png").exists()
        links = (d / "links.txt").read_text().splitlines()
        assert len(links) == 3 and all(f"{v['subid']}p{pid}" in l for pid, l in zip(pids, links))
        caption = (d / "caption.txt").read_text()
        assert "#acmeev" in caption and "#reklam #acme" in caption
        meta = __import__("asyncio").run(probe(d / f"adforge_{v['id']}.mp4"))
        vs = next(s for s in meta["streams"] if s["codec_type"] == "video")
        assert (vs["width"], vs["height"]) == (1080, 1920)
        assert (d / "subs.ass").exists()

        # per-product attribution from CSV subid
        r = c.post("/api/revenue/import", files={"file": ("r.csv", f"date,subid,amount,clicks\n{date.today()},{v['subid']}p{pids[1]},80,10\n".encode())})
        assert r.json() == {"added": 1, "matched": 1}
        row = c.get(f"/api/revenue?brand_id={b['id']}").json()[0]
        assert row["product_id"] == pids[1] and row["brand_id"] == b["id"] and row["brand_name"] == "Acme Ev"

        # billing: idempotent accrual
        ch1 = c.post(f"/api/brands/{b['id']}/charges/generate").json()
        ch2 = c.post(f"/api/brands/{b['id']}/charges/generate").json()
        assert len(ch1) == len(ch2) == 2
        assert sorted(x["amount"] for x in ch2) == [250.0, 5000.0]
        paid = c.patch(f"/api/brands/charges/{ch2[0]['id']}?paid=true").json()
        assert paid["paid"]

        s = c.get(f"/api/analytics/summary?brand_id={b['id']}").json()
        assert s["fees"]["total"] == 5250 and s["kpi"]["total_revenue"] == 80
        assert any(x["id"] == b["id"] and x["fees"] == 5250 for x in s["by_brand"])

        # approval + review package + report
        z = c.get(f"/api/brands/{b['id']}/review-package?ids={v['id']}")
        assert z.status_code == 200
        assert c.get(f"/api/videos/{v['id']}").json()["approval"] == "sent"
        assert c.patch(f"/api/videos/{v['id']}", json={"approval": "bogus"}).status_code == 422
        rep = c.get(f"/api/brands/{b['id']}/report").text
        assert "Acme Ev" in rep and v["hook"] in rep and "5.000,00 TRY" in rep

        brands = c.get("/api/brands").json()
        assert brands[0]["videos"] == 1 and brands[0]["fees_month"] == 5250


def test_banned_word_retry(monkeypatch):
    import asyncio
    from app.models import Campaign, Product
    from app.pipeline import script
    from app.pipeline.brandkit import BrandStyle

    calls = {"n": 0}

    async def fake(system, user, schema, **kw):
        calls["n"] += 1
        hook = "Bu ucuz ürün harika" if calls["n"] == 1 else "Bu ürün harika"
        assert calls["n"] == 1 or "YASAKLI" in user
        return schema(hook=hook, scenes=[script.Scene(voiceover="v", visual_prompt="p")] * 3, cta="c", caption="x",
                      hashtags=["a"], title="t")

    monkeypatch.setattr(script.ollama, "chat_json", fake)
    style = BrandStyle(1, "B", (0, 0, 0), (0, 0, 0), "#fff", "Arial", None, "", "", "", "", None, "", ["ucuz"], "", "", "")
    s, bad = asyncio.run(script.generate([Product(name="p")], Campaign(product_id=1, name="c", scenes=3), "problem", [],
                                         style=style))
    assert bad == [] and calls["n"] == 2 and "ucuz" not in s.hook


def test_autopilot_brand_collection():
    with TestClient(app) as c:
        b = c.post("/api/brands", json={"name": "Otobrand"}).json()
        for i in range(4):
            p = c.post("/api/products", json={"name": f"O{i}", "brand_id": b["id"]}).json()
            c.post(f"/api/products/{p['id']}/image", files={"file": ("p.png", png((10 * i, 50, 90)), "image/png")})
        other = c.post("/api/products", json={"name": "Yabancı"}).json()
        c.post(f"/api/products/{other['id']}/image", files={"file": ("p.png", png((1, 2, 3)), "image/png")})
        r = c.post("/api/autopilot", json={"name": "Koleksiyon", "brand_id": b["id"], "kind": "collection",
                                          "products_per_video": 3, "videos_per_day": 1}).json()
        camps = c.post(f"/api/autopilot/{r['id']}/run").json()["campaigns"]
        camp = c.get(f"/api/campaigns/{camps[0]}").json()
        assert camp["kind"] == "collection" and len(camp["products"]) == 3
        assert other["id"] not in [x["id"] for x in camp["products"]] and camp["brand"]["id"] == b["id"]
        wait(c, camps[0], {"done", "failed"})
