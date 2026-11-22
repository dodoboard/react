"""`python -m studio bench image|motion|talk|hd [runs]`: time a small fixed render.
`python -m studio doctor --all`: models, ComfyUI nodes and one small render for every mode.

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
from .compat import missing_nodes
from .flux2 import PROFILES, build_graph
from .hd import build_image_upscale_graph
from .settings import Settings
from .video import MODE_FILES, RESOLUTIONS, TALK_FPS, MotionParams, TalkParams, build_motion_graph, build_talk_graph

MODES = ("image", "motion", "talk", "hd")
DOCTOR_MODES = ("image", "dance", "music", "motion", "talk", "smooth", "hd")
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
    if mode == "hd":
        name = await comfy.upload(_portrait(256, 384), f"studio_bench_hd_{seed}.png")  # new file: no cache hit
        return build_image_upscale_graph(name), [], "Real-ESRGAN x4plus, 256×384 → 512×768"
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


def _required_files(mode: str, settings: Settings) -> list[tuple[str, str]]:
    if mode == "image":
        return list(PROFILES[settings.profile].required.items())
    return [(f.folder, f.name) for f in MODE_FILES[mode]]


async def doctor_all(settings: Settings) -> int:
    """One line per mode: missing model files, missing ComfyUI nodes, and a timed small render."""
    comfy = ComfyClient(settings.comfy_url, timeout=60)
    try:
        stats = await comfy.system_stats()
        device = (stats.get("devices") or [{}])[0]
        print(f"ComfyUI {stats.get('system', {}).get('comfyui_version', '?')} · {device.get('name', '?')}, "
              f"VRAM {device.get('vram_total', 0) / 2**30:.1f} GB")
        nodes = await missing_nodes(comfy, PROFILES[settings.profile])
        listings: dict[str, set[str]] = {}
        failures = 0
        for mode in DOCTOR_MODES:
            files = _required_files(mode, settings)
            for folder, _ in files:
                if folder not in listings:
                    listings[folder] = {n.replace("\\", "/") for n in await comfy.models(folder)}
            missing = [f"models/{folder}/{name}" for folder, name in files if name not in listings[folder]]
            problems = missing + [f"node {n} (update ComfyUI)" for n in nodes.get(mode, [])]
            if problems:
                print(f"[✗] {mode:7} " + "; ".join(problems))
                continue
            if mode not in MODES:
                print(f"[✓] {mode:7} models and nodes present (no test render for this mode)")
                continue
            try:
                graph, progress, label = await _graph(comfy, mode, settings, seed=1)
                start = time.perf_counter()
                await comfy.run(graph, progress_nodes=progress)
                print(f"[✓] {mode:7} {label}: {time.perf_counter() - start:.1f} s (includes model load)")
            except Exception as e:
                failures += 1
                print(f"[✗] {mode:7} render failed: {type(e).__name__}: {e}")
        print("Download missing models: python scripts/download_models.py --comfy <ComfyUI> --video <mode>")
        return 1 if failures else 0
    except Exception as e:
        print(f"[error] ComfyUI not reachable at {settings.comfy_url}: {type(e).__name__}: {e}")
        return 1
    finally:
        await comfy.aclose()
