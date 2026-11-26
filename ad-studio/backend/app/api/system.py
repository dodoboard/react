from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from ..config import WORKFLOWS_DIR, boot, config, paths
from ..events import broker
from ..media import video_encoder
from ..pipeline import product as product_mod
from ..pipeline.runner import runner
from ..providers import comfy, ollama, tts

router = APIRouter(prefix="/api", tags=["system"])
AUDIO = {".mp3", ".m4a", ".wav", ".ogg"}


def _mask(k: str) -> str:
    return (k[:4] + "•" * 8 + k[-4:]) if len(k) > 10 else ("•" * len(k))


@router.get("/config")
def get_config() -> dict:
    d = config.get().model_dump()
    d["elevenlabs_api_key"] = _mask(d["elevenlabs_api_key"])
    return d | {"dry_run": boot.dry_run}


@router.put("/config")
def put_config(patch: dict) -> dict:
    patch.pop("dry_run", None)
    if "•" in patch.get("elevenlabs_api_key", ""):
        patch.pop("elevenlabs_api_key")
    try:
        config.update(patch)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return get_config()


async def _safe(coro, timeout: float = 4):
    try:
        return {"ok": True, **(await asyncio.wait_for(coro, timeout))}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200] or e.__class__.__name__}


async def _ollama() -> dict:
    models = await ollama.list_models()
    want = config.get().ollama_model
    return {"models": len(models), "model_ready": any(m["name"] == want or m["name"].split(":")[0] == want for m in models)}


async def _comfy() -> dict:
    st = await comfy.system_stats()
    dev = (st.get("devices") or [{}])[0]
    return {"gpu": dev.get("name", ""), "vram_total": dev.get("vram_total", 0), "vram_free": dev.get("vram_free", 0),
            "version": st.get("system", {}).get("comfyui_version")}


async def _tts() -> dict:
    if config.get().tts_provider == "chatterbox":
        ok = importlib.util.find_spec("chatterbox") is not None
        if not ok:
            raise RuntimeError("chatterbox-tts kurulu değil")
        return {"provider": "chatterbox"}
    return {"provider": "elevenlabs", **(await tts.elevenlabs_quota())}


@router.get("/health")
async def health() -> dict:
    if boot.dry_run:
        demo = {"ok": True, "demo": True}
        return {"dry_run": True, "ollama": demo, "comfy": demo | {"gpu": "DEMO"}, "tts": demo | {"provider": "stub"},
                "encoder": await video_encoder(), "queue": runner.snapshot(), "rembg": product_mod.rembg_available()}
    o, c, t = await asyncio.gather(_safe(_ollama()), _safe(_comfy()), _safe(_tts(), 8))
    return {"dry_run": False, "ollama": o, "comfy": c, "tts": t, "encoder": await video_encoder(), "queue": runner.snapshot(),
            "rembg": product_mod.rembg_available()}


@router.get("/ollama/models")
async def ollama_models() -> list[dict]:
    if boot.dry_run:
        return []
    try:
        return await ollama.list_models()
    except Exception as e:
        raise HTTPException(502, f"Ollama erişilemiyor: {e}") from e


@router.get("/voices")
async def voices() -> list[dict]:
    local = [{"id": f.name, "name": f.stem, "preview_url": None,"category": "local"}
             for f in sorted(paths.voices.iterdir()) if f.suffix.lower() in AUDIO]
    if config.get().tts_provider == "chatterbox" or boot.dry_run:
        return local
    try:
        return await tts.elevenlabs_voices()
    except Exception as e:
        raise HTTPException(502, f"ElevenLabs: {e}") from e


@router.post("/voices/upload")
async def upload_voice(file: UploadFile) -> dict:
    return await _save(file, paths.voices)


@router.get("/music")
def music() -> list[dict]:
    return [{"name": f.name, "size": f.stat().st_size} for f in sorted(paths.music.iterdir()) if f.suffix.lower() in AUDIO]


@router.post("/music")
async def upload_music(file: UploadFile) -> dict:
    return await _save(file, paths.music)


@router.delete("/music/{name}")
def delete_music(name: str) -> dict:
    p = (paths.music / name).resolve()
    if p.parent != paths.music.resolve():
        raise HTTPException(400)
    p.unlink(missing_ok=True)
    return {"ok": True}


IMAGES = {".png", ".jpg", ".jpeg", ".webp"}


@router.get("/avatars")
def avatars() -> list[dict]:
    return [{"name": f.name, "url": paths.url(f)} for f in sorted(paths.avatars.iterdir()) if f.suffix.lower() in IMAGES]


@router.post("/avatars")
async def upload_avatar(file: UploadFile) -> dict:
    name = Path(file.filename or "avatar.png").name
    if Path(name).suffix.lower() not in IMAGES:
        raise HTTPException(400, "PNG/JPG yükleyin")
    (paths.avatars / name).write_bytes(await file.read())
    return {"name": name, "url": paths.url(paths.avatars / name)}


@router.post("/avatars/generate")
async def generate_avatar(body: dict) -> dict:
    """Synthetic persona via the image workflow (never a real person's likeness)."""
    from ..pipeline import graphics
    desc = str(body.get("description") or "friendly young adult, casual outfit")[:300]
    name = f"persona_{len(list(paths.avatars.iterdir())) + 1}.png"
    if boot.dry_run:
        graphics.stub_scene(paths.avatars / name, 3, "Persona", desc)
        return {"name": name, "url": paths.url(paths.avatars / name)}
    cfg = config.get()
    graph = comfy.fill(comfy.load_workflow(cfg.image_workflow), {
        "prompt": f"vertical selfie video frame of a fictional {desc}, looking at camera, smiling, holding phone at arm's length, "
                  "natural home lighting, realistic skin, upper body, centered face",
        "negative": cfg.negative_prompt + ", celebrity, famous person", "seed": comfy.seed(), "width": 768, "height": 1344,
        "steps": cfg.image_steps, "filename_prefix": "adforge/persona"})
    files = await comfy.run(graph, paths.avatars, Path(name).stem)
    files[0].rename(paths.avatars / name)
    return {"name": name, "url": paths.url(paths.avatars / name)}


@router.delete("/avatars/{name}")
def delete_avatar(name: str) -> dict:
    p = (paths.avatars / name).resolve()
    if p.parent != paths.avatars.resolve():
        raise HTTPException(400)
    p.unlink(missing_ok=True)
    return {"ok": True}


@router.get("/workflows")
def workflows() -> list[str]:
    return sorted(p.stem for p in WORKFLOWS_DIR.glob("*.json"))


@router.post("/workflows")
async def upload_workflow(file: UploadFile) -> dict:
    if not (file.filename or "").endswith(".json"):
        raise HTTPException(400, "API formatında .json workflow yükleyin")
    return await _save(file, WORKFLOWS_DIR)


async def _save(file: UploadFile, folder: Path) -> dict:
    name = Path(file.filename or "file").name
    ext = Path(name).suffix.lower()
    if folder != WORKFLOWS_DIR and ext not in AUDIO:
        raise HTTPException(400, "Desteklenmeyen ses türü")
    (folder / name).write_bytes(await file.read())
    return {"name": name}


@router.get("/events")
async def events(request: Request) -> StreamingResponse:
    q = broker.subscribe()

    async def gen():
        try:
            yield "retry: 2000\n\n"
            while not await request.is_disconnected():
                try:
                    msg = await asyncio.wait_for(q.get(), 15)
                    yield f"data: {msg}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            broker.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
