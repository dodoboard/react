import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { useJob } from "../hooks";
import type { LoraStatus } from "../types";
import { CancelJobButton } from "./QueuePanel";
import { ErrorNote, ProgressBar } from "./ui";

function TrainingJob({ jobId, onDone }: { jobId: string; onDone: () => void }) {
  const job = useJob(jobId, onDone);
  if (job?.status === "error") return <ErrorNote message={job.error} />;
  if (job?.status === "cancelled") return <p className="muted small">Training cancelled.</p>;
  if (job?.status === "done") return <p className="muted small">Done: the LoRA is now used for this influencer.</p>;
  return (
    <div className="job__status">
      <span className="row row--between">
        {!job || job.status === "queued" ? "Queued…" : job.progress < 0.03 ? "Preparing dataset…" : `Training · ${Math.round(job.progress * 100)}%`}
        <CancelJobButton job={job} />
      </span>
      <ProgressBar value={job?.progress ?? 0} />
    </div>
  );
}

/** "Train LoRA" on the character page: ai-toolkit in the background, assigned when finished. */
export function LoraTraining({ characterId, onTrained }: { characterId: string; onTrained: () => void }) {
  const [status, setStatus] = useState<LoraStatus | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api.loraStatus(characterId).then(setStatus, () => {});
  }, [characterId]);
  useEffect(load, [load]);

  if (!status) return null;
  return (
    <div className="lora-train">
      <span className="muted small">
        Dataset: {status.images} images (min {status.min_images}) · trigger <code>{status.trigger}</code>
      </span>
      {status.problems.map((p) => (
        <span key={p} className="muted small">
          • {p}
        </span>
      ))}
      <button
        type="button"
        className="btn btn--ghost btn--block"
        disabled={!status.ready || !!jobId}
        onClick={async () => {
          setError(null);
          try {
            setJobId((await api.trainLora(characterId)).id);
          } catch (e) {
            setError((e as Error).message);
          }
        }}
      >
        Train LoRA (~1–2 h on a 16 GB GPU)
      </button>
      {jobId && (
        <TrainingJob
          jobId={jobId}
          onDone={() => {
            load();
            onTrained();
          }}
        />
      )}
      <ErrorNote message={error} />
    </div>
  );
}
