"""One GPU: ad and documentary pipelines take turns on LLM / TTS / ComfyUI stages."""
from __future__ import annotations

import asyncio
import weakref

_locks: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock]" = weakref.WeakKeyDictionary()


def gpu_lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    lock = _locks.get(loop)
    if lock is None:
        lock = _locks[loop] = asyncio.Lock()
    return lock
