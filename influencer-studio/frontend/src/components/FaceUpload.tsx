import { useRef, useState } from "react";
import { api } from "../api";
import type { ImageMeta } from "../types";
import { ErrorNote } from "./ui";

export function FaceUpload(props: {
  face: ImageMeta | null;
  consent: boolean;
  onFace: (face: ImageMeta | null) => void;
  onConsent: (v: boolean) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  const upload = async (file: File | undefined) => {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      props.onFace(await api.upload(file));
      props.onConsent(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const isUpload = props.face?.kind === "upload";

  return (
    <section className="card face-upload">
      <div className="card__title">
        <span>Add your face</span>
        <span className="muted">optional</span>
      </div>
      {props.face ? (
        <div className="face-upload__selected">
          <img src={props.face.url} alt="Face reference" />
          <div>
            <p className="muted small">
              {isUpload ? "Identity is kept while everything else follows your settings." : "Iterating on a generated face."}
            </p>
            {isUpload && (
              <label className="checkbox">
                <input type="checkbox" checked={props.consent} onChange={(e) => props.onConsent(e.target.checked)} />
                <span>This is me, or I have the person's permission to use their face.</span>
              </label>
            )}
            <button type="button" className="btn btn--ghost btn--sm" onClick={() => props.onFace(null)}>
              Remove
            </button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          className={`dropzone${dragging ? " dropzone--over" : ""}`}
          onClick={() => input.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            upload(e.dataTransfer.files[0]);
          }}
          disabled={busy}
        >
          {busy ? "Uploading…" : "Drop a clear, front-facing photo or click to browse"}
        </button>
      )}
      <input
        ref={input}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        hidden
        onChange={(e) => {
          upload(e.target.files?.[0]);
          e.target.value = "";
        }}
      />
      <ErrorNote message={error} />
    </section>
  );
}
