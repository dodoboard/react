"""Content packs: a week of posts in one go.

A pack turns into ordinary jobs (content images, talking videos and, for each finished talking
video, a captioned export), so they share the queue, its model grouping and cancellation.
Exports are submitted when their talking video finishes; one failed job does not stop the rest.
"""

from __future__ import annotations

import io
import zipfile

from .export import ExportStudio
from .jobs import Job, JobQueue
from .models import BatchRequest, ExportItem, ExportRequest, TalkRequest
from .scripts_tr import TEMPLATE_BY_ID, render
from .service import Invalid, NotFound, Studio
from .store import Store
from .voice import VoiceStudio


class BatchStudio:
    def __init__(self, store: Store, jobs: JobQueue, studio: Studio, voice: VoiceStudio, exporter: ExportStudio):
        self.store, self.jobs, self.studio, self.voice, self.exporter = store, jobs, studio, voice, exporter
        self._exports: dict[str, tuple[str, str, BatchRequest]] = {}  # talk job → (batch, character, request)
        jobs.on_finish(self._finished)

    def _talks(self, character: dict, req: BatchRequest) -> list[tuple[str, TalkRequest]]:
        talks = []
        for i, t in enumerate(req.talks, start=1):
            if t.template_id:
                if t.template_id not in TEMPLATE_BY_ID:
                    raise Invalid(f"unknown script template {t.template_id}")
                try:
                    text = render(t.template_id, t.values)
                except ValueError as e:
                    raise Invalid(f"talking video {i}: {e}") from e
                prompt = t.prompt or TEMPLATE_BY_ID[t.template_id].prompt
            else:
                text, prompt = t.text, t.prompt
            if not text.strip():
                raise Invalid(f"talking video {i}: write a script or pick a template")
            label = (text[:57] + "…") if len(text) > 60 else text
            talks.append((label, TalkRequest(source_image_id=t.source_image_id or character["portrait_id"], text=text,
                                             prompt=prompt, orientation="portrait")))
        return talks

    def create(self, character_id: str, req: BatchRequest) -> dict:
        character = self.store.character(character_id)
        if not character:
            raise NotFound(f"character {character_id} not found")
        talks = self._talks(character, req)  # validate everything before queueing anything
        entries = []
        for post in req.posts:
            job = self.studio.generate_content(character_id, post)
            entries.append({"job_id": job.id, "role": "post", "label": post.preset_id or post.prompt[:60]})
        talk_jobs = []
        for label, talk in talks:
            job = self.voice.talk(character_id, talk)
            entries.append({"job_id": job.id, "role": "talk", "label": label})
            talk_jobs.append(job)
        batch_id = self.store.create_batch(character_id, entries)
        if req.export:  # jobs only start once this request returns, so none has finished yet
            for job in talk_jobs:
                self._exports[job.id] = (batch_id, character_id, req)
        return self.view(batch_id)

    def _finished(self, job: Job) -> None:
        pending = self._exports.pop(job.id, None)
        if pending is None or job.status != "done" or not job.outputs:
            return
        batch_id, character_id, req = pending
        export = self.exporter.export(ExportRequest(character_id=character_id, format=req.format, hd=req.hd,
                                                    items=[ExportItem(clip_id=job.outputs[0]["id"])]))
        self.store.add_batch_job(batch_id, {"job_id": export.id, "role": "export", "label": job.outputs[0]["caption"]})

    def _job(self, job_id: str) -> dict:
        if job := self.jobs.get(job_id):
            return job.public(self.jobs.position(job))
        return self.store.job(job_id) or {"id": job_id, "status": "error", "error": "unknown job", "outputs": [],
                                          "progress": 0, "kind": "", "queue_position": None}

    def view(self, batch_id: str) -> dict:
        batch = self.store.batch(batch_id)
        if not batch:
            raise NotFound(f"batch {batch_id} not found")
        jobs = [{**entry, "job": self._job(entry["job_id"])} for entry in batch["jobs"]]
        done = sum(j["job"]["status"] in ("done", "error", "cancelled") for j in jobs)
        waiting_exports = sum(1 for _, (b, _, _) in self._exports.items() if b == batch_id)
        return {"id": batch_id, "character_id": batch["character_id"], "created_at": batch["created_at"],
                "jobs": jobs, "finished": done == len(jobs) and not waiting_exports,
                "progress": done / max(1, len(jobs) + waiting_exports)}

    def list(self, character_id: str) -> list[dict]:
        return [self.view(b["id"]) for b in self.store.batches(character_id)]

    def zip(self, batch_id: str) -> tuple[str, bytes]:
        """Every finished output of the pack: images, talking videos and exports."""
        batch = self.view(batch_id)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:  # PNG/MP4 are compressed already
            n = 0
            for entry in batch["jobs"]:
                for out in entry["job"]["outputs"]:
                    n += 1
                    if "ext" in out:  # a clip
                        clip = self.store.clip(out["id"])
                        if clip:
                            zf.write(self.store.clip_path(clip), f"{n:02}_{entry['role']}_{out['id']}.{clip['ext']}")
                    elif self.store.image(out["id"]):
                        zf.write(self.store.image_path(out["id"]), f"{n:02}_{entry['role']}_{out['id']}.png")
        return f"pack_{batch_id}.zip", buf.getvalue()
