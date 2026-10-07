import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { ImageTile } from "../components/ImageTile";
import { JobView } from "../components/JobView";
import { Lightbox } from "../components/Lightbox";
import { Chip, Empty, ErrorNote, Segmented } from "../components/ui";
import { useStudio } from "../hooks";
import type { Character, ImageMeta } from "../types";

interface ContentJob {
  id: string;
  count: number;
  aspect: string;
}

export function CreatePage({ characterId, navigate }: { characterId?: string; navigate: (path: string) => void }) {
  const { schema } = useStudio();
  const [characters, setCharacters] = useState<Character[] | null>(null);
  const [presetId, setPresetId] = useState<string | null>("coffee");
  const [prompt, setPrompt] = useState("");
  const [aspect, setAspect] = useState("4:5");
  const [count, setCount] = useState(2);
  const [jobs, setJobs] = useState<ContentJob[]>([]);
  const [recent, setRecent] = useState<ImageMeta[]>([]);
  const [shownInJobs, setShownInJobs] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [lightbox, setLightbox] = useState<ImageMeta | null>(null);

  useEffect(() => {
    api.characters().then(setCharacters, (e: Error) => setError(e.message));
  }, []);

  const selected = characters?.find((c) => c.id === characterId) ?? characters?.[0];
  const loadRecent = useCallback(() => {
    if (selected) api.character(selected.id).then((d) => setRecent(d.images.filter((i) => i.kind === "content")), () => {});
  }, [selected]);
  useEffect(() => {
    setJobs([]);
    loadRecent();
  }, [loadRecent]);

  const categories = useMemo(() => [...new Set(schema.presets.map((p) => p.category))], [schema]);
  const ratio = (key: string) => (schema.aspects[key] ? schema.aspects[key].width / schema.aspects[key].height : 1);

  if (characters?.length === 0) {
    return (
      <div className="page">
        <Empty title="No influencer yet">
          <a href="#/builder">Design one in the Builder</a> first, then come back to create content.
        </Empty>
      </div>
    );
  }

  const generate = async () => {
    if (!selected) return;
    setError(null);
    try {
      const job = await api.content(selected.id, { preset_id: presetId, prompt, count, aspect, seed: null });
      setJobs((prev) => [{ id: job.id, count, aspect }, ...prev]);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className="workspace">
      <aside className="panel">
        <div className="panel__scroll">
          <section className="card">
            <div className="card__title">Influencer</div>
            <div className="avatar-row">
              {characters?.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  className={`avatar${c.id === selected?.id ? " avatar--active" : ""}`}
                  onClick={() => navigate(`/create/${c.id}`)}
                  title={c.name}
                >
                  <img src={c.portrait_url} alt={c.name} />
                  <span>{c.name}</span>
                </button>
              ))}
            </div>
            {selected && (
              <p className="muted small">
                {selected.reference_ids.length} reference image{selected.reference_ids.length === 1 ? "" : "s"}
                {selected.lora ? ` · LoRA ${selected.lora}` : ""} ·{" "}
                <a href={`#/characters/${selected.id}`}>manage</a>
              </p>
            )}
          </section>

          <section className="card">
            <div className="card__title">Scene presets</div>
            {categories.map((cat) => (
              <div key={cat} className="field">
                <span className="field__label">{cat}</span>
                <div className="chips">
                  {schema.presets
                    .filter((p) => p.category === cat)
                    .map((p) => (
                      <Chip
                        key={p.id}
                        active={presetId === p.id}
                        onClick={() => {
                          setPresetId(presetId === p.id ? null : p.id);
                          if (presetId !== p.id) setAspect(p.aspect);
                        }}
                      >
                        {p.label}
                      </Chip>
                    ))}
                </div>
              </div>
            ))}
          </section>

          <section className="card">
            <label className="field">
              <span className="field__label">{presetId ? "Add details" : "Describe the scene"}</span>
              <textarea
                rows={3}
                maxLength={1000}
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder={presetId ? "e.g. wearing a beige trench coat" : "e.g. reading on a rooftop terrace in Galata at dusk"}
              />
            </label>
          </section>
        </div>
        <footer className="panel__footer">
          <div className="row row--between">
            <Segmented
              size="sm"
              label="Aspect ratio"
              value={aspect}
              options={Object.keys(schema.aspects).map((k) => ({ value: k, label: k }))}
              onChange={setAspect}
            />
            <Segmented
              size="sm"
              label="Images"
              value={count}
              options={[1, 2, 3, 4].map((n) => ({ value: n, label: `×${n}` }))}
              onChange={setCount}
            />
          </div>
          <ErrorNote message={error} />
          <button
            type="button"
            className="btn btn--primary btn--block"
            disabled={!selected || (!presetId && !prompt.trim())}
            onClick={generate}
          >
            Generate content
          </button>
        </footer>
      </aside>

      <main className="stage">
        {jobs.map((j) => (
          <JobView
            key={j.id}
            jobId={j.id}
            placeholders={j.count}
            aspect={ratio(j.aspect)}
            onOpen={setLightbox}
            onDone={(job) => {
              setShownInJobs((prev) => new Set([...prev, ...job.outputs.map((i) => i.id)]));
              loadRecent();
            }}
          />
        ))}
        <h2 className="stage__heading">Recent content{selected ? ` · ${selected.name}` : ""}</h2>
        {recent.length === 0 ? (
          <Empty title="No content yet">Pick a preset and generate. Each image reuses the character's reference images.</Empty>
        ) : (
          <div className="grid grid--gallery">
            {recent.filter((img) => !shownInJobs.has(img.id)).map((img) => (
              <ImageTile key={img.id} image={img} onOpen={() => setLightbox(img)} />
            ))}
          </div>
        )}
      </main>
      {lightbox && <Lightbox image={lightbox} onClose={() => setLightbox(null)} />}
    </div>
  );
}
