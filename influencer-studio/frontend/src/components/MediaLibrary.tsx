import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { ClipMeta, MediaKind } from "../types";
import { ErrorNote, ProgressBar } from "./ui";

const VIDEO = "video/mp4,video/quicktime,video/webm,video/x-matroska,.mp4,.mov,.m4v,.webm,.mkv";
const AUDIO = "audio/*,.mp3,.wav,.m4a,.aac,.ogg,.opus,.flac,video/mp4,.mp4,.mov,.webm";
const ACCEPT: Record<MediaKind, string> = { driver: VIDEO, music: AUDIO, voice: AUDIO, speech: AUDIO };
const PROMPT: Record<MediaKind, string> = {
  driver: "Drop a dance video (MP4/MOV/WebM) or click to browse",
  music: "Drop a song (MP3/WAV/M4A) or click to browse",
  voice: "Drop a clean voice sample (10–15 s) or click to browse",
  speech: "Drop a voice-over (up to 30 s) or click to browse",
};
const ICON: Record<MediaKind, string> = { driver: "▶", music: "♪", voice: "◉", speech: "❞" };
// Opus first: every format here is accepted by the backend and decoded by PyAV.
const RECORDING_TYPES = ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/mp4"];

export function formatSeconds(s: number): string {
  const m = Math.floor(s / 60);
  return `${m}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
}

function recordingExt(mimeType: string): string {
  return mimeType.includes("mp4") ? "m4a" : mimeType.includes("ogg") ? "ogg" : "webm";
}

/** Microphone capture with MediaRecorder; hands back a File ready for upload. */
function MicRecorder(props: {
  maxSeconds: number;
  disabled: boolean;
  onRecorded: (file: File) => void;
  onError: (message: string) => void;
}) {
  const [elapsed, setElapsed] = useState<number | null>(null); // null: not recording
  const session = useRef<{ recorder: MediaRecorder; stream: MediaStream; timer: number } | null>(null);

  useEffect(
    () => () => {
      // unmounted mid-recording: release the mic and drop the take
      const s = session.current;
      if (!s) return;
      s.recorder.onstop = null;
      if (s.recorder.state !== "inactive") s.recorder.stop();
      s.stream.getTracks().forEach((t) => t.stop());
      window.clearInterval(s.timer);
    },
    [],
  );

  const stop = () => {
    const recorder = session.current?.recorder;
    if (recorder?.state === "recording") recorder.stop();
  };

  const start = async () => {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      props.onError("This browser can't record here. Open the studio at http://127.0.0.1 or localhost.");
      return;
    }
    let stream: MediaStream;
    try {
      // raw signal: noise suppression makes cloned voices sound processed
      stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: false } });
    } catch (e) {
      props.onError(`Microphone unavailable: ${(e as Error).message}`);
      return;
    }
    const mimeType = RECORDING_TYPES.find((t) => MediaRecorder.isTypeSupported(t));
    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    const chunks: Blob[] = [];
    const began = performance.now();
    const timer = window.setInterval(() => {
      const seconds = (performance.now() - began) / 1000;
      setElapsed(seconds);
      if (seconds >= props.maxSeconds) stop();
    }, 200);
    recorder.ondataavailable = (e) => e.data.size > 0 && chunks.push(e.data);
    recorder.onstop = () => {
      stream.getTracks().forEach((t) => t.stop());
      window.clearInterval(timer);
      session.current = null;
      setElapsed(null);
      const type = recorder.mimeType || mimeType || "audio/webm";
      const stamp = new Date().toISOString().slice(0, 19).replace(/[T:]/g, "-");
      props.onRecorded(new File(chunks, `recording-${stamp}.${recordingExt(type)}`, { type }));
    };
    session.current = { recorder, stream, timer };
    recorder.start(1000);
    setElapsed(0);
  };

  const recording = elapsed !== null;
  return (
    <button
      type="button"
      className={`btn btn--ghost record-btn${recording ? " is-recording" : ""}`}
      disabled={props.disabled && !recording}
      onClick={recording ? stop : start}
    >
      {recording ? `■ Stop · ${formatSeconds(elapsed)} / ${formatSeconds(props.maxSeconds)}` : "● Record with microphone"}
    </button>
  );
}

/** Upload, record and pick media: dance clips, songs, voice samples and voice-overs. */
export function MediaLibrary(props: {
  kind: MediaKind;
  selectedId: string | null;
  onSelect: (clip: ClipMeta | null) => void;
  /** Pick the newest item when nothing is selected (default true). */
  autoSelect?: boolean;
  /** Only uploads plus this character's generated clips. */
  characterId?: string;
  /** Offer microphone recording up to this many seconds. */
  recordSeconds?: number;
  /** Bump to reload the list (e.g. after a speech job finished). */
  refreshKey?: number;
}) {
  const { kind, onSelect, autoSelect = true, characterId, refreshKey } = props;
  const [items, setItems] = useState<ClipMeta[]>([]);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const selectedRef = useRef(props.selectedId);
  selectedRef.current = props.selectedId;

  useEffect(() => {
    api.mediaUploads(kind).then(
      (all) => {
        const list = all.filter((c) => !characterId || !c.character_id || c.character_id === characterId);
        setItems(list);
        if (autoSelect && list.length && !list.some((c) => c.id === selectedRef.current)) onSelect(list[0]);
      },
      (e: Error) => setError(e.message),
    );
  }, [kind, onSelect, autoSelect, characterId, refreshKey]);

  const upload = async (file: File | undefined) => {
    if (!file) return;
    setError(null);
    setProgress(0);
    try {
      const clip = await api.uploadMedia(kind, file, setProgress);
      setItems((prev) => [clip, ...prev]);
      onSelect(clip);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setProgress(null);
    }
  };

  const remove = async (clip: ClipMeta) => {
    if (!window.confirm(`Delete ${clip.caption || clip.name}?`)) return;
    try {
      await api.deleteClip(clip.id);
      setItems((prev) => prev.filter((c) => c.id !== clip.id));
      if (props.selectedId === clip.id) onSelect(null);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const selected = items.find((c) => c.id === props.selectedId);
  return (
    <div className="media-library">
      <button
        type="button"
        className="dropzone"
        disabled={progress !== null}
        onClick={() => input.current?.click()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          upload(e.dataTransfer.files[0]);
        }}
      >
        {progress !== null ? `Uploading… ${Math.round(progress * 100)}%` : PROMPT[kind]}
      </button>
      {progress !== null && <ProgressBar value={progress} />}
      {props.recordSeconds && (
        <MicRecorder maxSeconds={props.recordSeconds} disabled={progress !== null} onRecorded={upload} onError={setError} />
      )}
      <input
        ref={input}
        type="file"
        hidden
        accept={ACCEPT[kind]}
        onChange={(e) => {
          upload(e.target.files?.[0]);
          e.target.value = "";
        }}
      />
      <ErrorNote message={error} />
      {items.length > 0 && (
        <ul className="media-list">
          {items.map((clip) => (
            <li key={clip.id} className={clip.id === props.selectedId ? "is-active" : ""}>
              <button type="button" className="media-item" onClick={() => onSelect(clip)} aria-pressed={clip.id === props.selectedId}>
                {kind === "driver" ? (
                  <video src={`${clip.url}#t=0.5`} muted preload="metadata" playsInline />
                ) : (
                  <span className="media-item__icon">{ICON[kind]}</span>
                )}
                <span className="media-item__meta">
                  <strong title={clip.caption || clip.name}>{clip.caption || clip.name}</strong>
                  <span className="muted small">
                    {formatSeconds(clip.duration)}
                    {clip.width ? ` · ${clip.width}×${clip.height}` : ""}
                    {kind === "driver" && clip.has_audio ? " · ♪" : ""}
                    {kind === "speech" && clip.character_id ? " · generated" : ""}
                  </span>
                </span>
              </button>
              <button type="button" className="icon-btn" aria-label={`Delete ${clip.caption || clip.name}`} onClick={() => remove(clip)}>
                ✕
              </button>
            </li>
          ))}
        </ul>
      )}
      {kind !== "driver" && selected && <audio key={selected.id} className="media-preview" src={selected.url} controls preload="none" />}
    </div>
  );
}
