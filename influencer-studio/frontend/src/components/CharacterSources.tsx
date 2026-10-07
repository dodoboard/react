import type { Character, ImageMeta, Orientation } from "../types";

/** Avatar row to switch influencers; navigates so the choice lives in the URL. */
export function CharacterPicker(props: { characters: Character[]; selectedId?: string; onPick: (id: string) => void }) {
  return (
    <div className="avatar-row">
      {props.characters.map((c) => (
        <button
          key={c.id}
          type="button"
          className={`avatar${c.id === props.selectedId ? " avatar--active" : ""}`}
          onClick={() => props.onPick(c.id)}
          title={c.name}
        >
          <img src={c.portrait_url} alt={c.name} />
          <span>{c.name}</span>
        </button>
      ))}
    </div>
  );
}

/** Pick the start frame (one of the character's reference or content images). */
export function SourcePicker(props: { images: ImageMeta[]; selectedId: string | null; onPick: (id: string) => void }) {
  return (
    <div className="source-row">
      {props.images.map((img) => (
        <button
          key={img.id}
          type="button"
          className={`source${img.id === props.selectedId ? " source--active" : ""}`}
          onClick={() => props.onPick(img.id)}
          aria-pressed={img.id === props.selectedId}
          title={img.caption}
        >
          <img src={img.url} alt={img.caption || "Character image"} loading="lazy" />
        </button>
      ))}
    </div>
  );
}

export function sourceImages(images: ImageMeta[] | undefined): ImageMeta[] {
  return (images ?? []).filter((i) => i.kind === "content" || i.kind === "reference");
}

/** Mirrors the backend: "auto" follows the start frame's shape. */
export function resolveOrientation(orientation: Orientation, width: number, height: number): Exclude<Orientation, "auto"> {
  if (orientation !== "auto") return orientation;
  const r = height ? width / height : 1;
  return r > 1.15 ? "landscape" : r < 0.87 ? "portrait" : "square";
}
