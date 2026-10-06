import type { ImageMeta } from "../types";
import { Modal } from "./ui";

export function Lightbox({ image, onClose }: { image: ImageMeta; onClose: () => void }) {
  return (
    <Modal title={image.caption || "Image"} onClose={onClose} wide>
      <div className="lightbox">
        <img src={image.url} alt={image.caption || "Generated image"} />
        <aside>
          <dl className="meta">
            <dt>Size</dt>
            <dd>
              {image.width}×{image.height}
            </dd>
            {image.seed !== null && (
              <>
                <dt>Seed</dt>
                <dd>{image.seed}</dd>
              </>
            )}
            <dt>Type</dt>
            <dd>{image.kind}</dd>
          </dl>
          {image.prompt && (
            <details>
              <summary>Prompt</summary>
              <p className="prompt-text">{image.prompt}</p>
            </details>
          )}
          <a className="btn btn--ghost" href={image.url} download={`${image.id}.png`}>
            Download PNG
          </a>
        </aside>
      </div>
    </Modal>
  );
}
