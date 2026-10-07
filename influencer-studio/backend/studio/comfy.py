"""Async ComfyUI client: upload inputs, run an API-format graph, collect output images."""

from __future__ import annotations

import json
import mimetypes
import uuid
from typing import Callable, Protocol, Sequence

import httpx
from websockets.asyncio.client import connect

ProgressFn = Callable[[float], None]


class ComfyError(RuntimeError):
    pass


class ComfyBackend(Protocol):
    async def upload(self, data: bytes, filename: str) -> str: ...
    async def run(
        self, graph: dict, on_progress: ProgressFn | None = None, progress_nodes: Sequence[str] = ()
    ) -> list[bytes]: ...
    async def free(self) -> None:
        """Unload ComfyUI's models so another GPU process (the TTS server) has the VRAM."""
        r = await self._http.post("/free", json={"unload_models": True, "free_memory": True})
        r.raise_for_status()

    async def models(self, folder: str) -> list[str]: ...
    async def system_stats(self) -> dict: ...
    async def free(self) -> None: ...
    async def aclose(self) -> None: ...


def _format_validation_error(body: dict) -> str:
    lines = [body.get("error", {}).get("message", "prompt rejected")]
    for node_id, info in (body.get("node_errors") or {}).items():
        for err in info.get("errors", []):
            lines.append(f"{info.get('class_type')}#{node_id}: {err.get('message')} {err.get('details', '')}".strip())
    return "; ".join(lines)


class ComfyClient:
    def __init__(self, base_url: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.ws_url = "ws" + self.base_url.removeprefix("http") + "/ws"
        self.client_id = uuid.uuid4().hex
        self._http = httpx.AsyncClient(base_url=self.base_url, timeout=timeout)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def system_stats(self) -> dict:
        r = await self._http.get("/system_stats")
        r.raise_for_status()
        return r.json()

    async def free(self) -> None:
        """Unload ComfyUI's models so another GPU process (the TTS server) has the VRAM."""
        r = await self._http.post("/free", json={"unload_models": True, "free_memory": True})
        r.raise_for_status()

    async def models(self, folder: str) -> list[str]:
        r = await self._http.get(f"/models/{folder}")
        r.raise_for_status()
        return r.json()

    async def upload(self, data: bytes, filename: str) -> str:
        r = await self._http.post(
            "/upload/image",
            files={"image": (filename, data, mimetypes.guess_type(filename)[0] or "application/octet-stream")},
            data={"overwrite": "true", "type": "input"},
        )
        r.raise_for_status()
        j = r.json()
        return f"{j['subfolder']}/{j['name']}" if j.get("subfolder") else j["name"]

    async def run(
        self, graph: dict, on_progress: ProgressFn | None = None, progress_nodes: Sequence[str] = ()
    ) -> list[bytes]:
        """Queue `graph`, stream progress, return the output files (PNG images or MP4 videos).

        With `progress_nodes` (sampler node ids in execution order) progress is reported across
        all of them, so multi-pass video graphs move 0→1 once instead of once per sampler.
        """
        order = {node_id: i for i, node_id in enumerate(progress_nodes)}
        # Connect before queueing so no event for this prompt can be missed.
        async with connect(f"{self.ws_url}?clientId={self.client_id}", max_size=None, ping_interval=None) as ws:
            r = await self._http.post("/prompt", json={"prompt": graph, "client_id": self.client_id})
            if r.status_code != 200:
                raise ComfyError(_format_validation_error(r.json()))
            prompt_id = r.json()["prompt_id"]
            async for raw in ws:
                if isinstance(raw, bytes):  # latent previews
                    continue
                msg = json.loads(raw)
                data = msg.get("data") or {}
                if data.get("prompt_id") != prompt_id:
                    continue
                kind = msg.get("type")
                if kind == "progress" and on_progress and data.get("max"):
                    fraction = data["value"] / data["max"]
                    if order:
                        if str(data.get("node")) not in order:
                            continue
                        fraction = (order[str(data["node"])] + fraction) / len(order)
                    on_progress(fraction)
                elif kind == "execution_error":
                    raise ComfyError(f"{data.get('node_type')}: {data.get('exception_message', '').strip()}")
                elif kind == "execution_interrupted":
                    raise ComfyError("generation interrupted")
                elif kind == "executing" and data.get("node") is None:
                    break
            else:
                raise ComfyError("ComfyUI connection closed during generation")
        return await self._collect(prompt_id)

    async def _collect(self, prompt_id: str) -> list[bytes]:
        r = await self._http.get(f"/history/{prompt_id}")
        r.raise_for_status()
        outputs = r.json()[prompt_id]["outputs"]
        images: list[bytes] = []
        for node_output in outputs.values():
            for item in node_output.get("images", []):
                v = await self._http.get(
                    "/view", params={k: item[k] for k in ("filename", "subfolder", "type")}
                )
                v.raise_for_status()
                images.append(v.content)
        if not images:
            raise ComfyError("generation finished without images")
        return images
