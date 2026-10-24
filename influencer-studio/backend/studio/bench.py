"""`python -m studio bench image|motion|talk [runs]`: time a small fixed render.

The first run includes loading the models; later runs show the warm speed. Compare ComfyUI
launch flags (--fast, --use-sage-attention, --reserve-vram…) by restarting ComfyUI between benches.
"""

from __future__ import annotations

import io
import math
import struct
import time
import wave

from PIL import Image, ImageDraw

from .comfy import ComfyClient
from .flux2 import PROFILES, build_graph
from .settings import Settings
from .video import MODE_FILES, RESOLUTIONS, TALK_FPS, MotionParams, TalkParams, build_motion_graph, build_talk_graph

MODES = ("image", "motion", "talk")
TALK_SECONDS = 2.0  # one InfiniteTalk window


def _portrait(width: int, height: int) -> bytes:
    img = Image.new("RGB", (width, height), (196, 180, 170))
    d = ImageDraw.Draw(img)
    cx = width // 2
    d.ellipse([cx - width // 6, height // 6, cx + width // 6, height // 6 + width // 2.6], fill=(228, 196, 170))
    d.rectangle([cx - width // 4, height // 2, cx + width // 4, height], fill=(40, 60, 110))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _speech_wav(seconds: float, rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        # a syllable-like 4 Hz envelope over a 180 Hz tone, so the audio encoder sees "speech"
        w.writeframes(b"".join(
            struct.pack("<h", int(9000 * abs(math.sin(math.pi * 4 * i / rate)) * math.sin(2 * math.pi * 180 * i / rate)))
            for i in range(int(seconds * rate))
        ))
    return buf.getvalue()


async def _graph(comfy: ComfyClient, mode: str, settings: Settings, seed: int) -> tuple[dict, list[str], str]:
    """(graph, progress nodes, description). A new seed per run defeats ComfyUI's output cache."""
    if mode == "image":
        profile = PROFILES[settings.profile]
        graph = build_graph(profile, prompt="A photorealistic portrait of a smiling woman, studio light",
                            width=512, height=512, seed=seed)
        return graph, [], f"{profile.label}, 512×512"
    width, height = RESOLUTIONS["480p"]["portrait"]
    image = await comfy.upload(_portrait(width, height), "studio_bench.png")
    if mode == "motion":
        g = build_motion_graph(MotionParams(image=image, prompt="She waves at the camera and smiles.",
                                            width=width, height=height, seed=seed))
        return g, g.samplers(), f"Wan 2.2 I2V, {width}×{height}, 81 frames"
    audio = await comfy.upload(_speech_wav(TALK_SECONDS), "studio_bench.wav")
    frames = math.ceil(TALK_SECONDS * TALK_FPS)
    g = build_talk_graph(TalkParams(image=image, audio=audio, frames=frames, width=width, height=height,
                                    prompt="A woman talking to the camera.", seed=seed))
    return g, g.samplers(), f"InfiniteTalk, {width}×{height}, {frames} frames"


async def bench(settings: Settings, mode: str, runs: int = 2) -> int:
    if mode not in MODES:
        print(f"usage: python -m studio bench {'|'.join(MODES)} [runs]")
        return 2
    comfy = ComfyClient(settings.comfy_url, timeout=60)
    try:
        stats = await comfy.system_stats()
        device = (stats.get("devices") or [{}])[0]
        flags = " ".join(stats.get("system", {}).get("argv", [])[1:]) or "(none)"
        print(f"ComfyUI {stats.get('system', {}).get('comfyui_version', '?')} · {device.get('name', '?')}")
        print(f"  launch flags: {flags}")
        required = PROFILES[settings.profile].required.items() if mode == "image" else \
            [(m.folder, m.name) for m in MODE_FILES[mode]]
        missing = [f"models/{folder}/{name}" for folder, name in required if name not in await comfy.models(folder)]
        if missing:
            print("[missing] " + ", ".join(missing))
            return 1
        for run in range(1, runs + 1):
            graph, nodes, label = await _graph(comfy, mode, settings, seed=run)
            if run == 1:
                print(f"  {label}")
            start = time.perf_counter()
            first: list[float] = []

            def progress(p: float) -> None:
                if p > 0 and not first:
                    first.append(time.perf_counter())
                print(f"\r  run {run}: {p:4.0%}", end="", flush=True)

            await comfy.run(graph, progress, progress_nodes=nodes)
            total = time.perf_counter() - start
            sampling = total - (first[0] - start) if first else total
            note = " (includes model load)" if run == 1 else ""
            print(f"\r  run {run}: {total:6.1f} s total, {sampling:6.1f} s sampling+decode{note}")
        return 0
    except Exception as e:
        print(f"\n[error] {type(e).__name__}: {e}")
        return 1
    finally:
        await comfy.aclose()
