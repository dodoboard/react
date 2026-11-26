"""Scene media via ComfyUI. Per shot type:
- product shots → real product (pixel-exact composite on generated background, or Flux Kontext reference)
- presenter     → talking avatar (Wan 2.2 S2V) driven by that scene's voice segment
- lifestyle     → text-to-image
Optional Wan 2.2 image-to-video on the hook scene or all scenes.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

from ..config import config, paths
from ..media import run_ffmpeg
from ..models import Campaign
from ..providers import comfy
from . import graphics, product as product_mod
from .script import PRODUCT_SHOTS, AdScript
from .timeline import Timeline

IMG_W, IMG_H = 768, 1344  # 9:16-ish, multiple of 64
VID_W, VID_H, VID_FPS, VID_MAX = 704, 1280, 24, 121  # Wan 2.2 TI2V 5B
S2V_W, S2V_H, S2V_FPS, S2V_MAX = 480, 832, 16, 161  # Wan 2.2 S2V 14B

Progress = Callable[[float], Awaitable[None]]


def frames_for(dur: float, fps: int, cap: int, floor: int = 33) -> int:
    n = int(dur * fps)
    n = 4 * ((n - 1) // 4) + 1  # Wan requires 4k+1
    return max(floor, min(cap, n))


async def _t2i(prompt: str, out_dir: Path, stem: str, prog: Progress, negative_extra: str = "") -> Path:
    cfg = config.get()
    graph = comfy.fill(comfy.load_workflow(cfg.image_workflow), {
        "prompt": prompt, "negative": ", ".join(x for x in (cfg.negative_prompt, negative_extra) if x), "seed": comfy.seed(),
        "width": IMG_W, "height": IMG_H, "steps": cfg.image_steps, "filename_prefix": f"adforge/{stem}"})
    return (await comfy.run(graph, out_dir, stem, prog))[0]


async def _product_shot(sc, i: int, style: str, cut: Path, out_dir: Path, dry: bool, prog: Progress) -> Path:
    cfg = config.get()
    target = out_dir / f"scene_{i}.png"
    if cfg.product_mode == "kontext" and not dry:
        canvas = product_mod.kontext_canvas(cut, out_dir / f"ref_{i}.png", (IMG_W, IMG_H))
        ref = await comfy.upload_image(canvas)
        prompt = (f"Place this exact product into a new vertical scene: {sc.visual_prompt}. {style}. "
                  "Keep the product's shape, colors, logo and printed text exactly identical. Photorealistic advertising photo.")
        graph = comfy.fill(comfy.load_workflow(cfg.kontext_workflow), {
            "prompt": prompt, "image": ref, "seed": comfy.seed(), "width": IMG_W, "height": IMG_H,
            "steps": cfg.image_steps, "filename_prefix": f"adforge/scene_{i}"})
        return (await comfy.run(graph, out_dir, f"scene_{i}", prog))[0]
    bg_prompt = (f"{sc.visual_prompt}, {style}, {cfg.style_suffix}, empty clean surface in the lower center foreground "
                 "for product placement, nothing on the surface, negative space")
    if dry:
        bg = graphics.stub_scene(out_dir / f"bg_{i}.png", i, sc.on_screen_text or "", "")
        await prog(1.0)
    else:
        bg = await _t2i(bg_prompt, out_dir, f"bg_{i}", prog, "product, device, bottle, box, object on surface, hands")
    return product_mod.composite(bg, cut, target, sc.shot, i)


async def _presenter(i: int, avatar: Path, span: tuple[float, float], voice: Path, out_dir: Path, dry: bool,
                     prog: Progress) -> Path:
    if dry:
        await prog(1.0)
        return graphics.cover_copy(avatar, out_dir / f"scene_{i}.png")
    cfg = config.get()
    a, b = span
    seg_audio = out_dir / f"vo_{i}.wav"
    await run_ffmpeg(["-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", str(voice), "-ac", "1", "-ar", "16000", str(seg_audio)])
    img = await comfy.upload_image(avatar)
    aud = await comfy.upload_image(seg_audio)
    graph = comfy.fill(comfy.load_workflow(cfg.avatar_workflow), {
        "prompt": "a person talking enthusiastically to the camera, natural head movement, smartphone selfie video, realistic",
        "negative": cfg.negative_prompt + ", static, frozen, distorted face, extra limbs",
        "image": img, "audio": aud, "seed": comfy.seed(), "width": S2V_W, "height": S2V_H,
        "length": frames_for(b - a, S2V_FPS, S2V_MAX), "fps": S2V_FPS, "filename_prefix": f"adforge/avatar_{i}"})
    return (await comfy.run(graph, out_dir, f"clip_{i}", prog))[0]


async def _i2v(img: Path, prompt: str, dur: float, i: int, out_dir: Path, prog: Progress) -> Path:
    cfg = config.get()
    uploaded = await comfy.upload_image(img)
    graph = comfy.fill(comfy.load_workflow(cfg.video_workflow), {
        "prompt": f"{prompt}, smooth cinematic camera motion, natural movement",
        "negative": cfg.negative_prompt + ", static, frozen, morphing, flicker",
        "seed": comfy.seed(), "image": uploaded, "width": VID_W, "height": VID_H,
        "length": frames_for(dur, VID_FPS, VID_MAX), "fps": VID_FPS, "filename_prefix": f"adforge/clip_{i}"})
    return (await comfy.run(graph, out_dir, f"clip_{i}", prog))[0]


async def generate(script: AdScript, out_dir: Path, campaign: Campaign, cutout: Path | None, tl: Timeline,
                   voice: Path, dry_run: bool, on_progress: Progress) -> list[Path]:
    cfg = config.get()
    n = len(script.scenes)
    mode = campaign.i2v_mode if campaign.i2v_mode != "off" else ("all" if campaign.use_i2v else cfg.i2v_mode)
    avatar = paths.avatars / campaign.avatar if campaign.avatar else None
    durs = tl.scene_durations
    results: list[Path] = []
    for i, sc in enumerate(script.scenes):
        want_i2v = not dry_run and (mode == "all" or (mode == "hook" and i == 0)) and sc.shot != "presenter"
        w_img = 0.35 if want_i2v else 1.0

        def prog_at(off: float, span: float, _i=i):
            async def p(f: float) -> None:
                await on_progress((_i + off + span * f) / n)
            return p

        if sc.shot == "presenter" and avatar and avatar.exists():
            res = await _presenter(i, avatar, tl.scene_span(i), voice, out_dir, dry_run, prog_at(0, 1))
            results.append(res)
            continue
        if sc.shot in PRODUCT_SHOTS and cutout and cfg.product_mode != "off":
            img = await _product_shot(sc, i, campaign.visual_style, cutout, out_dir, dry_run, prog_at(0, w_img))
        elif dry_run:
            img = graphics.stub_scene(out_dir / f"scene_{i}.png", i, sc.on_screen_text or f"Sahne {i + 1}", sc.visual_prompt)
            await prog_at(0, 1)(1.0)
        else:
            prompt = ", ".join(x for x in (sc.visual_prompt, campaign.visual_style, cfg.style_suffix) if x)
            img = await _t2i(prompt, out_dir, f"scene_{i}", prog_at(0, w_img))
        if want_i2v:
            results.append(await _i2v(img, sc.visual_prompt, durs[i], i, out_dir, prog_at(w_img, 1 - w_img)))
        else:
            results.append(img)
    return results
