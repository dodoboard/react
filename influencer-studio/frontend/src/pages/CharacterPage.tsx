import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type CharacterPatch } from "../api";
import { ImageTile } from "../components/ImageTile";
import { JobView } from "../components/JobView";
import { Lightbox } from "../components/Lightbox";
import { Chip, Empty, ErrorNote, Segmented } from "../components/ui";
import { useStudio } from "../hooks";
import type { CharacterDetail, ImageKind, ImageMeta } from "../types";

const DEFAULT_ANGLES = ["front", "three_quarter_left", "three_quarter_right", "smile"];
type Filter = "all" | Extract<ImageKind, "reference" | "content">;

export function CharacterPage({ id, navigate }: { id: string; navigate: (path: string) => void }) {
  const { schema } = useStudio();
  const [character, setCharacter] = useState<CharacterDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [angles, setAngles] = useState<string[]>(DEFAULT_ANGLES);
  const [packJob, setPackJob] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [lightbox, setLightbox] = useState<ImageMeta | null>(null);
  const [loras, setLoras] = useState<string[]>([]);

  const reload = useCallback(() => api.character(id).then(setCharacter, (e: Error) => setError(e.message)), [id]);
  useEffect(() => {
    reload();
    api.loras().then(setLoras, () => {});
  }, [reload]);

  const labels = useMemo(() => {
    const map = new Map<string, string>();
    for (const a of schema.attributes) for (const o of a.options) map.set(`${a.id}:${o.id}`, o.label);
    return map;
  }, [schema]);

  if (!character) return <div className="page">{error ? <ErrorNote message={error} /> : <p className="muted">Loading…</p>}</div>;

  const patch = async (body: CharacterPatch) => {
    setError(null);
    try {
      setCharacter(await api.updateCharacter(id, body));
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const refs = character.reference_ids;
  const toggleRef = (imageId: string) => {
    const next = refs.includes(imageId) ? refs.filter((r) => r !== imageId) : [...refs, imageId];
    if (next.length === 0) return setError("Keep at least one reference image.");
    if (next.length > schema.max_refs) return setError(`FLUX.2 uses up to ${schema.max_refs} references. Remove one first.`);
    patch({ reference_ids: next });
  };

  const removeImage = async (img: ImageMeta) => {
    if (!window.confirm("Delete this image?")) return;
    try {
      await api.deleteImage(img.id);
      reload();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const startPack = async () => {
    setError(null);
    try {
      setPackJob((await api.identityPack(id, angles)).id);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const shown = character.images.filter((i) => filter === "all" || i.kind === filter);
  const summary = Object.entries(character.spec.selections).flatMap(([attr, sel]) =>
    sel.values.map((v) => labels.get(`${attr}:${v}`) ?? v),
  );

  return (
    <div className="page">
      <header className="page__header">
        <a href="#/characters" className="muted">
          ← Influencers
        </a>
        <div className="row">
          <a className="btn btn--ghost" href={api.datasetUrl(id)} download>
            Export LoRA dataset
          </a>
          <button
            type="button"
            className="btn btn--ghost btn--danger"
            onClick={async () => {
              if (!window.confirm(`Delete ${character.name} and all of their images?`)) return;
              await api.deleteCharacter(id);
              navigate("/characters");
            }}
          >
            Delete
          </button>
          <a className="btn btn--ghost" href={`#/motion/${id}`}>
            Make it move
          </a>
          <a className="btn btn--primary" href={`#/create/${id}`}>
            Create content
          </a>
        </div>
      </header>
      <ErrorNote message={error} />

      <div className="character-layout">
        <aside className="character-side">
          <img className="portrait" src={character.portrait_url} alt={character.name} />
          <input
            className="name-input"
            aria-label="Name"
            defaultValue={character.name}
            maxLength={60}
            onBlur={(e) => e.target.value.trim() && e.target.value.trim() !== character.name && patch({ name: e.target.value.trim() })}
          />
          <p className="muted small">
            {character.spec.age} y/o · {summary.join(" · ")}
          </p>

          <section className="card">
            <div className="card__title">
              <span>Identity pack</span>
              <span className="muted small">multi-angle references</span>
            </div>
            <div className="chips">
              {schema.angles.map((a) => (
                <Chip
                  key={a.id}
                  active={angles.includes(a.id)}
                  onClick={() => setAngles(angles.includes(a.id) ? angles.filter((x) => x !== a.id) : [...angles, a.id])}
                >
                  {a.label}
                </Chip>
              ))}
            </div>
            <button type="button" className="btn btn--primary btn--block" disabled={!angles.length} onClick={startPack}>
              Generate {angles.length} angle{angles.length === 1 ? "" : "s"}
            </button>
            <p className="muted small">New angles land in the gallery. Mark the best ones with ★ to use them as references.</p>
            {packJob && (
              <JobView
                jobId={packJob}
                placeholders={angles.length}
                aspect={1}
                compact
                onOpen={setLightbox}
                onDone={() => reload()}
              />
            )}
          </section>

          <section className="card">
            <div className="card__title">
              <span>Character LoRA</span>
              <span className="muted small">optional</span>
            </div>
            <select value={character.lora} onChange={(e) => patch({ lora: e.target.value })} aria-label="LoRA file">
              <option value="">None (references only)</option>
              {[...new Set([character.lora, ...loras])].filter(Boolean).map((l) => (
                <option key={l} value={l}>
                  {l}
                </option>
              ))}
            </select>
            {character.lora && (
              <label className="field">
                <span className="field__label">
                  Strength <span className="accent">{character.lora_strength.toFixed(2)}</span>
                </span>
                <input
                  type="range"
                  min={0}
                  max={1.5}
                  step={0.05}
                  defaultValue={character.lora_strength}
                  onPointerUp={(e) => patch({ lora_strength: Number((e.target as HTMLInputElement).value) })}
                  onKeyUp={(e) => patch({ lora_strength: Number((e.target as HTMLInputElement).value) })}
                />
              </label>
            )}
          </section>
        </aside>

        <main>
          <section className="refs">
            <div className="card__title">
              <span>
                Consistency references {refs.length}/{schema.max_refs}
              </span>
              <span className="muted small">Fed to FLUX.2 as reference images on every generation</span>
            </div>
            <div className="refs__row">
              {refs.map((r) => {
                const img = character.images.find((i) => i.id === r);
                return img ? <img key={r} src={img.url} alt="Reference" onClick={() => setLightbox(img)} /> : null;
              })}
            </div>
          </section>

          <div className="row row--between gallery-head">
            <h2>Gallery</h2>
            <Segmented
              size="sm"
              label="Filter"
              value={filter}
              options={[
                { value: "all", label: "All" },
                { value: "reference", label: "References" },
                { value: "content", label: "Content" },
              ]}
              onChange={setFilter}
            />
          </div>
          {shown.length === 0 ? (
            <Empty title="Nothing here yet">Generate an identity pack or create content.</Empty>
          ) : (
            <div className="grid grid--gallery">
              {shown.map((img) => (
                <ImageTile
                  key={img.id}
                  image={img}
                  selected={refs.includes(img.id)}
                  badge={img.id === character.portrait_id ? "Portrait" : refs.includes(img.id) ? "★ Ref" : undefined}
                  onOpen={() => setLightbox(img)}
                  actions={
                    <>
                      <button type="button" className="btn btn--ghost btn--sm" onClick={() => toggleRef(img.id)}>
                        {refs.includes(img.id) ? "Unset reference" : "★ Reference"}
                      </button>
                      {img.id !== character.portrait_id && (
                        <button type="button" className="btn btn--ghost btn--sm btn--danger" onClick={() => removeImage(img)}>
                          Delete
                        </button>
                      )}
                    </>
                  }
                />
              ))}
            </div>
          )}
        </main>
      </div>
      {lightbox && <Lightbox image={lightbox} onClose={() => setLightbox(null)} />}
    </div>
  );
}
