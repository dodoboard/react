from __future__ import annotations

import json
import re
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from ..config import config

T = TypeVar("T", bound=BaseModel)
_THINK = re.compile(r"<think>.*?</think>", re.S)


class OllamaError(RuntimeError):
    pass


async def chat_json(system: str, user: str, schema: type[T], retries: int = 2, temperature: float | None = None) -> T:
    cfg = config.get()
    payload = {
        "model": cfg.ollama_model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "format": schema.model_json_schema(),
        "stream": False,
        "keep_alive": "10m",
        "options": {"temperature": cfg.ollama_temperature if temperature is None else temperature, "num_ctx": 8192},
    }
    last: Exception | None = None
    async with httpx.AsyncClient(base_url=cfg.ollama_url, timeout=600) as c:
        for _ in range(retries + 1):
            r = await c.post("/api/chat", json=payload)
            if r.status_code >= 400:
                raise OllamaError(f"Ollama {r.status_code}: {r.text[:300]}")
            content = _THINK.sub("", r.json()["message"]["content"]).strip()
            try:
                return schema.model_validate(json.loads(content))
            except (json.JSONDecodeError, ValidationError) as e:
                last = e
    raise OllamaError(f"Geçersiz JSON çıktı: {last}")


async def unload() -> None:
    """Free VRAM before ComfyUI phase."""
    cfg = config.get()
    try:
        async with httpx.AsyncClient(base_url=cfg.ollama_url, timeout=30) as c:
            await c.post("/api/chat", json={"model": cfg.ollama_model, "messages": [], "keep_alive": 0})
    except httpx.HTTPError:
        pass


async def list_models() -> list[dict]:
    async with httpx.AsyncClient(base_url=config.get().ollama_url, timeout=5) as c:
        r = await c.get("/api/tags")
        r.raise_for_status()
        return [{"name": m["name"], "size": m.get("size", 0)} for m in r.json().get("models", [])]
