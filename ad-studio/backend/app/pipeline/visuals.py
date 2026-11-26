"""Scene media via ComfyUI: text-to-image per scene, optional image-to-video (Wan 2.2)."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

from ..config import config
from ..providers import comfy
from . import graphics
from .script import AdScript

IMG_W, IMG_H = 768, 1344  # 9:16-ish, multiple of 64 (Flux/SDXL friendly)
VID_W, VID_H, VID_FRAMES, VID_FPS = 704, 1280, 121, 24  # Wan 2.2 TI2V 5B native


async def generate(script: AdScript, out_dir: Path, style: str, use_i2v: bool, dry_run: bool,
                   on_progress: Callable[[float], Awaitable[None]]) -> list[Path]:
    cfg = config.get()
    n = len(script.scenes)
    results: list[Path] = []
    for i, sc in enumerate(script.scenes):
        base = (i / n)
        span = 1 / n

        async def prog(p: float, _b=base, _s=span, _w=(0.4 if use_i2v else 1.0), _o=0.0) -> None:
            await on_progress(_b + _s * (_o + p * _w))

        if dry_run:
            img = graphics.stub_scene(out_dir / f"scene_{i}.png", i, sc.on_screen_text or f"Sahne {i + 1}", sc.visual_prompt)
            await prog(1.0)
            results.append(img)
            continue

        prompt = ", ".join(x for x in (sc.visual_prompt, style, cfg.style_suffix) if x)
        graph = comfy.fill(comfy.load_workflow(cfg.image_workflow), {
            "prompt": prompt, "negative": cfg.negative_prompt, "seed": comfy.seed(), "width": IMG_W, "height": IMG_H,
            "steps": cfg.image_steps, "filename_prefix": f"adforge/scene_{i}",
        })
        img = (await comfy.run(graph, out_dir, f"scene_{i}", prog))[0]
        if use_i2v:
            uploaded = await comfy.upload_image(img)

            async def vprog(p: float, _b=base, _s=span) -> None:
                await on_progress(_b + _s * (0.4 + 0.6 * p))

            vgraph = comfy.fill(comfy.load_workflow(cfg.video_workflow), {
                "prompt": f"{sc.visual_prompt}, smooth cinematic camera motion, natural movement",
                "negative": cfg.negative_prompt + ", static, frozen, morphing, flicker",
                "seed": comfy.seed(), "image": uploaded, "width": VID_W, "height": VID_H,
                "length": VID_FRAMES, "fps": VID_FPS, "filename_prefix": f"adforge/clip_{i}",
            })
            clip = (await comfy.run(vgraph, out_dir, f"clip_{i}", vprog))[0]
            results.append(clip)
        else:
            results.append(img)
    return results
