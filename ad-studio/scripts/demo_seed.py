"""Seed a running AdForge (ideally ADF_DRY_RUN=1) with demo products, campaigns and revenue.

usage: python scripts/demo_seed.py [http://127.0.0.1:8000]
"""
from __future__ import annotations

import io
import random
import sys
import time
from datetime import date, timedelta

import httpx
from PIL import Image, ImageDraw

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
BRANDS = [
    {"name": "Nova Elektronik", "primary_color": "#0E7490", "accent_color": "#22D3EE", "hashtag": "novaelektronik",
     "tone": "teknik ama samimi", "banned_words": "ucuz, bedava", "must_say": "2 yıl garanti", "cta": "Nova'da keşfet",
     "monthly_fee": 7500, "per_video_fee": 300, "contact_name": "Ayşe Y.", "website": "nova.example"},
    {"name": "Bloom Home", "primary_color": "#BE185D", "accent_color": "#FDE68A", "hashtag": "bloomhome",
     "tone": "sıcak, estetik", "cta": "Bloom'da sepete ekle", "monthly_fee": 5000, "per_video_fee": 250,
     "contact_name": "Mert K.", "website": "bloom.example"},
]
PRODUCTS = [
    ("Kablosuz Kulaklık Aura X1", "40 saat pil ömrü\nAktif gürültü engelleme\n10 dk şarjla 5 saat\nIPX4 su direnci", 1299.9, "Trendyol", (124, 58, 237)),
    ("Akıllı Termos Kupa 350ml", "Sıcaklığı 12 saat korur\nLED sıcaklık göstergesi\nSızdırmaz kapak", 449.0, "Hepsiburada", (236, 72, 153)),
    ("Mini Projektör Lumo", "1080p destek\n120 inç görüntü\nDahili hoparlör\nTelefonla kablosuz bağlantı", 2899.0, "Amazon", (14, 165, 233)),
    ("Aroma Difüzör Zen", "Ultrasonik sessiz çalışma\n7 renk ışık\n8 saat otomatik kapanma", 649.0, "Trendyol", (217, 119, 6)),
    ("Keten Yastık Kılıfı", "%100 keten\n45x45 cm\nGizli fermuar", 299.0, "Trendyol", (120, 113, 108)),
    ("Seramik Vazo Duo", "El yapımı\nMat sır\n2'li set", 549.0, "Hepsiburada", (190, 24, 93)),
]
BRAND_OF = [0, 1, 0, 1, 1, 1]


def logo_png(text: str, color: tuple[int, int, int]) -> bytes:
    img = Image.new("RGBA", (420, 140), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 20, 100, 120), 24, fill=color)
    d.ellipse((30, 50, 70, 90), fill=(255, 255, 255))
    d.text((120, 45), text, fill=color, font_size=46)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def product_png(color: tuple[int, int, int]) -> bytes:
    img = Image.new("RGB", (800, 800), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((200, 160, 600, 640), 80, fill=color)
    d.ellipse((300, 260, 500, 460), fill=(255, 255, 255))
    d.ellipse((350, 310, 450, 410), fill=tuple(int(c * 0.6) for c in color))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def main() -> None:
    c = httpx.Client(base_url=BASE, timeout=60)
    brands = []
    for b in BRANDS:
        r = c.post("/api/brands", json=b).json()
        col = tuple(int(b["primary_color"][i:i + 2], 16) for i in (1, 3, 5))
        c.post(f"/api/brands/{r['id']}/logo", files={"file": ("l.png", logo_png(b["name"].split()[0], col), "image/png")})
        brands.append(r)
    camps, pids = [], []
    for (name, feats, price, platform, color), bi in zip(PRODUCTS, BRAND_OF):
        p = c.post("/api/products", json={"name": name, "features": feats, "price": price, "platform": platform,
                                          "brand_id": brands[bi]["id"],
                                          "description": f"{name} — günlük kullanım için tasarlandı.",
                                          "affiliate_url": f"https://example.com/p/{random.randint(1000, 9999)}?aff=demo&sub={{subid}}",
                                          "commission_rate": random.choice([5, 8, 10, 12])}).json()
        c.post(f"/api/products/{p['id']}/image", files={"file": ("p.png", product_png(color), "image/png")})
        pids.append(p["id"])
        if len(camps) >= 3:
            continue
        camps.append(c.post("/api/campaigns", json={"product_id": p["id"], "variants": 4, "scenes": 3,
                                                     "auto_render": True, "tone": random.choice(["enerjik", "samimi", "lüks"])}).json())
    home = [pid for pid, bi in zip(pids, BRAND_OF) if bi == 1][1:]
    camps.append(c.post("/api/campaigns", json={"product_ids": home, "kind": "collection", "collection_type": "top_list",
                                                 "variants": 2, "auto_render": True}).json())
    print("rendering…", end="", flush=True)
    while any(v["status"] not in ("done", "failed") for v in c.get("/api/videos").json()):
        print(".", end="", flush=True)
        time.sleep(2)
    print()
    vids = c.get("/api/videos?status=done").json()
    for i, v in enumerate(vids):
        when = (date.today() + timedelta(days=i % 9 - 3)).isoformat()
        if i % 3 == 0:
            c.patch(f"/api/videos/{v['id']}", json={"published_at": f"{when}T19:00:00", "platform": random.choice(["tiktok", "reels", "youtube"])})
        elif i % 3 == 1:
            c.patch(f"/api/videos/{v['id']}", json={"scheduled_at": f"{(date.today() + timedelta(days=i % 6 + 1)).isoformat()}T21:00:00"})
    for d in range(28):
        day = date.today() - timedelta(days=d)
        for v in random.sample(vids, k=min(len(vids), random.randint(1, 3))):
            clicks = random.randint(20, 400)
            conv = random.randint(0, max(1, clicks // 25))
            c.post("/api/revenue", json={"day": day.isoformat(), "video_id": v["id"], "platform": random.choice(["tiktok", "reels", "youtube"]),
                                         "amount": round(conv * random.uniform(30, 140), 2), "clicks": clicks, "conversions": conv,
                                         "views": clicks * random.randint(20, 60)})
    for b in brands:
        c.post(f"/api/brands/{b['id']}/charges/generate")
    for v in vids[:4]:
        c.patch(f"/api/videos/{v['id']}", json={"approval": random.choice(["sent", "approved", "revision"])})
    # documentary channel with a presenter character
    av = Image.new("RGB", (600, 900), (38, 42, 52))
    d = ImageDraw.Draw(av)
    d.ellipse((200, 130, 400, 370), fill=(214, 172, 140))
    d.rectangle((140, 390, 460, 900), fill=(92, 84, 60))
    buf = io.BytesIO(); av.save(buf, "PNG")
    a = c.post("/api/avatars", files={"file": ("deniz.png", buf.getvalue(), "image/png")}).json()
    persona = c.post("/api/docu/characters/generate", json={"niche": "antik uygarlıklar"}).json()
    ch = c.post("/api/docu/characters", json=persona | {"avatar": a["name"]}).json()
    chan = c.post("/api/docu/channels", json={"name": "Kayıp Uygarlıklar", "niche": "antik uygarlıklar ve kayıp şehirler",
                                              "character_id": ch["id"], "format": "both", "target_minutes": 1.5}).json()
    c.post(f"/api/docu/channels/{chan['id']}/topics/generate?n=8")
    ep = c.post(f"/api/docu/channels/{chan['id']}/episodes", json={"kind": "long"}).json()
    print("documentary rendering…", end="", flush=True)
    while c.get(f"/api/docu/episodes/{ep['id']}").json()["status"] not in ("ready", "failed", "needs_review"):
        print(".", end="", flush=True)
        time.sleep(3)
    print()
    print(f"seeded {len(brands)} brands, {len(PRODUCTS)} products, {len(camps)} campaigns, {len(vids)} videos")


if __name__ == "__main__":
    main()
