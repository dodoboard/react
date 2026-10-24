"""Single-worker job queue: the GPU runs one generation at a time.

Jobs carry a model group ("flux2", "wan-animate", "talk"…). The next job is taken from the group
that just ran when one is waiting, so ComfyUI keeps its models loaded instead of swapping 10–20 GB
of weights between every job. A job passed over MAX_SKIPS times runs next regardless.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Literal

log = logging.getLogger(__name__)

Status = Literal["queued", "running", "done", "error"]
MAX_SKIPS = 2


@dataclass
class Job:
    kind: str
    group: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: Status = "queued"
    progress: float = 0.0
    outputs: list[dict] = field(default_factory=list)  # saved images or clips
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    skipped: int = 0

    def public(self, position: int | None = None) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "progress": round(self.progress, 3),
            "outputs": self.outputs,
            "error": self.error,
            "queue_position": position,
        }


JobFn = Callable[[Job], Awaitable[list[dict]]]


def _pick(pending: list[tuple[str, int]], last_group: str | None) -> int:
    """Index of the job to run next, from each waiting job's (group, times skipped)."""
    for i, (_, skipped) in enumerate(pending):
        if skipped >= MAX_SKIPS:
            return i
    for i, (group, _) in enumerate(pending):
        if group == last_group:
            return i
    return 0


class JobQueue:
    def __init__(self, max_history: int = 200):
        self._jobs: dict[str, Job] = {}
        self._pending: list[tuple[Job, JobFn]] = []
        self._wake = asyncio.Event()
        self._last_group: str | None = None
        self._max_history = max_history

    def submit(self, kind: str, fn: JobFn, group: str | None = None) -> Job:
        job = Job(kind=kind, group=group or kind)
        self._jobs[job.id] = job
        self._pending.append((job, fn))
        self._wake.set()
        self._prune()
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def position(self, job: Job) -> int | None:
        """1-based place in the run order, simulating the group-aware picks."""
        if job.status != "queued":
            return None
        order = [[j, j.skipped] for j, _ in self._pending]
        last = self._last_group
        for n in range(1, len(order) + 1):
            i = _pick([(j.group, skipped) for j, skipped in order], last)
            for entry in order[:i]:
                entry[1] += 1
            chosen = order.pop(i)[0]
            if chosen is job:
                return n
            last = chosen.group
        return None

    def next(self) -> tuple[Job, JobFn]:
        i = _pick([(j.group, j.skipped) for j, _ in self._pending], self._last_group)
        for job, _ in self._pending[:i]:
            job.skipped += 1
        job, fn = self._pending.pop(i)
        self._last_group = job.group
        return job, fn

    async def run_forever(self) -> None:
        while True:
            while not self._pending:
                self._wake.clear()
                await self._wake.wait()
            job, fn = self.next()
            job.status = "running"
            try:
                job.outputs = await fn(job)
                job.status = "done"
            except Exception as e:  # surfaced to the UI
                log.exception("job %s failed", job.id)
                job.status, job.error = "error", str(e) or type(e).__name__
            finally:
                job.progress = 1.0

    def _prune(self) -> None:
        finished = [j for j in self._jobs.values() if j.status in ("done", "error")]
        for j in finished[: max(0, len(self._jobs) - self._max_history)]:
            del self._jobs[j.id]
