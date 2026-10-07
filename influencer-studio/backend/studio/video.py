"""Video model files and ComfyUI (API format) graphs for the Motion studio.

Three modes, each mirroring an official ComfyUI template node-for-node:

- dance:  Wan-Animate-2 Distilled — the character performs the choreography and camera of a
          driving clip. Clips longer than one 81-frame window are chained via continue_motion.
- music:  Wan-Dancer-14B — music-driven dance from a single image: a global pass plans
          keyframes from the audio, a local pass renders 5-second 30 fps segments.
- motion: Wan 2.2 I2V A14B + 4-step lightx2v LoRAs — prompt-driven 5-second moves.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

_HF = "https://huggingface.co"


@dataclass(frozen=True)
class ModelFile:
    folder: str  # ComfyUI models/ subfolder
    name: str
    url: str


UMT5 = ModelFile("text_encoders", "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
                 f"{_HF}/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors")
CLIP_VISION_H = ModelFile("clip_vision", "clip_vision_h.safetensors",
                          f"{_HF}/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/clip_vision/clip_vision_h.safetensors")
WAN_VAE = ModelFile("vae", "wan_2.1_vae.safetensors",
                    f"{_HF}/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors")
ANIMATE2 = ModelFile("diffusion_models", "wan_animate_2_distill_int8_convrot.safetensors",
                     f"{_HF}/Comfy-Org/Wan-Animate-2/resolve/main/diffusion_models/wan_animate_2_distill_int8_convrot.safetensors")
DANCER_GLOBAL = ModelFile("diffusion_models", "wan2.2_dancer_14b_global_fp8_scaled.safetensors",
                          f"{_HF}/Comfy-Org/Wan-Dancer/resolve/main/diffusion_models/wan2.2_dancer_14b_global_fp8_scaled.safetensors")
DANCER_LOCAL = ModelFile("diffusion_models", "wan2.2_dancer_14b_local_fp8_scaled.safetensors",
                         f"{_HF}/Comfy-Org/Wan-Dancer/resolve/main/diffusion_models/wan2.2_dancer_14b_local_fp8_scaled.safetensors")
LIGHTX2V_I2V = ModelFile("loras", "lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors",
                         f"{_HF}/Kijai/WanVideo_comfy/resolve/main/Lightx2v/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors")
_WAN22 = f"{_HF}/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files"
WAN22_HIGH = ModelFile("diffusion_models", "wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors",
                       f"{_WAN22}/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors")
WAN22_LOW = ModelFile("diffusion_models", "wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors",
                      f"{_WAN22}/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors")
WAN22_LORA_HIGH = ModelFile("loras", "wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors",
                            f"{_WAN22}/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors")
WAN22_LORA_LOW = ModelFile("loras", "wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors",
                           f"{_WAN22}/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors")
FILM = ModelFile("frame_interpolation", "film_net_fp16.safetensors",
                 f"{_HF}/Comfy-Org/frame_interpolation/resolve/main/frame_interpolation/film_net_fp16.safetensors")

MODE_FILES: dict[str, tuple[ModelFile, ...]] = {
    "dance": (ANIMATE2, UMT5, CLIP_VISION_H, WAN_VAE),
    "music": (DANCER_GLOBAL, DANCER_LOCAL, LIGHTX2V_I2V, UMT5, CLIP_VISION_H, WAN_VAE),
    "motion": (WAN22_HIGH, WAN22_LOW, WAN22_LORA_HIGH, WAN22_LORA_LOW, UMT5, WAN_VAE),
    "smooth": (FILM,),
}

# Wan's standard negative prompt (the models were trained with it, in Chinese).
WAN_NEGATIVE = (
    "色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，"
    "多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走"
)

WAN_FPS = 16
SEGMENT_FRAMES = 81  # one Wan-Animate-2 window (5 s at 16 fps)
DANCER_FRAMES = 149  # Wan-Dancer keyframe/segment length
DANCER_FPS = 30
DANCER_SEGMENT_SECONDS = 5

# All sizes are multiples of 16, as the Wan latent nodes require.
RESOLUTIONS: dict[str, dict[str, tuple[int, int]]] = {
    "480p": {"portrait": (480, 832), "landscape": (832, 480), "square": (624, 624)},
    "720p": {"portrait": (720, 1280), "landscape": (1280, 720), "square": (960, 960)},
}

DANCE_STYLES: dict[str, tuple[str, str]] = {  # id → (label, Wan-Dancer prompt token)
    "kpop": ("K-Pop", "韩舞"),
    "street": ("Street", "街舞"),
    "latin": ("Latin", "拉丁舞"),
    "tap": ("Tap", "踢踏舞"),
    "classical": ("Chinese classical", "古典舞"),
}
DANCE_ENERGY: dict[str, tuple[str, str]] = {
    "low": ("Low", "低"),
    "medium": ("Medium", "中等"),
    "high": ("High", "高"),
    "max": ("Max", "最大"),
}


@dataclass(frozen=True)
class MotionPreset:
    id: str
    label: str
    action: str  # {who} = "the woman"/"the man"/"the person"; {their}/{them} = matching pronouns


MOTION_PRESETS: tuple[MotionPreset, ...] = (
    MotionPreset("groove", "Dance groove", "{who} dances energetically to an upbeat song, bouncing on the beat with arms and hips moving"),
    MotionPreset("hair_flip", "Hair flip", "{who} flips {their} hair over the shoulder and smiles at the camera"),
    MotionPreset("spin", "Spin", "{who} does a slow full 360-degree spin in place, clothes and hair swaying"),
    MotionPreset("runway", "Runway walk", "{who} walks confidently toward the camera like on a fashion runway"),
    MotionPreset("wave", "Wave hello", "{who} waves at the camera with a bright, friendly smile"),
    MotionPreset("jump", "Jump for joy", "{who} jumps up joyfully with both arms raised, then lands and laughs"),
    MotionPreset("kiss", "Blow a kiss", "{who} blows a kiss toward the camera and winks"),
    MotionPreset("look_back", "Look back", "{who} turns {their} head from looking away to glance back at the camera over the shoulder"),
    MotionPreset("pose", "Pose change", "{who} strikes a series of playful poses for the camera, changing pose every second"),
    MotionPreset("sway", "Gentle sway", "{who} sways gently from side to side with natural breathing and subtle body movement"),
    MotionPreset("orbit", "Camera orbit", "{who} stands still and smiles while the camera slowly orbits around {them}"),
    MotionPreset("wind", "Wind in hair", "{who} gazes into the distance while a soft breeze blows through {their} hair and clothes"),
)
MOTION_PRESET_BY_ID = {p.id: p for p in MOTION_PRESETS}


class Graph(dict):
    """ComfyUI API-format prompt under construction."""

    def add(self, class_type: str, **inputs) -> list:
        node_id = str(len(self) + 1)
        self[node_id] = {"class_type": class_type, "inputs": inputs}
        return [node_id, 0]

    def samplers(self) -> list[str]:
        """Sampling node ids in execution order, for overall progress reporting."""
        kinds = {"SamplerCustom", "SamplerCustomAdvanced", "KSamplerAdvanced"}
        return [i for i, n in self.items() if n["class_type"] in kinds]


def out(link: list, index: int) -> list:
    return [link[0], index]


def _loaders(g: Graph) -> tuple[list, list]:
    clip = g.add("CLIPLoader", clip_name=UMT5.name, type="wan", device="default")
    vae = g.add("VAELoader", vae_name=WAN_VAE.name)
    return clip, vae


def _image(g: Graph, filename: str, width: int, height: int) -> list:
    return g.add("ImageScale", image=g.add("LoadImage", image=filename), upscale_method="lanczos",
                 width=width, height=height, crop="center")


def _finish(g: Graph, images: list, fps: float, audio: list | None, smooth: bool) -> None:
    if smooth:  # FILM frame interpolation doubles the frame rate
        model = g.add("FrameInterpolationModelLoader", model_name=FILM.name)
        images = g.add("FrameInterpolate", interp_model=model, images=images, multiplier=2)
        fps *= 2
    video = g.add("CreateVideo", images=images, fps=fps, **({"audio": audio} if audio else {}))
    g.add("SaveVideo", video=video, filename_prefix="influencer-studio/motion", format="mp4")


# ── dance: Wan-Animate-2 motion transfer ────────────────────────────────────
def dance_segments(frames: int) -> tuple[int, int]:
    """(window length, window count) covering `frames`; windows overlap by one frame."""
    if frames <= SEGMENT_FRAMES:
        return 4 * math.ceil((frames - 1) / 4) + 1, 1
    return SEGMENT_FRAMES, math.ceil((frames - 1) / (SEGMENT_FRAMES - 1))


@dataclass(frozen=True)
class DanceParams:
    reference: str  # ComfyUI input filenames
    driver: str  # pre-processed: WAN_FPS, width x height, silent
    frames: int
    width: int
    height: int
    prompt: str
    seed: int
    audio: str | None = None
    pose_strength: float = 1.0
    smooth: bool = False
    pose_cache: str | None = "int4"  # WanAnimate2Cache dtype in system RAM; None disables


def build_dance_graph(p: DanceParams) -> Graph:
    g = Graph()
    model = g.add("UNETLoader", unet_name=ANIMATE2.name, weight_dtype="default")
    if p.pose_cache:  # caches the pose branch once per window: ~2x faster, costs system RAM
        model = g.add("WanAnimate2Cache", model=model, device="cpu", dtype=p.pose_cache)
    sampling = g.add("ModelSamplingSD3", model=model, shift=5)
    clip, vae = _loaders(g)
    positive = g.add("CLIPTextEncode", text=p.prompt, clip=clip)
    negative = g.add("CLIPTextEncode", text=WAN_NEGATIVE, clip=clip)
    pose_text = g.add("CLIPTextEncode", text="a person dancing, full-body choreography, natural motion", clip=clip)
    clip_vision = g.add("CLIPVisionLoader", clip_name=CLIP_VISION_H.name)
    reference = _image(g, p.reference, p.width, p.height)
    reference_cv = g.add("CLIPVisionEncode", clip_vision=clip_vision, image=reference, crop="none")
    driver = g.add("GetVideoComponents", video=g.add("LoadVideo", file=p.driver))
    first_pose = g.add("ImageFromBatch", image=driver, batch_index=0, length=1)
    pose_cv = g.add("CLIPVisionEncode", clip_vision=clip_vision, image=first_pose, crop="none")
    sampler = g.add("KSamplerSelect", sampler_name="lcm")
    sigmas = g.add("BasicScheduler", model=model, scheduler="simple", steps=10, denoise=1.0)

    length, windows = dance_segments(p.frames)
    video, previous = None, None
    for _ in range(windows):
        animate = g.add(
            "WanAnimate2ToVideo",
            positive=positive, negative=negative, vae=vae, width=p.width, height=p.height, length=length,
            batch_size=1, video_frame_offset=out(previous["animate"], 5) if previous else 0,
            pose_strength=p.pose_strength, pose_start_percent=0.0, pose_end_percent=1.0,
            reference_image_strength=1.0, reference_image=reference, pose_video=driver,
            clip_vision_output=reference_cv, positive_pose=pose_text, clip_vision_output_pose=pose_cv,
            **({"continue_motion": previous["images"]} if previous else {}),
        )
        latent = g.add("SamplerCustom", model=sampling, add_noise=True, noise_seed=p.seed, cfg=1.0,
                       positive=out(animate, 0), negative=out(animate, 1), sampler=sampler,
                       sigmas=sigmas, latent_image=out(animate, 2))
        latent = g.add("TrimVideoLatent", samples=latent, trim_amount=out(animate, 3))
        images = g.add("VAEDecode", samples=latent, vae=vae)
        # Drop the frame(s) that overlap the previous window (0 for the first window).
        fresh = g.add("ImageFromBatch", image=images, batch_index=out(animate, 4), length=4096)
        video = fresh if video is None else g.add("ImageBatch", image1=video, image2=fresh)
        previous = {"animate": animate, "images": images}

    video = g.add("ImageFromBatch", image=video, batch_index=0, length=p.frames)
    audio = g.add("LoadAudio", audio=p.audio) if p.audio else None
    _finish(g, video, WAN_FPS, audio, p.smooth)
    return g


# ── music: Wan-Dancer music-to-dance ────────────────────────────────────────
@dataclass(frozen=True)
class MusicDanceParams:
    image: str
    audio: str  # pre-trimmed to `seconds`
    seconds: int  # multiple of DANCER_SEGMENT_SECONDS
    style: str
    energy: str
    width: int
    height: int
    seed: int
    fast: bool = True  # lightx2v LoRA on the global pass: 6 steps instead of 25
    smooth: bool = False


def build_music_graph(p: MusicDanceParams) -> Graph:
    if p.seconds % DANCER_SEGMENT_SECONDS or p.seconds <= 0:
        raise ValueError(f"seconds must be a positive multiple of {DANCER_SEGMENT_SECONDS}")
    g = Graph()
    clip, vae = _loaders(g)
    clip_vision = g.add("CLIPVisionLoader", clip_name=CLIP_VISION_H.name)
    start = _image(g, p.image, p.width, p.height)
    start_cv = g.add("CLIPVisionEncode", clip_vision=clip_vision, image=start, crop="none")
    audio = g.add("LoadAudio", audio=p.audio)
    style_text = f"一个人正在跳舞，舞蹈种类是{DANCE_STYLES[p.style][1]}"  # "a person is dancing, the style is …"

    # Global pass: plan DANCER_FRAMES keyframes over the whole song.
    global_audio = g.add("WanDancerEncodeAudio", audio=audio, video_frames=DANCER_FRAMES, audio_inject_scale=1.0)
    global_prompt = g.add("StringConcatenate", string_a=style_text, string_b=out(global_audio, 1), delimiter=" ")
    model = g.add("UNETLoader", unet_name=DANCER_GLOBAL.name, weight_dtype="default")
    if p.fast:
        model = g.add("LoraLoaderModelOnly", model=model, lora_name=LIGHTX2V_I2V.name, strength_model=3.0)
    model = g.add("ModelSamplingSD3", model=model, shift=5)
    model = g.add("SkipLayerGuidanceDiTSimple", model=model, double_layers="9", single_layers="",
                  start_percent=0.0, end_percent=1.0)
    planned = g.add(
        "WanDancerVideo",
        positive=g.add("CLIPTextEncode", text=global_prompt, clip=clip),
        negative=g.add("CLIPTextEncode", text=WAN_NEGATIVE, clip=clip),
        vae=vae, width=p.width, height=p.height, length=DANCER_FRAMES,
        clip_vision_output=start_cv, clip_vision_output_ref=start_cv, start_image=start,
        audio_encoder_output=global_audio,
    )
    keyframes = g.add(
        "SamplerCustomAdvanced",
        noise=g.add("RandomNoise", noise_seed=p.seed),
        guider=g.add("CFGGuider", model=model, positive=out(planned, 0), negative=out(planned, 1),
                     cfg=1.0 if p.fast else 5.0),
        sampler=g.add("KSamplerSelect", sampler_name="euler"),
        sigmas=g.add("BasicScheduler", model=model, scheduler="simple", steps=6 if p.fast else 25, denoise=1.0),
        latent_image=out(planned, 2),
    )
    keyframes = g.add("VAEDecode", samples=g.add("LatentCutToBatch", samples=keyframes, dim="t", slice_size=1), vae=vae)

    # Local pass: one 5-second, 30 fps segment per list item, guided by the keyframes.
    segments = g.add("WanDancerPadKeyframesList", images=keyframes, segment_length=DANCER_FRAMES,
                     num_segments=p.seconds // DANCER_SEGMENT_SECONDS, audio=audio)
    local_audio = g.add("WanDancerEncodeAudio", audio=out(segments, 2), video_frames=DANCER_FRAMES, audio_inject_scale=1.0)
    local_text = g.add("CLIPTextEncode", clip=clip,
                       text=f"{style_text},图像清晰程度高,人物动作幅度{DANCE_ENERGY[p.energy][1]}")  # "sharp image, motion amplitude …"
    local_model = g.add("UNETLoader", unet_name=DANCER_LOCAL.name, weight_dtype="default")
    local_model = g.add("LoraLoaderModelOnly", model=local_model, lora_name=LIGHTX2V_I2V.name, strength_model=1.03)
    first_keyframe = g.add("ImageFromBatch", image=segments, batch_index=0, length=1)
    local = g.add(
        "WanDancerVideo",
        positive=local_text, negative=g.add("ConditioningZeroOut", conditioning=local_text), vae=vae,
        width=p.width, height=p.height, length=DANCER_FRAMES,
        clip_vision_output=g.add("CLIPVisionEncode", clip_vision=clip_vision, image=first_keyframe, crop="none"),
        clip_vision_output_ref=start_cv, start_image=segments, mask=out(segments, 1),
        audio_encoder_output=local_audio,
    )
    latent = g.add("SamplerCustom", model=local_model, add_noise=True, noise_seed=p.seed, cfg=1.0,
                   positive=out(local, 0), negative=out(local, 1),
                   sampler=g.add("KSamplerSelect", sampler_name="euler"),
                   sigmas=g.add("BasicScheduler", model=local_model, scheduler="simple", steps=6, denoise=1.0),
                   latent_image=out(local, 2))
    frames = g.add("RebatchImages", images=g.add("VAEDecode", samples=latent, vae=vae), batch_size=4096)
    _finish(g, frames, DANCER_FPS, audio, p.smooth)
    return g


# ── motion: Wan 2.2 image-to-video ──────────────────────────────────────────
@dataclass(frozen=True)
class MotionParams:
    image: str
    prompt: str
    width: int
    height: int
    seed: int
    smooth: bool = False


def build_motion_graph(p: MotionParams) -> Graph:
    g = Graph()

    def expert(unet: ModelFile, lora: ModelFile) -> list:
        model = g.add("UNETLoader", unet_name=unet.name, weight_dtype="default")
        model = g.add("LoraLoaderModelOnly", model=model, lora_name=lora.name, strength_model=1.0)
        return g.add("ModelSamplingSD3", model=model, shift=5)

    high, low = expert(WAN22_HIGH, WAN22_LORA_HIGH), expert(WAN22_LOW, WAN22_LORA_LOW)
    clip, vae = _loaders(g)
    cond = g.add(
        "WanImageToVideo",
        positive=g.add("CLIPTextEncode", text=p.prompt, clip=clip),
        negative=g.add("CLIPTextEncode", text=WAN_NEGATIVE, clip=clip),
        vae=vae, width=p.width, height=p.height, length=SEGMENT_FRAMES, batch_size=1,
        start_image=_image(g, p.image, p.width, p.height),
    )
    common = {"cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "steps": 4,
              "positive": out(cond, 0), "negative": out(cond, 1)}
    latent = g.add("KSamplerAdvanced", model=high, add_noise="enable", noise_seed=p.seed, latent_image=out(cond, 2),
                   start_at_step=0, end_at_step=2, return_with_leftover_noise="enable", **common)
    latent = g.add("KSamplerAdvanced", model=low, add_noise="disable", noise_seed=0, latent_image=latent,
                   start_at_step=2, end_at_step=4, return_with_leftover_noise="disable", **common)
    _finish(g, g.add("VAEDecode", samples=latent, vae=vae), WAN_FPS, None, p.smooth)
    return g
