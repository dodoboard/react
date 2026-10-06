"""`python -m studio` serves the app; `python -m studio doctor` runs a tiny end-to-end FLUX.2 render."""

from __future__ import annotations

import asyncio
import sys
import time

import uvicorn

from .api import create_app
from .comfy import ComfyClient
from .flux2 import PROFILES, build_graph
from .settings import Settings


async def doctor(settings: Settings) -> int:
    profile = PROFILES[settings.profile]
    comfy = ComfyClient(settings.comfy_url, timeout=10)
    try:
        stats = await comfy.system_stats()
        device = (stats.get("devices") or [{}])[0]
        print(f"[ok] ComfyUI {stats.get('system', {}).get('comfyui_version', '?')} at {settings.comfy_url}")
        print(f"  GPU: {device.get('name', '?')}, VRAM {device.get('vram_total', 0) / 2**30:.1f} GB")
        ok = True
        for folder, name in profile.required.items():
            present = name in await comfy.models(folder)
            ok &= present
            print(f"{'[ok]' if present else '[missing]'} models/{folder}/{name}")
        if not ok:
            print("Download them: python scripts/download_models.py --comfy <ComfyUI dir>")
            return 1
        t = time.perf_counter()
        graph = build_graph(profile, prompt="A photorealistic portrait of a smiling woman, studio light",
                            width=512, height=512, seed=1)
        images = await comfy.run(graph, lambda p: print(f"\r  rendering {p:4.0%}", end=""))
        print(f"\n[ok] {profile.label}: {len(images)} image(s) in {time.perf_counter() - t:.1f}s (includes model load)")
        return 0
    except Exception as e:
        print(f"[error] {type(e).__name__}: {e}")
        return 1
    finally:
        await comfy.aclose()


def main() -> None:
    settings = Settings()
    if sys.argv[1:] == ["doctor"]:
        raise SystemExit(asyncio.run(doctor(settings)))
    print(f"Influencer Studio: http://{settings.host}:{settings.port}  (ComfyUI: {settings.comfy_url}, model: {settings.profile})")
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    main()
