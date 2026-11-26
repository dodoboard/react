"""In-process pub/sub for SSE."""
from __future__ import annotations

import asyncio
import json
from typing import Any


class Broker:
    def __init__(self) -> None:
        self._subs: set[asyncio.Queue[str]] = set()

    def subscribe(self) -> asyncio.Queue[str]:
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=500)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[str]) -> None:
        self._subs.discard(q)

    def publish(self, kind: str, data: Any) -> None:
        msg = json.dumps({"type": kind, "data": data}, default=str, ensure_ascii=False)
        for q in list(self._subs):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                self._subs.discard(q)


broker = Broker()
