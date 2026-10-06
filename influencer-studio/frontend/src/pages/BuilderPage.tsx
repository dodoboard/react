import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { AttributeField } from "../components/AttributeField";
import { FaceUpload } from "../components/FaceUpload";
import { JobView } from "../components/JobView";
import { Lightbox } from "../components/Lightbox";
import { ErrorNote, Modal, Segmented } from "../components/ui";
import { useDebounced, usePersistentState, useStudio } from "../hooks";
import type { CharacterSpec, GroupId, ImageMeta, Level, Schema, Selection } from "../types";

interface BuilderJob {
  id: string;
  count: number;
  aspect: string;
  spec: CharacterSpec;
}

const pick = <T,>(items: T[]): T => items[Math.floor(Math.random() * items.length)];

function defaultSpec(schema: Schema): CharacterSpec {
  const one = (v: string): Selection => ({ values: [v], level: "average" });
  return {
    age: schema.age.default,
    extra: "",
    selections: { character_type: one("human"), gender: one("woman"), render_style: one("photo") },
  };
}

/** Drops selections the current catalog no longer knows (saved drafts survive catalog edits). */
function sanitize(spec: CharacterSpec, schema: Schema): CharacterSpec {
  const selections: Record<string, Selection> = {};
  for (const a of schema.attributes) {
    const sel = spec.selections?.[a.id];
    const values = sel?.values?.filter((v) => a.options.some((o) => o.id === v)).slice(0, a.max_select) ?? [];
    if (values.length) selections[a.id] = { values, level: schema.levels.includes(sel!.level) ? sel!.level : "average" };
  }
  const age = Math.min(schema.age.max, Math.max(schema.age.min, Number(spec.age) || schema.age.default));
  return { selections, age, extra: typeof spec.extra === "string" ? spec.extra : "" };
}

function randomSpec(schema: Schema): CharacterSpec {
  const selections: Record<string, Selection> = {};
  const level = (): Level => (Math.random() < 0.7 ? "average" : pick<Level>(["notable", "extreme"]));
  for (const a of schema.attributes) {
    const ids = a.options.map((o) => o.id);
    if (a.id === "skin_details") continue;
    if (a.id === "character_type") selections[a.id] = { values: [Math.random() < 0.75 ? "human" : pick(ids)], level: "average" };
    else if (a.id === "render_style") selections[a.id] = { values: [Math.random() < 0.75 ? "photo" : pick(ids)], level: "average" };
    else if (a.group === "base" || Math.random() < 0.6) {
      const n = a.max_select > 1 ? Math.floor(Math.random() * 2) + 1 : 1;
      selections[a.id] = { values: [...ids].sort(() => Math.random() - 0.5).slice(0, n), level: level() };
    }
  }
  if (Math.random() < 0.4) selections.skin_details = { values: [pick(["freckles", "beauty_marks"])], level: "average" };
  return { selections, age: 18 + Math.floor(Math.random() * 30), extra: "" };
}

export function BuilderPage({ navigate }: { navigate: (path: string) => void }) {
  const { schema } = useStudio();
  const [rawSpec, setSpec] = usePersistentState<CharacterSpec>("studio.builder.spec", () => defaultSpec(schema));
  const spec = useMemo(() => sanitize(rawSpec, schema), [rawSpec, schema]);
  const [count, setCount] = usePersistentState("studio.builder.count", () => 2);
  const [aspect, setAspect] = usePersistentState("studio.builder.aspect", () => "1:1");
  const [face, setFace] = useState<ImageMeta | null>(null);
  const [consent, setConsent] = useState(false);
  const [advanced, setAdvanced] = useState(false);
  const [tab, setTab] = useState<GroupId>("face");
  const [jobs, setJobs] = useState<BuilderJob[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [lightbox, setLightbox] = useState<ImageMeta | null>(null);
  const [saving, setSaving] = useState<{ image: ImageMeta; spec: CharacterSpec } | null>(null);
  const [prompt, setPrompt] = useState("");

  const preview = useDebounced(spec, 300);
  useEffect(() => {
    let live = true;
    api.promptPreview(preview, face !== null).then((r) => live && setPrompt(r.prompt), () => {});
    return () => {
      live = false;
    };
  }, [preview, face]);

  const setSelection = (id: string, sel: Selection | undefined) =>
    setSpec((prev) => {
      const clean = sanitize(prev, schema);
      const selections = { ...clean.selections };
      if (sel) selections[id] = sel;
      else delete selections[id];
      return { ...clean, selections };
    });

  const fieldsFor = (group: GroupId) =>
    schema.attributes
      .filter((a) => a.group === group)
      .map((a) => (
        <AttributeField
          key={a.id}
          attribute={a}
          levels={schema.levels}
          selection={spec.selections[a.id]}
          onChange={(sel) => setSelection(a.id, sel)}
        />
      ));

  const needsConsent = face?.kind === "upload" && !consent;

  const generate = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const job = await api.generateCandidates({ spec, face_image_id: face?.id ?? null, consent, count, aspect, seed: null });
      setJobs((prev) => [{ id: job.id, count, aspect, spec }, ...prev]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  const ratio = (key: string) => (schema.aspects[key] ? schema.aspects[key].width / schema.aspects[key].height : 1);

  return (
    <div className="workspace">
      <aside className="panel">
        <div className="panel__scroll">
          <FaceUpload face={face} consent={consent} onFace={setFace} onConsent={setConsent} />

          <section className="card">
            <div className="card__title">
              <span>Base identity</span>
              <span className="row">
                <button type="button" className="btn btn--ghost btn--sm" onClick={() => setSpec(randomSpec(schema))}>
                  🎲 Randomize
                </button>
                <button type="button" className="btn btn--ghost btn--sm" onClick={() => setSpec(defaultSpec(schema))}>
                  Reset
                </button>
              </span>
            </div>
            {fieldsFor("base")}
            <label className="field">
              <span className="field__label">
                Age <span className="accent">{spec.age}</span>
              </span>
              <input
                type="range"
                min={schema.age.min}
                max={schema.age.max}
                value={spec.age}
                onChange={(e) => setSpec({ ...spec, age: Number(e.target.value) })}
              />
            </label>
          </section>

          <section className="card">
            <button
              type="button"
              className="card__title card__toggle"
              aria-expanded={advanced}
              onClick={() => setAdvanced(!advanced)}
            >
              <span>Advanced settings</span>
              <span className="muted">{advanced ? "▲" : "▼"}</span>
            </button>
            {advanced && (
              <>
                <Segmented
                  label="Advanced group"
                  value={tab}
                  options={schema.groups.filter((g) => g.id !== "base").map((g) => ({ value: g.id, label: g.label }))}
                  onChange={setTab}
                />
                {fieldsFor(tab)}
              </>
            )}
          </section>

          <section className="card">
            <label className="field">
              <span className="field__label">Extra details</span>
              <textarea
                rows={2}
                maxLength={500}
                placeholder="e.g. a small mole above the lip, soft confident smile"
                value={spec.extra}
                onChange={(e) => setSpec({ ...spec, extra: e.target.value })}
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
              label="Variations"
              value={count}
              options={[1, 2, 3, 4].map((n) => ({ value: n, label: `×${n}` }))}
              onChange={setCount}
            />
          </div>
          <ErrorNote message={error} />
          <button type="button" className="btn btn--primary btn--block" disabled={submitting || needsConsent} onClick={generate}>
            {needsConsent ? "Confirm face permission to continue" : submitting ? "Queuing…" : "Generate influencer"}
          </button>
        </footer>
      </aside>

      <main className="stage">
        <details className="card prompt-card">
          <summary>Compiled FLUX.2 prompt</summary>
          <p className="prompt-text">{prompt}</p>
        </details>
        {jobs.length === 0 ? (
          <div className="hero">
            <h1>Design your AI influencer</h1>
            <p className="muted">
              Pick a base identity, fine-tune face, body and style from Average to Extreme, then generate variations.
              Save the one you like to build a consistent character for content.
            </p>
          </div>
        ) : (
          jobs.map((j) => (
            <JobView
              key={j.id}
              jobId={j.id}
              placeholders={j.count}
              aspect={ratio(j.aspect)}
              onOpen={setLightbox}
              actions={(img) => (
                <>
                  <button type="button" className="btn btn--primary btn--sm" onClick={() => setSaving({ image: img, spec: j.spec })}>
                    Save as influencer
                  </button>
                  <button
                    type="button"
                    className="btn btn--ghost btn--sm"
                    title="Keep this face and keep editing attributes"
                    onClick={() => setFace(img)}
                  >
                    Use as face
                  </button>
                </>
              )}
            />
          ))
        )}
      </main>

      {lightbox && <Lightbox image={lightbox} onClose={() => setLightbox(null)} />}
      {saving && (
        <SaveDialog
          image={saving.image}
          onClose={() => setSaving(null)}
          onSave={async (name) => {
            const c = await api.createCharacter(name, saving.spec, saving.image.id);
            navigate(`/characters/${c.id}`);
          }}
        />
      )}
    </div>
  );
}

function SaveDialog(props: { image: ImageMeta; onClose: () => void; onSave: (name: string) => Promise<void> }) {
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <Modal title="Save influencer" onClose={props.onClose}>
      <form
        className="save-dialog"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            await props.onSave(name.trim());
          } catch (err) {
            setError((err as Error).message);
            setBusy(false);
          }
        }}
      >
        <img src={props.image.url} alt="Selected portrait" />
        <label className="field">
          <span className="field__label">Name</span>
          <input autoFocus required maxLength={60} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Elif Nova" />
        </label>
        <ErrorNote message={error} />
        <button type="submit" className="btn btn--primary btn--block" disabled={busy || !name.trim()}>
          {busy ? "Saving…" : "Save and open"}
        </button>
      </form>
    </Modal>
  );
}
