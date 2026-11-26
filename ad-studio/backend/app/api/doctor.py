"""System doctor: verifies the real machine (ffmpeg, fonts, Ollama, ComfyUI nodes + model files, TTS, YouTube)
and runs a short smoke test through the real providers."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import re
import shutil
import time
from pathlib import Path

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from ..config import WORKFLOWS_DIR, boot, config, paths
from ..media import FFMPEG, _exec, bold_font, video_encoder
from ..pipeline.gpu import gpu_lock
from ..providers import comfy, ollama, tts, yt

router = APIRouter(prefix="/api/doctor", tags=["doctor"])
FILTERS = ["subtitles", "lut3d", "minterpolate", "deesser", "xfade", "sidechaincompress", "loudnorm", "zoompan", "vignette"]
MODEL_INPUTS = {"ckpt_name", "unet_name", "vae_name", "clip_name", "clip_name1", "clip_name2", "lora_name", "model_name",
                "audio_encoder_name", "pulid_file", "name"}
NODE_PACKS = [
    (r"^PulidFlux|^ApplyPulidFlux", "ComfyUI-PuLID-Flux (Manager → Install Custom Nodes → 'PuLID Flux')"),
    (r"^WanInfiniteTalk|^ModelPatchLoader|^AudioEncoder", "ComfyUI'ı en güncel sürüme yükseltin (yerleşik node)"),
    (r"^Wan|^CreateVideo|^SaveVideo|^ReferenceLatent|^FluxKontext", "ComfyUI'ı en güncel sürüme yükseltin (yerleşik node)"),
]


class Check(BaseModel):
    id: str
    group: str
    label: str
    status: str  # ok | warn | fail | skip
    detail: str = ""
    fix: str = ""


def node_hint(cls: str) -> str:
    return next((h for p, h in NODE_PACKS if re.search(p, cls)), "Custom node paketi eksik — ComfyUI Manager ile arayın")


def active_workflows() -> dict[str, str]:
    from ..pipeline import visuals
    cfg = config.get()
    wf = {"Görsel": visuals.image_workflow(), "Ürün/kimlik (Kontext)": cfg.kontext_workflow,
          "Hareket (i2v)": visuals.video_workflow(), "Konuşan sunucu": cfg.avatar_workflow}
    return {k: v for k, v in wf.items() if (WORKFLOWS_DIR / f"{v}.json").exists()}


def runtime_models() -> dict[str, str]:
    cfg = config.get()
    return {"{{upscale_model}}": cfg.upscale_model, "{{lora}}": cfg.realism_lora, "{{fast_lora}}": cfg.i2v_fast_lora}


def validate_workflow(graph: dict, object_info: dict) -> tuple[list[str], list[tuple[str, str]]]:
    """Returns (missing node classes, missing model files as (input, filename))."""
    missing_nodes: list[str] = []
    missing_models: list[tuple[str, str]] = []
    subst = runtime_models()
    for node in graph.values():
        if not isinstance(node, dict):
            continue
        cls = node.get("class_type", "")
        info = object_info.get(cls)
        if info is None:
            if cls not in missing_nodes:
                missing_nodes.append(cls)
            continue
        spec = {**(info.get("input", {}).get("required") or {}), **(info.get("input", {}).get("optional") or {})}
        for key, val in (node.get("inputs") or {}).items():
            if key not in MODEL_INPUTS or not isinstance(val, str):
                continue
            val = subst.get(val, val)
            if not val or "{{" in val or not re.search(r"\.(safetensors|pth|pt|ckpt|gguf|bin|onnx)$", val):
                continue
            allowed = spec.get(key, [None])[0]
            if isinstance(allowed, list) and val not in allowed:
                missing_models.append((key, val))
    return missing_nodes, missing_models


async def check_ffmpeg() -> list[Check]:
    out: list[Check] = []
    code, so, _ = await _exec(FFMPEG, "-hide_banner", "-version")
    ver = so.decode(errors="ignore").splitlines()[0] if not code and so else ""
    out.append(Check(id="ffmpeg", group="Sistem", label="FFmpeg", status="ok" if ver else "fail", detail=ver,
                     fix="" if ver else "winget install Gyan.FFmpeg  (PATH'e ekleyin)"))
    if not ver:
        return out
    enc = await video_encoder()
    out.append(Check(id="nvenc", group="Sistem", label="GPU video kodlama (NVENC)", status="ok" if enc == "h264_nvenc" else "warn",
                     detail=enc, fix="" if enc == "h264_nvenc" else "NVIDIA sürücüsünü güncelleyin; NVENC'li FFmpeg (gyan.dev full) kullanın"))
    _, fl, _ = await _exec(FFMPEG, "-hide_banner", "-filters")
    have = fl.decode(errors="ignore")
    miss = [f for f in FILTERS if not re.search(rf"\s{f}\s", have)]
    out.append(Check(id="filters", group="Sistem", label="FFmpeg filtreleri", status="ok" if not miss else "fail",
                     detail="tamam" if not miss else "eksik: " + ", ".join(miss), fix="" if not miss else "Tam (full) FFmpeg derlemesi kurun"))
    f = bold_font()
    out.append(Check(id="fonts", group="Sistem", label="Altyazı/kapak fontu", status="ok" if f else "warn", detail=f or "sistem varsayılanı",
                     fix="" if f else "python scripts/setup_models.py --only fonts"))
    free = shutil.disk_usage(boot.data_dir).free / 1024 ** 3
    out.append(Check(id="disk", group="Sistem", label="Boş disk alanı", status="ok" if free > 30 else "warn" if free > 10 else "fail",
                     detail=f"{free:.0f} GB", fix="" if free > 30 else "Uzun belgeseller için 30+ GB önerilir"))
    return out


async def check_ollama(deep: bool) -> list[Check]:
    cfg = config.get()
    try:
        models = await asyncio.wait_for(ollama.list_models(), 5)
    except Exception as e:
        return [Check(id="ollama", group="LLM", label="Ollama sunucusu", status="fail", detail=str(e)[:160],
                      fix="Ollama'yı başlatın: ollama serve")]
    names = [m["name"] for m in models]
    ready = any(n == cfg.ollama_model or n.split(":")[0] == cfg.ollama_model for n in names)
    out = [Check(id="ollama", group="LLM", label="Ollama sunucusu", status="ok", detail=f"{len(names)} model"),
           Check(id="ollama_model", group="LLM", label=f"Model: {cfg.ollama_model}", status="ok" if ready else "fail",
                 detail="yüklü" if ready else "bulunamadı", fix="" if ready else f"ollama pull {cfg.ollama_model}")]
    if deep and ready:
        class Probe(BaseModel):
            ok: bool
            word: str
        t0 = time.time()
        try:
            r = await asyncio.wait_for(ollama.chat_json("Yalnızca JSON döndür.", 'ok=true ve word="merhaba" döndür.', Probe, retries=1), 120)
            out.append(Check(id="ollama_json", group="LLM", label="Yapılandırılmış çıktı (JSON şema)", status="ok" if r.ok else "warn",
                             detail=f"{time.time() - t0:.1f} sn"))
        except Exception as e:
            out.append(Check(id="ollama_json", group="LLM", label="Yapılandırılmış çıktı (JSON şema)", status="fail", detail=str(e)[:160],
                             fix="Ollama'yı güncelleyin (format=JSON şema desteği 0.5+)"))
    return out


async def check_comfy() -> list[Check]:
    try:
        st = await asyncio.wait_for(comfy.system_stats(), 5)
    except Exception as e:
        return [Check(id="comfy", group="ComfyUI", label="ComfyUI sunucusu", status="fail", detail=str(e)[:160],
                      fix="ComfyUI'ı başlatın (run_nvidia_gpu.bat) — adres Ayarlar'da")]
    dev = (st.get("devices") or [{}])[0]
    vram = dev.get("vram_total", 0) / 1024 ** 3
    out = [Check(id="comfy", group="ComfyUI", label="ComfyUI sunucusu", status="ok",
                 detail=f"{dev.get('name', '')} · {vram:.0f} GB VRAM · v{st.get('system', {}).get('comfyui_version', '?')}")]
    try:
        async with httpx.AsyncClient(base_url=config.get().comfy_url.rstrip("/"), timeout=60) as c:
            info = (await c.get("/object_info")).json()
    except Exception as e:
        out.append(Check(id="object_info", group="ComfyUI", label="Node listesi", status="fail", detail=str(e)[:160]))
        return out
    for label, name in active_workflows().items():
        graph = comfy.load_workflow(name)
        nodes, models = validate_workflow(graph, info)
        if nodes:
            out.append(Check(id=f"wf_{name}", group="ComfyUI", label=f"{label} · {name}", status="fail",
                             detail="eksik node: " + ", ".join(nodes), fix=" · ".join(sorted({node_hint(n) for n in nodes}))))
        elif models:
            out.append(Check(id=f"wf_{name}", group="ComfyUI", label=f"{label} · {name}", status="fail",
                             detail="eksik model: " + ", ".join(f for _, f in models),
                             fix=f"python scripts/setup_models.py --comfy <ComfyUI klasörü> --files {' '.join(f for _, f in models)}"))
        else:
            out.append(Check(id=f"wf_{name}", group="ComfyUI", label=f"{label} · {name}", status="ok", detail="node ve modeller tamam"))
    if vram and vram < 15 and config.get().avatar_workflow in ("wan22_s2v", "infinitetalk"):
        out.append(Check(id="vram", group="ComfyUI", label="Konuşan sunucu için VRAM", status="warn", detail=f"{vram:.0f} GB",
                         fix="Sunucu klip süresini kısaltın (Ayarlar → presenter_chunk) veya GGUF modeller kullanın"))
    return out


async def check_tts() -> list[Check]:
    cfg = config.get()
    if cfg.tts_provider == "chatterbox":
        ok = importlib.util.find_spec("chatterbox") is not None
        w = importlib.util.find_spec("faster_whisper") is not None
        return [Check(id="tts", group="Ses", label="Chatterbox (lokal)", status="ok" if ok else "fail",
                      fix="" if ok else "pip install -r backend/requirements-local-tts.txt"),
                Check(id="whisper", group="Ses", label="faster-whisper (altyazı hizalama)", status="ok" if w else "warn",
                      fix="" if w else "pip install faster-whisper")]
    if not cfg.elevenlabs_api_key:
        return [Check(id="tts", group="Ses", label="ElevenLabs", status="fail", detail="API anahtarı yok", fix="Ayarlar → Seslendirme")]
    out = []
    try:
        q = await asyncio.wait_for(tts.elevenlabs_quota(), 10)
        left = q["limit"] - q["used"]
        out.append(Check(id="tts", group="Ses", label="ElevenLabs", status="ok" if left > 20000 else "warn",
                         detail=f"{q.get('tier')} · {left:,} karakter kaldı".replace(",", "."),
                         fix="" if left > 20000 else "Uzun belgesel ≈ 8-12 bin karakter; planı yükseltin"))
        async with httpx.AsyncClient(base_url=tts.EL_BASE, timeout=10) as c:
            ms = [m["model_id"] for m in (await c.get("/v1/models", headers=tts._el_headers())).json()]
        has = cfg.elevenlabs_model in ms
        out.append(Check(id="tts_model", group="Ses", label=f"Model: {cfg.elevenlabs_model}", status="ok" if has else "fail",
                         fix="" if has else "Ayarlar'dan erişilebilir bir model seçin"))
    except Exception as e:
        out.append(Check(id="tts", group="Ses", label="ElevenLabs", status="fail", detail=str(e)[:160], fix="API anahtarını kontrol edin"))
    return out


def check_youtube() -> list[Check]:
    lib = importlib.util.find_spec("googleapiclient") is not None
    tokens = list(yt.TOKENS.glob("channel_*.json")) if yt.TOKENS.exists() else []
    return [
        Check(id="yt_lib", group="YouTube", label="Google API kütüphaneleri", status="ok" if lib else "warn",
              fix="" if lib else "pip install -r backend/requirements-youtube.txt"),
        Check(id="yt_secret", group="YouTube", label="OAuth istemci dosyası", status="ok" if yt.SECRET.exists() else "warn",
              fix="" if yt.SECRET.exists() else "Ayarlar → YouTube → client_secret.json yükle"),
        Check(id="yt_tokens", group="YouTube", label="Bağlı kanallar", status="ok" if tokens else "skip", detail=f"{len(tokens)} kanal"),
    ]


@router.get("")
async def run(deep: bool = False) -> dict:
    groups = await asyncio.gather(check_ffmpeg(), check_ollama(deep), check_comfy(), check_tts())
    checks = [c for g in groups for c in g] + check_youtube()
    worst = "fail" if any(c.status == "fail" for c in checks) else "warn" if any(c.status == "warn" for c in checks) else "ok"
    return {"status": worst, "dry_run": boot.dry_run, "checks": [c.model_dump() for c in checks]}


@router.post("/smoke")
async def smoke() -> dict:
    """Real providers, tiny workloads: LLM JSON → 1 image → 1 TTS sentence → 3 s render."""
    from ..pipeline import visuals
    from ..pipeline.compose import WIDE, Effects, Segment, compose

    d = paths.media / "smoke"
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    steps: list[dict] = []

    async def step(name: str, fn):
        t0 = time.time()
        try:
            res = await fn()
            steps.append({"name": name, "ok": True, "seconds": round(time.time() - t0, 1), "detail": res or ""})
            return True
        except Exception as e:
            steps.append({"name": name, "ok": False, "seconds": round(time.time() - t0, 1), "detail": str(e)[:300]})
            return False

    class Line(BaseModel):
        line: str

    line = {"text": "Bu bir sistem testidir; her şey yolunda görünüyor."}

    async def llm():
        r = await ollama.chat_json("Yalnızca JSON döndür.", "Belgesel açılışı için 12 kelimelik tek cümle yaz.", Line)
        line["text"] = r.line
        await ollama.unload()
        return r.line

    async def image():
        async def p(_: float) -> None: ...
        f = await visuals._t2i("an ancient stone bridge over a misty river at dawn", d, "smoke", p, size=(832, 480),
                               shot="establishing", domain="doc")
        line["img"] = str(f)
        await comfy.free()
        return paths.url(f)

    async def voice():
        from ..pipeline import speech
        r = await tts.synthesize(speech.spoken(line["text"], "tr"), d / "voice.mp3", "tr", None, False)
        line["voice"] = str(r.audio)
        return f"{r.duration:.1f} sn · {len(r.words)} kelime hizalandı"

    async def render():
        img = Path(line.get("img") or "")
        if not img.exists():
            from ..pipeline import graphics
            img = graphics.stub_scene(d / "fallback.png", 0, "Test", "", (1344, 768))
        out = await compose([Segment(img, 3.0)], Path(line["voice"]), None, d / "smoke.mp4", d, None, 0.0,
                            Effects(punch=False, progress_color=None, sfx_volume=0, canvas=WIDE, film=True, loudness=-16))
        return paths.url(out)

    async with gpu_lock():
        await step("LLM (Ollama)", llm)
        await step("Görsel (ComfyUI)", image)
        ok_voice = await step("Ses (TTS)", voice)
    if ok_voice:
        await step("Montaj (FFmpeg)", render)
    return {"steps": steps, "video_url": paths.url(d / "smoke.mp4") if (d / "smoke.mp4").exists() else None,
            "image_url": paths.url(Path(line["img"])) if line.get("img") else None}


def manifest() -> list[dict]:
    p = Path(__file__).resolve().parents[3] / "scripts" / "models.json"
    return json.loads(p.read_text()) if p.exists() else []


@router.get("/manifest")
def get_manifest() -> list[dict]:
    return manifest()
