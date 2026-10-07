from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient

from studio.api import create_app
from studio.comfy import ComfyClient
from studio.settings import Settings
from studio.voice import TTSClient
from tests.fake_comfy import create_fake_comfy
from tests.fake_tts import create_fake_tts


@dataclass
class FakeComfy:
    url: str
    app: FastAPI

    @property
    def prompts(self) -> list[dict]:
        return self.app.state.prompts


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _serve(app: FastAPI) -> Iterator[str]:
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.01)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture
def fake_comfy() -> Iterator[FakeComfy]:
    app = create_fake_comfy()
    for url in _serve(app):
        yield FakeComfy(url, app)


@dataclass
class FakeTTS:
    url: str
    app: FastAPI

    @property
    def calls(self) -> list[dict]:
        return self.app.state.engine.calls


@pytest.fixture
def fake_tts() -> Iterator[FakeTTS]:
    app = create_fake_tts()
    for url in _serve(app):
        yield FakeTTS(url, app)


@pytest.fixture
def client(fake_comfy: FakeComfy, fake_tts: FakeTTS, tmp_path) -> Iterator[TestClient]:
    settings = Settings(comfy_url=fake_comfy.url, data_dir=tmp_path, profile="klein-4b",
                        frontend_dist=tmp_path / "none", tts_url=fake_tts.url)
    with TestClient(create_app(settings, ComfyClient(fake_comfy.url), TTSClient(fake_tts.url))) as c:
        yield c


def wait_job(client: TestClient, job: dict, timeout: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout
    while job["status"] in ("queued", "running"):
        assert time.monotonic() < deadline, f"job {job['id']} timed out"
        time.sleep(0.05)
        job = client.get(f"/api/jobs/{job['id']}").json()
    return job
