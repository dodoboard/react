import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { ClipMeta } from "../types";
import { ErrorNote, ProgressBar } from "./ui";

const ACCEPT = {
  driver: "video/mp4,video/quicktime,video/webm,video/x-matroska,.mp4,.mov,.m4v,.webm,.mkv",
  music: "audio/*,.mp3,.wav,.m4a,.aac,.ogg,.flac,video/mp4,.mp4,.mov",
};

export function formatSeconds(s: number): string {
  const m = Math.floor(s / 60);
  return `${m}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
}

/** Upload + pick a dance reference clip or a music track. */
export function MediaLibrary(props: {
  kind: "driver" | "music";
  selected: ClipMeta | null;
  onSelect: (clip: ClipMeta | null) => void;
}) {
  const { kind, onSelect } = props;
  const [items, setItems] = useState<ClipMeta[]>([]);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const selectedRef = useRef(props.selected);
  selectedRef.current = props.selected;

  useEffect(() => {
    api.mediaUploads(kind).then(
      (list) => {
        setItems(list);
        if (list.length && !selectedRef.current) onSelect(list[0]);
      },
      (e: Error) => setError(e.message),
    );
  }, [kind, onSelect]);

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
    if (!window.confirm(`Delete ${clip.name}?`)) return;
    await api.deleteClip(clip.id);
    setItems((prev) => prev.filter((c) => c.id !== clip.id));
    if (props.selected?.id === clip.id) onSelect(null);
  };

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
        {progress !== null
          ? `Uploading… ${Math.round(progress * 100)}%`
          : kind === "driver"
            ? "Drop a dance video (MP4/MOV/WebM) or click to browse"
            : "Drop a song (MP3/WAV/M4A) or click to browse"}
      </button>
      {progress !== null && <ProgressBar value={progress} />}
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
      <ul className="media-list">
        {items.map((clip) => (
          <li key={clip.id} className={clip.id === props.selected?.id ? "is-active" : ""}>
            <button type="button" className="media-item" onClick={() => onSelect(clip)} aria-pressed={clip.id === props.selected?.id}>
              {kind === "driver" ? (
                <video src={`${clip.url}#t=0.5`} muted preload="metadata" playsInline />
              ) : (
                <span className="media-item__icon">♪</span>
              )}
              <span className="media-item__meta">
                <strong>{clip.name}</strong>
                <span className="muted small">
                  {formatSeconds(clip.duration)}
                  {clip.width ? ` · ${clip.width}×${clip.height}` : ""}
                  {kind === "driver" && clip.has_audio ? " · ♪" : ""}
                </span>
              </span>
            </button>
            <button type="button" className="icon-btn" aria-label={`Delete ${clip.name}`} onClick={() => remove(clip)}>
              ✕
            </button>
          </li>
        ))}
      </ul>
      {kind === "music" && props.selected && <audio className="media-preview" src={props.selected.url} controls preload="none" />}
    </div>
  );
}
