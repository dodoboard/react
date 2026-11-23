import { useRef, useState } from "react";
import { api } from "../api";
import type { ImageMeta } from "../types";
import { ErrorNote } from "./ui";

/** Optional product photo for UGC scenes; FLUX.2 gets it as the last reference image. */
export function ProductUpload({ product, onProduct }: { product: ImageMeta | null; onProduct: (p: ImageMeta | null) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const upload = async (file: File | undefined) => {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      onProduct(await api.upload(file));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="product-upload">
      {product ? (
        <div className="product-upload__item">
          <img src={product.url} alt="Product" />
          <span className="muted small">The product appears in the scene with its shape, colors and label.</span>
          <button type="button" className="icon-btn" aria-label="Remove product" onClick={() => onProduct(null)}>
            ✕
          </button>
        </div>
      ) : (
        <button
          type="button"
          className="dropzone"
          disabled={busy}
          onClick={() => input.current?.click()}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            upload(e.dataTransfer.files[0]);
          }}
        >
          {busy ? "Uploading…" : "Add a product photo (optional): clean shot, plain background"}
        </button>
      )}
      <input
        ref={input}
        type="file"
        hidden
        accept="image/png,image/jpeg,image/webp"
        onChange={(e) => {
          upload(e.target.files?.[0]);
          e.target.value = "";
        }}
      />
      <ErrorNote message={error} />
    </div>
  );
}
