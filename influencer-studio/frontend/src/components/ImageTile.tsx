import type { ReactNode } from "react";
import type { ImageMeta } from "../types";

export function ImageTile(props: {
  image: ImageMeta;
  onOpen: () => void;
  actions?: ReactNode;
  badge?: ReactNode;
  selected?: boolean;
}) {
  const { image } = props;
  return (
    <figure className={`tile${props.selected ? " tile--selected" : ""}`}>
      <button type="button" className="tile__open" onClick={props.onOpen} aria-label="Open image">
        <img
          src={image.url}
          alt={image.caption || "Generated image"}
          loading="lazy"
          style={{ aspectRatio: `${image.width} / ${image.height}` }}
        />
      </button>
      {props.badge && <span className="tile__badge">{props.badge}</span>}
      {props.actions && <figcaption className="tile__actions">{props.actions}</figcaption>}
    </figure>
  );
}
