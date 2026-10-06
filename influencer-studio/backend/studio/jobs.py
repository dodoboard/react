"""Single-worker job queue: the GPU runs one generation at a time."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Literal

log = logging.getLogger(__name__)

Status = Literal["queued", "running", "done", "error"]


@dataclass
class Job:
    kind: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: Status = "queued"
    progress: float = 0.0
    images: list[dict] = field(default_factory=list)
    error: str | None = None
    created_at: float = field(default_factory=time.time)

    def public(self, position: int | None = None) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "progress": round(self.progress, 3),
            "images": self.images,
            "error": self.error,
            "queue_position": position,
        }


JobFn = Callable[[Job], Awaitable[list[dict]]]


class JobQueue:
    def __init__(self, max_history: int = 200):
        self._jobs: dict[str, Job] = {}
        self._queue: asyncio.Queue[tuple[Job, JobFn]] = asyncio.Queue()
        self._max_history = max_history

    def submit(self, kind: str, fn: JobFn) -> Job:
        job = Job(kind=kind)
        self._jobs[job.id] = job
        self._queue.put_nowait((job, fn))
        self._prune()
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def position(self, job: Job) -> int | None:
        if job.status != "queued":
            return None
        queued = [j for j in self._jobs.values() if j.status == "queued"]
        return queued.index(job) + 1

    async def run_forever(self) -> None:
        while True:
            job, fn = await self._queue.get()
            job.status = "running"
            try:
                job.images = await fn(job)
                job.status = "done"
            except Exception as e:  # surfaced to the UI
                log.exception("job %s failed", job.id)
                job.status, job.error = "error", str(e) or type(e).__name__
            finally:
                job.progress = 1.0
                self._queue.task_done()

    def _prune(self) -> None:
        finished = [j for j in self._jobs.values() if j.status in ("done", "error")]
        for j in finished[: max(0, len(self._jobs) - self._max_history)]:
            del self._jobs[j.id]
