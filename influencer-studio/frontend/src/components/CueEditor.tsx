import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { useJob } from "../hooks";
import type { ClipMeta, Cue, CuesResponse, Option } from "../types";
import { ErrorNote, ProgressBar } from "./ui";

const SOURCE_LABEL: Record<string, string> = {
  script: "from the script",
  recognized: "recognized",
  edited: "edited",
};

function stamp(s: number): string {
  return `${Math.floor(s / 60)}:${(s % 60).toFixed(1).padStart(4, "0")}`;
}

function TranscribeStatus({ jobId, onDone }: { jobId: string; onDone: () => void }) {
  const job = useJob(jobId, onDone);
  if (job?.status === "error") return <ErrorNote message={job.error} />;
  return (
    <div className="job__status">
      <span>{job?.status === "running" ? "Recognizing speech…" : "Queued…"}</span>
      <ProgressBar value={job?.progress ?? 0} />
    </div>
  );
}

/** Subtitle status of one clip: recognize speech when there is no script, fix the words by hand. */
export function CueEditor({ clip, languages }: { clip: ClipMeta; languages: Option[] }) {
  const [data, setData] = useState<CuesResponse | null>(null);
  const [draft, setDraft] = useState<Cue[] | null>(null);
  const [language, setLanguage] = useState("tr");
  const [job, setJob] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api.cues(clip.id).then(setData, (e: Error) => setError(e.message));
  }, [clip.id]);
  useEffect(load, [load]);

  const transcribe = async () => {
    setError(null);
    try {
      setJob((await api.transcribe(clip.id, language === "auto" ? null : language)).id);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const save = async (cues: Cue[]) => {
    setError(null);
    try {
      setData(await api.saveCues(clip.id, cues.map(({ start, end, text }) => ({ start, end, text }))));
      setDraft(null);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  if (!data) return error ? <ErrorNote message={error} /> : null;
  return (
    <div className="cue-editor">
      <div className="row row--between">
        <span className="muted small">
          {data.cues.length ? `${data.cues.length} captions · ${SOURCE_LABEL[data.source ?? ""] ?? ""}` : "No captions yet"}
        </span>
        <span className="row">
          {clip.has_audio && !data.scripted && !job && (
            <>
              <select className="select--sm" aria-label="Speech language" value={language} onChange={(e) => setLanguage(e.target.value)}>
                <option value="auto">Auto</option>
                {languages.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.label}
                  </option>
                ))}
              </select>
              <button type="button" className="btn btn--ghost btn--sm" onClick={transcribe}>
                {data.source === "recognized" ? "Recognize again" : "Recognize speech"}
              </button>
            </>
          )}
          {data.cues.length > 0 && !draft && (
            <button type="button" className="btn btn--ghost btn--sm" onClick={() => setDraft(data.cues)}>
              Edit text
            </button>
          )}
        </span>
      </div>
      {job && (
        <TranscribeStatus
          jobId={job}
          onDone={() => {
            setJob(null);
            load();
          }}
        />
      )}
      {draft && (
        <>
          <ol className="cue-list">
            {draft.map((cue, i) => (
              <li key={`${cue.start}-${i}`}>
                <span className="muted small">{stamp(cue.start)}</span>
                <input
                  aria-label={`Caption ${i + 1}`}
                  value={cue.text}
                  maxLength={200}
                  onChange={(e) => setDraft(draft.map((c, j) => (j === i ? { ...c, text: e.target.value } : c)))}
                />
              </li>
            ))}
          </ol>
          <div className="row">
            <button type="button" className="btn btn--primary btn--sm" onClick={() => save(draft)}>
              Save captions
            </button>
            <button type="button" className="btn btn--ghost btn--sm" onClick={() => setDraft(null)}>
              Cancel
            </button>
            {data.source === "edited" && (
              <button type="button" className="btn btn--ghost btn--sm" onClick={() => save([])}>
                Undo all edits
              </button>
            )}
          </div>
        </>
      )}
      <ErrorNote message={error} />
    </div>
  );
}
