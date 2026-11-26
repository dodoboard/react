from __future__ import annotations

import copy
import json
import random
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx
import websockets

from ..config import WORKFLOWS_DIR, config

ProgressCb = Callable[[float], Awaitable[None] | None]


class ComfyError(RuntimeError):
    pass


def load_workflow(name: str) -> dict:
    p = WORKFLOWS_DIR / f"{name}.json"
    if not p.exists():
        raise ComfyError(f"Workflow bulunamadı: {p.name}")
    return {k: v for k, v in json.loads(p.read_text()).items() if not k.startswith("_")}


def fill(graph: dict, values: dict[str, Any]) -> dict:
    """Replace "{{key}}" strings. Exact match keeps the value's type (int seeds etc.)."""
    def walk(v: Any) -> Any:
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, str) and "{{" in v:
            for k, val in values.items():
                tok = "{{" + k + "}}"
                if v == tok:
                    return val
                v = v.replace(tok, str(val))
        return v
    return walk(copy.deepcopy(graph))


def _base() -> str:
    return config.get().comfy_url.rstrip("/")


async def upload_image(path: Path) -> str:
    async with httpx.AsyncClient(base_url=_base(), timeout=60) as c:
        r = await c.post("/upload/image", files={"image": (path.name, path.read_bytes())}, data={"overwrite": "true"})
        r.raise_for_status()
        j = r.json()
        return f"{j['subfolder']}/{j['name']}" if j.get("subfolder") else j["name"]


async def run(graph: dict, out_dir: Path, stem: str, on_progress: ProgressCb | None = None) -> list[Path]:
    client_id = uuid.uuid4().hex
    ws_url = _base().replace("http", "ws", 1) + f"/ws?clientId={client_id}"
    async with websockets.connect(ws_url, max_size=None) as ws, httpx.AsyncClient(base_url=_base(), timeout=120) as c:
        r = await c.post("/prompt", json={"prompt": graph, "client_id": client_id})
        if r.status_code >= 400:
            raise ComfyError(f"ComfyUI /prompt {r.status_code}: {r.text[:500]}")
        pid = r.json()["prompt_id"]
        while True:
            raw = await ws.recv()
            if isinstance(raw, bytes):
                continue  # latent previews
            msg = json.loads(raw)
            data = msg.get("data", {})
            if data.get("prompt_id") not in (None, pid):
                continue
            t = msg.get("type")
            if t == "progress" and on_progress and data.get("max"):
                res = on_progress(data["value"] / data["max"])
                if res is not None:
                    await res
            elif t == "execution_error":
                raise ComfyError(f"{data.get('node_type')}: {data.get('exception_message', '').strip()}")
            elif t == "execution_success" or (t == "executing" and data.get("node") is None):
                break
        hist = (await c.get(f"/history/{pid}")).json().get(pid, {})
        files: list[Path] = []
        for node_out in hist.get("outputs", {}).values():
            for items in node_out.values():
                if not isinstance(items, list):
                    continue
                for it in items:
                    if isinstance(it, dict) and "filename" in it and it.get("type", "output") == "output":
                        b = await c.get("/view", params={"filename": it["filename"], "subfolder": it.get("subfolder", ""), "type": "output"})
                        b.raise_for_status()
                        dst = out_dir / f"{stem}_{len(files)}{Path(it['filename']).suffix}"
                        dst.write_bytes(b.content)
                        files.append(dst)
        if not files:
            raise ComfyError("ComfyUI çıktı üretmedi (Save node var mı?)")
        return files


async def free() -> None:
    try:
        async with httpx.AsyncClient(base_url=_base(), timeout=30) as c:
            await c.post("/free", json={"unload_models": True, "free_memory": True})
    except httpx.HTTPError:
        pass


async def system_stats() -> dict:
    async with httpx.AsyncClient(base_url=_base(), timeout=5) as c:
        r = await c.get("/system_stats")
        r.raise_for_status()
        return r.json()


def seed() -> int:
    return random.randint(1, 2**48)
