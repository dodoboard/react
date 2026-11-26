import json
import time

from fastapi.testclient import TestClient

from app.main import app
from app.media import probe


def wait(c, cid, statuses, timeout=180):
    t = time.time()
    while time.time() - t < timeout:
        vids = c.get(f"/api/campaigns/{cid}").json()["videos"]
        if all(v["status"] in statuses for v in vids):
            return vids
        time.sleep(0.5)
    raise AssertionError(vids)


def test_full_dry_run_pipeline():
    with TestClient(app) as c:
        assert c.get("/api/health").json()["dry_run"] is True
        p = c.post("/api/products", json={"name": "Kablosuz Kulaklık X1", "features": "40 saat pil\nANC\nHızlı şarj",
                                          "price": 1299.9, "affiliate_url": "https://example.com/p?aff=1&sub={subid}"}).json()
        camp = c.post("/api/campaigns", json={"product_id": p["id"], "variants": 2, "scenes": 3}).json()
        vids = wait(c, camp["id"], {"scripted"})
        assert len(vids) == 2 and vids[0]["script"]["hook"]
        # edit script then render
        sc = vids[0]["script"]
        sc["hook"] = "Bunu görmeden kulaklık alma"
        assert c.put(f"/api/videos/{vids[0]['id']}/script", json=sc).json()["hook"] == sc["hook"]
        import subprocess
        from app.config import paths as P
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
                        str(P.music / "bed.mp3")], check=True)
        assert c.get("/api/music").json()[0]["name"] == "bed.mp3"
        assert c.post(f"/api/campaigns/{camp['id']}/render").json()["queued"]
        vids = wait(c, camp["id"], {"done", "failed"})
        assert all(v["status"] == "done" for v in vids), [v["error"] for v in vids]

        v = c.get(f"/api/videos/{vids[0]['id']}").json()
        assert v["tracking_url"].endswith("sub=" + v["subid"])
        info = c.get(v["video_url"])
        assert info.status_code == 200 and len(info.content) > 10_000
        from app.config import paths
        meta = __import__("asyncio").run(probe(paths.video_dir(v["id"]) / f"adforge_{v['id']}.mp4"))
        vs = next(s for s in meta["streams"] if s["codec_type"] == "video")
        assert (vs["width"], vs["height"]) == (1080, 1920)
        assert any(s["codec_type"] == "audio" for s in meta["streams"])
        assert abs(float(meta["format"]["duration"]) - v["duration"]) < 0.5

        z = c.get(f"/api/videos/{v['id']}/package")
        assert z.status_code == 200 and z.headers["content-type"] == "application/zip"

        r = c.post("/api/revenue/import", files={"file": ("r.csv", f"date;subid;amount;clicks\n2026-11-20;{v['subid']};250,50;40\n".encode())})
        assert r.json() == {"added": 1, "matched": 1}
        s = c.get("/api/analytics/summary").json()
        assert s["kpi"]["total_revenue"] == 250.5 and s["top_videos"][0]["id"] == v["id"]
        assert s["campaigns"][0]["revenue"] == 250.5
