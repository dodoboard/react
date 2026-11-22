import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { Job } from "../types";
import { ProgressBar } from "./ui";

const KIND_LABEL: Record<string, string> = {
  builder: "Builder portraits",
  identity_pack: "Identity pack",
  content: "Content",
  face_fix: "Face detail",
  upscale_image: "Image upscale",
  dance: "Dance video",
  music_dance: "Music dance",
  motion: "Motion",
  speech: "Speech",
  talk: "Talking video",
  upscale_video: "Video HD",
  transcribe: "Speech recognition",
  export: "Export",
  batch: "Content pack",
  lora: "LoRA training",
};

export function jobLabel(kind: string): string {
  return KIND_LABEL[kind] ?? kind;
}

/** Stops a queued or running job (ComfyUI is interrupted mid-render). */
export function CancelJobButton({ job }: { job: Job<unknown> | null }) {
  const [sent, setSent] = useState(false);
  if (!job || (job.status !== "queued" && job.status !== "running")) return null;
  return (
    <button
      type="button"
      className="link-btn small"
      disabled={sent}
      onClick={() => {
        setSent(true);
        api.cancelJob(job.id).catch(() => setSent(false));
      }}
    >
      {sent ? "Cancelling…" : "Cancel"}
    </button>
  );
}

function when(seconds?: number): string {
  if (!seconds) return "";
  const minutes = Math.round((Date.now() / 1000 - seconds) / 60);
  return minutes < 1 ? "just now" : minutes < 60 ? `${minutes} min ago` : `${Math.round(minutes / 60)} h ago`;
}

/** Top-bar button with the number of unfinished jobs; opens the queue and recent history. */
export function QueuePanel() {
  const [jobs, setJobs] = useState<Job<unknown>[]>([]);
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let alive = true;
    const poll = () => api.jobs(15).then((list) => alive && setJobs(list), () => {});
    poll();
    const t = window.setInterval(poll, open ? 1500 : 4000);
    return () => {
      alive = false;
      window.clearInterval(t);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => box.current && !box.current.contains(e.target as Node) && setOpen(false);
    window.addEventListener("mousedown", close);
    return () => window.removeEventListener("mousedown", close);
  }, [open]);

  const active = jobs.filter((j) => j.status === "queued" || j.status === "running");
  return (
    <div className="queue" ref={box}>
      <button type="button" className={`queue__button${active.length ? " queue__button--busy" : ""}`} onClick={() => setOpen(!open)} aria-expanded={open}>
        {active.length ? `Queue · ${active.length}` : "Queue"}
      </button>
      {open && (
        <div className="queue__panel" role="dialog" aria-label="Job queue">
          {jobs.length === 0 && <p className="muted small">Nothing has run yet.</p>}
          <ul>
            {jobs.map((job) => (
              <li key={job.id} className={`queue__job queue__job--${job.status}`}>
                <div className="row row--between">
                  <strong>{jobLabel(job.kind)}</strong>
                  <span className="muted small">
                    {job.status === "queued"
                      ? job.queue_position
                        ? `#${job.queue_position} in line`
                        : "queued"
                      : job.status === "running"
                        ? `${Math.round(job.progress * 100)}%`
                        : `${job.status} · ${when(job.created_at)}`}
                  </span>
                </div>
                {job.status === "running" && <ProgressBar value={job.progress} />}
                {job.status === "error" && <span className="error-text small">{job.error}</span>}
                <CancelJobButton job={job} />
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
