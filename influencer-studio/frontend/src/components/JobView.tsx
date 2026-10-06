import type { ReactNode } from "react";
import { useJob } from "../hooks";
import type { ImageMeta, Job } from "../types";
import { ImageTile } from "./ImageTile";
import { ErrorNote, ProgressBar } from "./ui";

function status(job: Job | null): string {
  if (!job) return "Submitting…";
  if (job.status === "queued") return job.queue_position ? `Queued · #${job.queue_position}` : "Queued";
  if (job.status === "running") return job.progress > 0 ? `Generating · ${Math.round(job.progress * 100)}%` : "Loading model…";
  return "";
}

/** Live view of one generation job: progress while running, then its images. */
export function JobView(props: {
  jobId: string;
  placeholders: number;
  aspect: number;
  onDone?: (job: Job) => void;
  onOpen: (image: ImageMeta) => void;
  actions?: (image: ImageMeta) => ReactNode;
  compact?: boolean;
}) {
  const job = useJob(props.jobId, props.onDone);
  const finished = job?.status === "done";

  return (
    <div className="job">
      {!finished && job?.status !== "error" && (
        <div className="job__status">
          <span>{status(job)}</span>
          <ProgressBar value={job?.progress ?? 0} />
        </div>
      )}
      {job?.status === "error" && <ErrorNote message={job.error} />}
      <div className={`grid${props.compact ? " grid--compact" : ""}`}>
        {finished
          ? job.images.map((img) => (
              <ImageTile key={img.id} image={img} onOpen={() => props.onOpen(img)} actions={props.actions?.(img)} />
            ))
          : job?.status !== "error" &&
            Array.from({ length: props.placeholders }, (_, i) => (
              <div key={i} className="tile tile--pending" style={{ aspectRatio: String(props.aspect) }} />
            ))}
      </div>
    </div>
  );
}
