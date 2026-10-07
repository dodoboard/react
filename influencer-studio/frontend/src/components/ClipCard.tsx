import type { ReactNode } from "react";
import { useJob } from "../hooks";
import type { ClipMeta, Job } from "../types";
import { ErrorNote, ProgressBar } from "./ui";

const KIND_LABEL: Record<string, string> = { dance: "Dance", music_dance: "Music dance", motion: "Motion" };

export function ClipCard({ clip, actions }: { clip: ClipMeta; actions?: ReactNode }) {
  return (
    <figure className="clip">
      <video
        src={clip.url}
        controls
        loop
        playsInline
        preload="metadata"
        style={{ aspectRatio: clip.width && clip.height ? `${clip.width} / ${clip.height}` : undefined }}
      />
      <figcaption>
        <span className="clip__badge">{KIND_LABEL[clip.kind] ?? clip.kind}</span>
        <span className="clip__caption" title={clip.prompt}>
          {clip.caption}
        </span>
        <span className="muted small">
          {clip.duration.toFixed(1)}s · {Math.round(clip.fps)} fps{clip.has_audio ? " · ♪" : ""}
        </span>
        <span className="row">
          <a className="btn btn--ghost btn--sm" href={clip.url} download={`${clip.kind}-${clip.id}.mp4`}>
            Download
          </a>
          {actions}
        </span>
      </figcaption>
    </figure>
  );
}

function status(job: Job<ClipMeta> | null): string {
  if (!job) return "Submitting…";
  if (job.status === "queued") return job.queue_position ? `Queued · #${job.queue_position}` : "Queued";
  if (job.progress < 0.05) return "Preparing media…";
  if (job.progress >= 0.999) return "Encoding video…";
  return `Rendering · ${Math.round(job.progress * 100)}%`;
}

export function ClipJobView(props: { jobId: string; aspect: number; onDone?: (job: Job<ClipMeta>) => void }) {
  const job = useJob<ClipMeta>(props.jobId, props.onDone);
  if (job?.status === "done") return null; // the finished clip shows up in the gallery
  return (
    <div className="job">
      {job?.status === "error" ? (
        <ErrorNote message={job.error} />
      ) : (
        <div className="job__status">
          <span>{status(job)}</span>
          <ProgressBar value={job?.progress ?? 0} />
          <div className="tile tile--pending clip-pending" style={{ aspectRatio: String(props.aspect) }} />
        </div>
      )}
    </div>
  );
}
