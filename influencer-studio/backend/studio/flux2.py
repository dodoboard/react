"""FLUX.2 model profiles and ComfyUI (API format) graph builder.

Graph mirrors ComfyUI's official FLUX.2 templates: UNETLoader + CLIPLoader(type=flux2) +
VAELoader → CFGGuider → SamplerCustomAdvanced with Flux2Scheduler. Each reference image is
VAE-encoded and chained onto both conditionings with ReferenceLatent (multi-reference edit).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

_HF = "https://huggingface.co"
_VAE = ("vae", f"{_HF}/Comfy-Org/flux2-dev/resolve/main/split_files/vae/flux2-vae.safetensors")
_QWEN3_4B = ("text_encoders", f"{_HF}/Comfy-Org/z_image_turbo/resolve/main/split_files/text_encoders/qwen_3_4b.safetensors")


@dataclass(frozen=True)
class Profile:
    id: str
    label: str
    unet: str
    text_encoder: str
    vae: str
    steps: int
    cfg: float
    license: str
    downloads: tuple[tuple[str, str], ...]  # (ComfyUI models/ subfolder, url)
    max_refs: int = 4

    @property
    def required(self) -> dict[str, str]:
        return {"diffusion_models": self.unet, "text_encoders": self.text_encoder, "vae": self.vae}


PROFILES: dict[str, Profile] = {
    p.id: p
    for p in (
        Profile(
            id="klein-4b",
            label="FLUX.2 [klein] 4B · distilled",
            unet="flux-2-klein-4b-fp8.safetensors",
            text_encoder="qwen_3_4b.safetensors",
            vae="flux2-vae.safetensors",
            steps=4,
            cfg=1.0,
            license="Apache-2.0",
            downloads=(
                ("diffusion_models", f"{_HF}/black-forest-labs/FLUX.2-klein-4b-fp8/resolve/main/flux-2-klein-4b-fp8.safetensors"),
                _QWEN3_4B,
                _VAE,
            ),
        ),
        Profile(
            id="klein-4b-base",
            label="FLUX.2 [klein] 4B · base",
            unet="flux-2-klein-base-4b-fp8.safetensors",
            text_encoder="qwen_3_4b.safetensors",
            vae="flux2-vae.safetensors",
            steps=20,
            cfg=5.0,
            license="Apache-2.0",
            downloads=(
                ("diffusion_models", f"{_HF}/black-forest-labs/FLUX.2-klein-base-4b-fp8/resolve/main/flux-2-klein-base-4b-fp8.safetensors"),
                _QWEN3_4B,
                _VAE,
            ),
        ),
        Profile(
            id="klein-9b",
            label="FLUX.2 [klein] 9B · distilled",
            unet="flux-2-klein-9b-fp8.safetensors",
            text_encoder="qwen_3_8b_fp8mixed.safetensors",
            vae="flux2-vae.safetensors",
            steps=4,
            cfg=1.0,
            license="FLUX Non-Commercial",
            downloads=(
                ("diffusion_models", f"{_HF}/black-forest-labs/FLUX.2-klein-9b-fp8/resolve/main/flux-2-klein-9b-fp8.safetensors"),
                ("text_encoders", f"{_HF}/Comfy-Org/flux2-klein-9B/resolve/main/split_files/text_encoders/qwen_3_8b_fp8mixed.safetensors"),
                _VAE,
            ),
        ),
    )
}


def build_graph(
    profile: Profile,
    *,
    prompt: str,
    negative: str = "",
    width: int,
    height: int,
    seed: int,
    batch: int = 1,
    references: Sequence[str] = (),
    reference_megapixels: float = 1.0,
    loras: Sequence[tuple[str, float]] = (),
) -> dict[str, dict]:
    """Returns a ComfyUI API-format prompt. `references` are filenames in ComfyUI's input dir."""
    if len(references) > profile.max_refs:
        raise ValueError(f"{profile.id} supports at most {profile.max_refs} reference images")
    graph: dict[str, dict] = {}

    def add(class_type: str, **inputs) -> list:
        node_id = str(len(graph) + 1)
        graph[node_id] = {"class_type": class_type, "inputs": inputs}
        return [node_id, 0]

    model = add("UNETLoader", unet_name=profile.unet, weight_dtype="default")
    for name, strength in loras:
        model = add("LoraLoaderModelOnly", model=model, lora_name=name, strength_model=strength)
    clip = add("CLIPLoader", clip_name=profile.text_encoder, type="flux2", device="default")
    vae = add("VAELoader", vae_name=profile.vae)
    positive = add("CLIPTextEncode", text=prompt, clip=clip)
    negative_cond = add("CLIPTextEncode", text=negative, clip=clip)

    for ref in references:
        image = add("LoadImage", image=ref)
        image = add("ImageScaleToTotalPixels", image=image, upscale_method="lanczos",
                    megapixels=reference_megapixels, resolution_steps=16)
        latent = add("VAEEncode", pixels=image, vae=vae)
        positive = add("ReferenceLatent", conditioning=positive, latent=latent)
        negative_cond = add("ReferenceLatent", conditioning=negative_cond, latent=latent)

    sampled = add(
        "SamplerCustomAdvanced",
        noise=add("RandomNoise", noise_seed=seed),
        guider=add("CFGGuider", model=model, positive=positive, negative=negative_cond, cfg=profile.cfg),
        sampler=add("KSamplerSelect", sampler_name="euler"),
        sigmas=add("Flux2Scheduler", steps=profile.steps, width=width, height=height),
        latent_image=add("EmptyFlux2LatentImage", width=width, height=height, batch_size=batch),
    )
    add("PreviewImage", images=add("VAEDecode", samples=sampled, vae=vae))
    return graph
