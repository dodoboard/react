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
from . import graphics, product as product_mod, realism
from .script import PRODUCT_SHOTS, AdScript
from .timeline import Timeline

IMG_W, IMG_H = 768, 1344  # 9:16-ish, multiple of 64
VID_W, VID_H, VID_FPS, VID_MAX = 704, 1280, 24, 121  # Wan 2.2 TI2V 5B
S2V_W, S2V_H, S2V_FPS, S2V_MAX = 480, 832, 16, 161  # Wan 2.2 S2V 14B
AVATAR_FPS = {"wan22_s2v": (16, 161), "infinitetalk": (25, 201)}  # workflow → (fps, max frames per call)

Progress = Callable[[float], Awaitable[None]]


def frames_for(dur: float, fps: int, cap: int, floor: int = 33) -> int:
    n = int(dur * fps)
    n = 4 * ((n - 1) // 4) + 1  # Wan requires 4k+1
    return max(floor, min(cap, n))


def image_workflow() -> str:
    cfg = config.get()
    if cfg.image_workflow == "flux_realism" and cfg.realism_lora:
        return "flux_realism_lora"
    return cfg.image_workflow


async def _t2i(prompt: str, out_dir: Path, stem: str, prog: Progress, negative_extra: str = "",
               size: tuple[int, int] = (IMG_W, IMG_H), shot: str = "", domain: str = "ad") -> Path:
    cfg = config.get()
    if cfg.realism:
        prompt = realism.recipe(prompt, shot, domain, key=f"{out_dir.name}/{stem}")
        negative = realism.negative(", ".join(x for x in (cfg.negative_prompt, negative_extra) if x))
    else:
        negative = ", ".join(x for x in (cfg.negative_prompt, negative_extra) if x)
    graph = comfy.fill(comfy.load_workflow(image_workflow()), {
        "prompt": prompt, "negative": negative, "seed": comfy.seed(),
        "width": size[0], "height": size[1], "steps": cfg.image_steps, "filename_prefix": f"adforge/{stem}",
        "out_width": size[0] * 2, "out_height": size[1] * 2, "upscale_model": cfg.upscale_model,
        "lora": cfg.realism_lora, "lora_strength": cfg.realism_lora_strength})
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
        bg = await _t2i(bg_prompt, out_dir, f"bg_{i}", prog, "product, device, bottle, box, object on surface, hands",
                        shot="product_hero" if sc.shot == "product_hero" else "lifestyle")
    return product_mod.composite(bg, cut, target, sc.shot, i)


async def character_ref(avatar: Path, scene: str, framing: str, out: Path, dry: bool, prog: Progress,
                        size: tuple[int, int] = (832, 480)) -> Path:
    """Identity-locked still of the presenter in a new place/framing (Flux Kontext). Fallback: interview framing."""
    if dry or not config.get().identity_lock:
        await prog(1.0)
        return graphics.presenter_frame(avatar, out, (size[0] * 2, size[1] * 2))
    cfg = config.get()
    canvas = graphics.presenter_frame(avatar, out.with_name(out.stem + "_src.png"), (size[0] * 2, size[1] * 2))
    ref = await comfy.upload_image(canvas)
    prompt = (f"The same person, identical face, hairstyle and outfit, now {framing} {scene}. Documentary interview, "
              "looking at the camera, natural skin texture, realistic photograph, soft window light, shallow depth of field.")
    graph = comfy.fill(comfy.load_workflow(cfg.kontext_workflow), {
        "prompt": prompt, "image": ref, "seed": comfy.seed(), "width": size[0] * 2,
        "height": size[1] * 2, "steps": cfg.image_steps, "filename_prefix": f"adforge/{out.stem}"})
    res = (await comfy.run(graph, out.parent, out.stem, prog))[0]
    return res.rename(out) if res != out else res


async def _presenter(i: int, avatar: Path, span: tuple[float, float], voice: Path, out_dir: Path, dry: bool,
                     prog: Progress, size: tuple[int, int] = (S2V_W, S2V_H), prompt: str = "",
                     ref_frame: Path | None = None) -> Path:
    if dry:
        await prog(1.0)
        if size[0] > size[1]:
            return graphics.presenter_frame(avatar, out_dir / f"scene_{i}.png", (size[0] * 2, size[1] * 2))
        return graphics.cover_copy(avatar, out_dir / f"scene_{i}.png", (size[0] * 2, size[1] * 2))
    cfg = config.get()
    a, b = span
    seg_audio = out_dir / f"vo_{i}.wav"
    await run_ffmpeg(["-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", str(voice), "-ac", "1", "-ar", "16000", str(seg_audio)])
    ref = ref_frame or avatar
    if not ref_frame and size[0] > size[1]:  # landscape: give the model a 16:9 interview frame to animate
        ref = graphics.presenter_frame(avatar, out_dir / f"ref_presenter_{i}.png", (size[0] * 2, size[1] * 2))
    img = await comfy.upload_image(ref)
    aud = await comfy.upload_image(seg_audio)
    graph = comfy.fill(comfy.load_workflow(cfg.avatar_workflow), {
        "prompt": (prompt or "a person talking enthusiastically to the camera, smartphone selfie video, realistic")
        + ", " + realism.PRESENTER_BEHAVIOR,
        "negative": cfg.negative_prompt + ", static, frozen, distorted face, extra limbs",
        "image": img, "audio": aud, "seed": comfy.seed(), "width": size[0], "height": size[1],
        "length": frames_for(b - a, *_avatar_rate()), "fps": _avatar_rate()[0], "filename_prefix": f"adforge/avatar_{i}"})
    return (await comfy.run(graph, out_dir, f"clip_{i}", prog))[0]


def _avatar_rate() -> tuple[int, int]:
    return AVATAR_FPS.get(config.get().avatar_workflow, (S2V_FPS, S2V_MAX))


def video_workflow() -> str:
    cfg = config.get()
    if cfg.video_workflow == "wan22_i2v" and cfg.i2v_fast_lora:
        return "wan22_i2v_fast"
    return cfg.video_workflow


async def _i2v(img: Path, prompt: str, dur: float, i: int, out_dir: Path, prog: Progress,
               size: tuple[int, int] = (VID_W, VID_H), shot: str = "", domain: str = "ad") -> Path:
    cfg = config.get()
    uploaded = await comfy.upload_image(img)
    move = realism.motion(prompt, shot, domain)
    graph = comfy.fill(comfy.load_workflow(video_workflow()), {
        "fast_lora": cfg.i2v_fast_lora,
        "prompt": f"{prompt}, {move}, natural physically plausible motion, realistic",
        "negative": cfg.negative_prompt + ", static, frozen, morphing, flicker",
        "seed": comfy.seed(), "image": uploaded, "width": size[0], "height": size[1],
        "length": frames_for(dur, VID_FPS, VID_MAX), "fps": VID_FPS, "filename_prefix": f"adforge/clip_{i}"})
    return (await comfy.run(graph, out_dir, f"clip_{i}", prog))[0]


async def generate(script: AdScript, out_dir: Path, campaign: Campaign, cutouts: list[Path | None], tl: Timeline,
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
        cutout = cutouts[min(sc.product_ref, len(cutouts) - 1)] if cutouts else None
        if sc.shot in PRODUCT_SHOTS and cutout and cfg.product_mode != "off":
            img = await _product_shot(sc, i, campaign.visual_style, cutout, out_dir, dry_run, prog_at(0, w_img))
        elif dry_run:
            img = graphics.stub_scene(out_dir / f"scene_{i}.png", i, sc.on_screen_text or f"Sahne {i + 1}", sc.visual_prompt)
            await prog_at(0, 1)(1.0)
        else:
            suffix = "" if cfg.realism else cfg.style_suffix  # realism recipes replace the generic style suffix
            prompt = ", ".join(x for x in (sc.visual_prompt, campaign.visual_style, suffix) if x)
            img = await _t2i(prompt, out_dir, f"scene_{i}", prog_at(0, w_img), shot=sc.shot)
        if want_i2v:
            results.append(await _i2v(img, sc.visual_prompt, durs[i], i, out_dir, prog_at(w_img, 1 - w_img), shot=sc.shot))
        else:
            results.append(img)
    return results
