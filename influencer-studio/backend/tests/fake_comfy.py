"""Fake ComfyUI (HTTP + WebSocket protocol) for tests and GPU-less UI development.

    python -m tests.fake_comfy --port 8188

Validates graph links like ComfyUI does, streams progress over /ws and returns placeholder
PNGs sized from EmptyFlux2LatentImage, or a placeholder MP4 (with a tone when the graph
attaches audio) for SaveVideo graphs.
"""

from __future__ import annotations

import argparse
import asyncio
import colorsys
import hashlib
import io
import math
import struct
import textwrap
import uuid

import av

from fastapi import FastAPI, File, Form, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response
from PIL import Image, ImageDraw

from studio.flux2 import PROFILES
from studio.video import MODE_FILES


def _all_models() -> dict[str, list[str]]:
    models: dict[str, set[str]] = {"loras": {"zz_demo_lora.safetensors"}}
    for p in PROFILES.values():
        for folder, name in p.required.items():
            models.setdefault(folder, set()).add(name)
    for files in MODE_FILES.values():
        for f in files:
            models.setdefault(f.folder, set()).add(f.name)
    return {k: sorted(v) for k, v in models.items()}


ALL_MODELS = _all_models()

KNOWN_NODES = {
    "UNETLoader", "LoraLoaderModelOnly", "CLIPLoader", "VAELoader", "CLIPTextEncode", "LoadImage",
    "ImageScaleToTotalPixels", "VAEEncode", "ReferenceLatent", "RandomNoise", "CFGGuider", "KSamplerSelect",
    "Flux2Scheduler", "EmptyFlux2LatentImage", "SamplerCustomAdvanced", "VAEDecode", "PreviewImage",
    # video
    "ImageScale", "CLIPVisionLoader", "CLIPVisionEncode", "LoadVideo", "GetVideoComponents", "LoadAudio",
    "ImageFromBatch", "ImageBatch", "WanAnimate2Cache", "WanAnimate2ToVideo", "ModelSamplingSD3", "BasicScheduler",
    "SamplerCustom", "TrimVideoLatent", "WanDancerEncodeAudio", "StringConcatenate", "SkipLayerGuidanceDiTSimple",
    "WanDancerVideo", "LatentCutToBatch", "WanDancerPadKeyframesList", "ConditioningZeroOut", "RebatchImages",
    "WanImageToVideo", "KSamplerAdvanced", "FrameInterpolationModelLoader", "FrameInterpolate", "CreateVideo",
    "SaveVideo", "ModelPatchLoader", "AudioEncoderLoader", "AudioEncoderEncode", "WanInfiniteTalkToVideo",
}
_MODEL_INPUTS = {
    ("UNETLoader", "unet_name"): "diffusion_models",
    ("CLIPLoader", "clip_name"): "text_encoders",
    ("VAELoader", "vae_name"): "vae",
    ("LoraLoaderModelOnly", "lora_name"): "loras",
    ("CLIPVisionLoader", "clip_name"): "clip_vision",
    ("FrameInterpolationModelLoader", "model_name"): "frame_interpolation",
    ("ModelPatchLoader", "name"): "model_patches",
    ("AudioEncoderLoader", "audio_encoder_name"): "audio_encoders",
}
_INPUT_FILES = {("LoadImage", "image"), ("LoadVideo", "file"), ("LoadAudio", "audio")}
_SAMPLERS = {"SamplerCustom", "SamplerCustomAdvanced", "KSamplerAdvanced"}
_VIDEO_SIZE_NODES = ("WanAnimate2ToVideo", "WanDancerVideo", "WanImageToVideo", "WanInfiniteTalkToVideo")


def _placeholder_video(width: int, height: int, label: str, fps: int, with_audio: bool, frames: int = 24) -> bytes:
    """A short MP4 with a bouncing figure, so UI video players have something real to play."""
    buf = io.BytesIO()
    with av.open(buf, "w", format="mp4") as out:
        video = out.add_stream("libx264", rate=fps)
        video.width, video.height, video.pix_fmt = width, height, "yuv420p"
        audio = out.add_stream("aac", rate=44100, layout="stereo") if with_audio else None
        for i in range(frames):
            img = Image.new("RGB", (width, height), (24, 24, 32))
            draw = ImageDraw.Draw(img)
            bounce = int(abs(math.sin(i / frames * math.pi * 2)) * height * 0.12)
            cx, cy, r = width // 2, int(height * 0.38) - bounce, min(width, height) // 7
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(235, 220, 205))
            draw.rounded_rectangle([cx - 2 * r, cy + r + 8, cx + 2 * r, cy + 5 * r], radius=r, fill=(212, 255, 58))
            draw.multiline_text((16, 16), "\n".join(textwrap.wrap(label, 40)[:5]), fill=(255, 255, 255))
            for packet in video.encode(av.VideoFrame.from_image(img)):
                out.mux(packet)
        for packet in video.encode():
            out.mux(packet)
        if audio is not None:
            samples = 44100 * frames // fps
            for start in range(0, samples, 1024):
                n = min(1024, samples - start)
                frame = av.AudioFrame(format="s16", layout="stereo", samples=n)
                frame.planes[0].update(b"".join(
                    struct.pack("<hh", v, v) for v in (int(6000 * math.sin((start + k) * 0.06)) for k in range(n))
                ) + bytes(frame.planes[0].buffer_size - n * 4))
                frame.sample_rate, frame.pts = 44100, start
                for packet in audio.encode(frame):
                    out.mux(packet)
            for packet in audio.encode():
                out.mux(packet)
    return buf.getvalue()


def _placeholder(width: int, height: int, label: str, seed: str) -> bytes:
    hue = int(hashlib.sha1(seed.encode()).hexdigest()[:4], 16) / 0xFFFF
    top = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(hue, 0.55, 0.55))
    bottom = tuple(int(c * 255) for c in colorsys.hsv_to_rgb((hue + 0.15) % 1, 0.7, 0.18))
    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)
    for y in range(height):
        t = y / height
        draw.line([(0, y), (width, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    cx, cy, r = width // 2, int(height * 0.42), min(width, height) // 5
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(235, 220, 205))
    draw.rounded_rectangle([cx - 2 * r, cy + r + 10, cx + 2 * r, height + r], radius=r, fill=(235, 220, 205))
    draw.multiline_text((24, 24), "\n".join(textwrap.wrap(label, 48)[:6]), fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def create_fake_comfy(models: dict[str, list[str]] | None = None, delay: float = 0.01) -> FastAPI:
    app = FastAPI()
    app.state.models = ALL_MODELS if models is None else models
    app.state.prompts = []  # graphs received, for test assertions
    app.state.frees = 0
    clients: dict[str, WebSocket] = {}
    inputs: dict[str, bytes] = {}
    outputs: dict[str, bytes] = {}
    history: dict[str, dict] = {}

    @app.get("/system_stats")
    def system_stats() -> dict:
        return {"system": {"comfyui_version": "fake"}, "devices": [{"name": "Fake GPU", "vram_total": 16 * 2**30}]}

    @app.post("/free")
    def free(body: dict) -> dict:
        app.state.frees += 1
        return {}

    @app.get("/models/{folder}")
    def models_in(folder: str) -> list[str]:
        return app.state.models.get(folder, [])

    @app.post("/upload/image")
    async def upload(image: UploadFile = File(...), overwrite: str = Form("false"), type: str = Form("input")) -> dict:
        inputs[image.filename] = await image.read()
        return {"name": image.filename, "subfolder": "", "type": type}

    @app.websocket("/ws")
    async def ws(websocket: WebSocket, clientId: str) -> None:
        await websocket.accept()
        clients[clientId] = websocket
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            clients.pop(clientId, None)

    def validate(graph: dict) -> dict:
        errors: dict[str, dict] = {}

        def fail(node_id: str, message: str) -> None:
            errors.setdefault(node_id, {"errors": [], "class_type": graph[node_id].get("class_type")})
            errors[node_id]["errors"].append({"message": message, "details": ""})

        for node_id, node in graph.items():
            cls = node.get("class_type")
            if cls not in KNOWN_NODES:
                fail(node_id, f"unknown node type {cls}")
            for name, value in node.get("inputs", {}).items():
                if isinstance(value, list) and (len(value) != 2 or str(value[0]) not in graph):
                    fail(node_id, f"bad link on input {name}")
                folder = _MODEL_INPUTS.get((cls, name))
                if folder and value not in app.state.models.get(folder, []):
                    fail(node_id, "Value not in list")
                if (cls, name) in _INPUT_FILES and value not in inputs:
                    fail(node_id, "Invalid file")
        return errors

    async def execute(prompt_id: str, client_id: str, graph: dict) -> None:
        ws = clients.get(client_id)

        async def send(kind: str, data: dict) -> None:
            if ws:
                await ws.send_json({"type": kind, "data": data | {"prompt_id": prompt_id}})

        await send("execution_start", {})
        if any(n["class_type"] == "SaveVideo" for n in graph.values()):
            for node_id in [i for i, n in graph.items() if n["class_type"] in _SAMPLERS]:
                for step in range(1, 5):
                    await asyncio.sleep(delay)
                    await send("progress", {"value": step, "max": 4, "node": node_id})
            size = next(n["inputs"] for n in graph.values() if n["class_type"] in _VIDEO_SIZE_NODES)
            create = next(n["inputs"] for n in graph.values() if n["class_type"] == "CreateVideo")
            label = f"fake video · {next(n['class_type'] for n in graph.values() if n['class_type'] in _VIDEO_SIZE_NODES)}"
            name = f"fake_{prompt_id}.mp4"
            outputs[name] = await asyncio.to_thread(
                _placeholder_video, size["width"], size["height"], label, int(create["fps"]), "audio" in create,
                2 * int(create["fps"]),
            )
            history[prompt_id] = {"outputs": {"99": {"images": [{"filename": name, "subfolder": "", "type": "output"}],
                                                      "animated": [True]}}}
            await send("executing", {"node": None})
            return
        latent = next(n["inputs"] for n in graph.values() if n["class_type"] == "EmptyFlux2LatentImage")
        steps = next(n["inputs"]["steps"] for n in graph.values() if n["class_type"] == "Flux2Scheduler")
        text = next(n["inputs"]["text"] for n in graph.values() if n["class_type"] == "CLIPTextEncode")
        seed = next(n["inputs"]["noise_seed"] for n in graph.values() if n["class_type"] == "RandomNoise")
        refs = sum(n["class_type"] == "LoadImage" for n in graph.values())
        for step in range(1, steps + 1):
            await asyncio.sleep(delay)
            await send("progress", {"value": step, "max": steps, "node": "sampler"})
        images = []
        for i in range(latent["batch_size"]):
            name = f"fake_{prompt_id}_{i}.png"
            label = f"FLUX.2 fake render · refs={refs} · seed={seed}\n{text}"
            outputs[name] = _placeholder(latent["width"], latent["height"], label, f"{text}{seed}{i}")
            images.append({"filename": name, "subfolder": "", "type": "temp"})
        history[prompt_id] = {"outputs": {"99": {"images": images}}}
        await send("executing", {"node": None})

    @app.post("/prompt")
    async def prompt(body: dict) -> JSONResponse:
        graph = body["prompt"]
        app.state.prompts.append(graph)
        if errors := validate(graph):
            return JSONResponse({"error": {"message": "Prompt outputs failed validation"}, "node_errors": errors}, 400)
        prompt_id = uuid.uuid4().hex
        asyncio.create_task(execute(prompt_id, body.get("client_id", ""), graph))
        return JSONResponse({"prompt_id": prompt_id, "number": len(app.state.prompts), "node_errors": {}})

    @app.get("/history/{prompt_id}")
    def get_history(prompt_id: str) -> dict:
        return {prompt_id: history[prompt_id]} if prompt_id in history else {}

    @app.get("/view")
    def view(filename: str, subfolder: str = "", type: str = "output") -> Response:
        return Response(outputs[filename], media_type="video/mp4" if filename.endswith(".mp4") else "image/png")

    return app


if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8188)
    parser.add_argument("--delay", type=float, default=0.25, help="seconds per sampling step")
    args = parser.parse_args()
    uvicorn.run(create_fake_comfy(delay=args.delay), host="127.0.0.1", port=args.port)
