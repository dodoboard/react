from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import autopilot, campaigns, products, revenue, system, youtube
from .config import ROOT, boot, config, paths
from .events import broker
from .models import Video, init_db, session
from .pipeline.runner import runner

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("adforge")


async def scheduler() -> None:
    """Every minute: autopilot runs, auto-scheduling, due-post notifications, YouTube auto-upload; analytics every 6h."""
    notified: set[int] = set()
    last_sync = 0.0
    while True:
        await asyncio.sleep(60)
        now = datetime.now()
        try:
            for rule in autopilot.due_rules(now):
                ids = autopilot.run_rule(rule)
                broker.publish("autopilot", {"rule": rule.name, "campaigns": ids})
            if autopilot.auto_schedule(now):
                broker.publish("queue", runner.snapshot())
        except Exception:
            log.exception("autopilot")
        if time.time() - last_sync > 6 * 3600:
            last_sync = time.time()
            try:
                n = await asyncio.to_thread(youtube.analytics_sync_blocking)
                if n:
                    log.info("YouTube analytics: %s satır", n)
            except Exception as e:
                log.info("YouTube analytics atlandı: %s", e)
        try:
            with session() as s:
                due = s.query(Video).filter(Video.scheduled_at <= datetime.now(), Video.published_at.is_(None),
                                            Video.video_path.is_not(None)).all()
            for v in due:
                if config.get().youtube_auto_upload and v.platform == "youtube":
                    try:
                        await youtube.upload(v.id)
                        continue
                    except Exception as e:
                        log.warning("YouTube upload failed for %s: %s", v.id, e)
                if v.id not in notified:
                    notified.add(v.id)
                    broker.publish("due", {"id": v.id, "hook": v.hook, "platform": v.platform})
        except Exception:
            log.exception("scheduler")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    runner.start()
    task = asyncio.create_task(scheduler())
    log.info("AdForge hazır%s → http://%s:%s", " (DEMO / dry-run)" if boot.dry_run else "", boot.host, boot.port)
    yield
    task.cancel()
    await runner.stop()


app = FastAPI(title="AdForge", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])
for r in (system.router, products.router, campaigns.router, revenue.router, youtube.router, autopilot.router):
    app.include_router(r)
app.mount("/media", StaticFiles(directory=paths.media), name="media")

DIST = ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        f = (DIST / full_path).resolve()
        if full_path and f.is_file() and DIST.resolve() in f.parents:
            return FileResponse(f)
        return FileResponse(DIST / "index.html")


def run() -> None:
    import uvicorn
    uvicorn.run("app.main:app", host=boot.host, port=boot.port, reload=False)


if __name__ == "__main__":
    run()
