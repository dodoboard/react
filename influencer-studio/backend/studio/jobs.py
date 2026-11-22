"""Single-worker job queue: the GPU runs one generation at a time.

Jobs carry a model group ("flux2", "wan-animate", "talk"…). The next job is taken from the group
that just ran when one is waiting, so ComfyUI keeps its models loaded instead of swapping 10–20 GB
of weights between every job. A job passed over MAX_SKIPS times runs next regardless.

Status changes are handed to `persist` (the SQLite store), so finished jobs survive a restart and
the UI can list recent work. A running job can be cancelled: its task is cancelled and `interrupt`
stops whatever ComfyUI is rendering for it.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal

log = logging.getLogger(__name__)

Status = Literal["queued", "running", "done", "error", "cancelled"]
FINISHED = ("done", "error", "cancelled")
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
            "created_at": self.created_at,
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
    def __init__(self, max_history: int = 200, persist: Callable[[Job], Any] | None = None,
                 interrupt: Callable[[], Awaitable[Any]] | None = None):
        self._jobs: dict[str, Job] = {}
        self._pending: list[tuple[Job, JobFn]] = []
        self._wake = asyncio.Event()
        self._last_group: str | None = None
        self._max_history = max_history
        self._persist = persist or (lambda job: None)
        self.interrupt = interrupt  # set after construction when the ComfyUI client exists
        self._running: tuple[Job, asyncio.Task] | None = None
        self._listeners: list[Callable[[Job], Any]] = []

    def on_finish(self, listener: Callable[[Job], Any]) -> None:
        """Call `listener(job)` whenever a job ends (done, error or cancelled)."""
        self._listeners.append(listener)

    def submit(self, kind: str, fn: JobFn, group: str | None = None) -> Job:
        job = Job(kind=kind, group=group or kind)
        self._jobs[job.id] = job
        self._pending.append((job, fn))
        self._save(job)
        self._wake.set()
        self._prune()
        return job

    def _save(self, job: Job) -> None:
        try:
            self._persist(job)
        except Exception:  # history is a convenience: never fail a job over it
            log.exception("could not store job %s", job.id)

    def active(self) -> list[Job]:
        return [j for j in self._jobs.values() if j.status not in FINISHED]

    async def cancel(self, job_id: str) -> Job | None:
        job = self._jobs.get(job_id)
        if job is None or job.status in FINISHED:
            return job
        for i, (queued, _) in enumerate(self._pending):
            if queued is job:
                del self._pending[i]
                self._finish(job, "cancelled", "cancelled")
                return job
        if self._running and self._running[0] is job:
            self._running[1].cancel()
            if self.interrupt:
                try:
                    await self.interrupt()
                except Exception:
                    log.exception("could not interrupt ComfyUI")
        return job

    def _finish(self, job: Job, status: Status, error: str | None = None) -> None:
        job.status, job.error, job.progress = status, error, 1.0 if status == "done" else job.progress
        self._save(job)
        for listener in self._listeners:
            try:
                listener(job)
            except Exception:
                log.exception("job listener failed for %s", job.id)

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
            self._save(job)
            task = asyncio.create_task(fn(job))
            self._running = (job, task)
            try:
                job.outputs = await task
                self._finish(job, "done")
            except asyncio.CancelledError:
                if not task.cancelled():  # the worker itself is shutting down
                    raise
                self._finish(job, "cancelled", "cancelled")
            except Exception as e:  # surfaced to the UI
                log.exception("job %s failed", job.id)
                self._finish(job, "error", str(e) or type(e).__name__)
            finally:
                self._running = None

    def _prune(self) -> None:
        finished = [j for j in self._jobs.values() if j.status in FINISHED]
        for j in finished[: max(0, len(self._jobs) - self._max_history)]:
            del self._jobs[j.id]
