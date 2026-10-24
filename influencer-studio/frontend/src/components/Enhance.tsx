import { useState } from "react";
import { api } from "../api";
import type { ClipMeta, ImageMeta, Job } from "../types";

export interface StartedJob {
  id: string;
  aspect: number;
}

/** "Fix face" and "Upscale" on an influencer's image; the new image arrives through the started job. */
export function ImageEnhanceActions(props: {
  image: ImageMeta;
  onJob: (job: StartedJob) => void;
  onError: (message: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const start = async (run: (id: string) => Promise<Job>) => {
    setBusy(true);
    try {
      const job = await run(props.image.id);
      props.onJob({ id: job.id, aspect: props.image.width / props.image.height });
    } catch (e) {
      props.onError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <button type="button" className="btn btn--ghost btn--sm" disabled={busy} onClick={() => start(api.faceFix)}
        title="Redraw the face at full resolution with the character's references">
        Fix face
      </button>
      <button type="button" className="btn btn--ghost btn--sm" disabled={busy} onClick={() => start(api.upscaleImage)}
        title="Real-ESRGAN, twice the resolution">
        Upscale ×2
      </button>
    </>
  );
}

export const HD_SHORT_SIDE = 1080;

export function canUpscale(clip: ClipMeta): boolean {
  return !clip.meta?.hd && Math.min(clip.width, clip.height) < HD_SHORT_SIDE && !clip.media_type.startsWith("audio/");
}

/** "HD 1080p" on a generated video; the HD copy arrives through the started job. */
export function ClipHdAction(props: { clip: ClipMeta; onJob: (job: StartedJob) => void; onError: (message: string) => void }) {
  const [busy, setBusy] = useState(false);
  if (!canUpscale(props.clip)) return null;
  return (
    <button
      type="button"
      className="btn btn--ghost btn--sm"
      disabled={busy}
      title="Real-ESRGAN upscale to 1080p, a few seconds at a time"
      onClick={async () => {
        setBusy(true);
        try {
          const job = await api.upscaleClip(props.clip.id);
          props.onJob({ id: job.id, aspect: props.clip.width / props.clip.height });
        } catch (e) {
          props.onError((e as Error).message);
        } finally {
          setBusy(false);
        }
      }}
    >
      HD 1080p
    </button>
  );
}
