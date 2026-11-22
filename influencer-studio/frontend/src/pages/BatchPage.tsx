import { useCallback, useEffect, useState } from "react";
import { api, type BatchBody } from "../api";
import { CharacterPicker } from "../components/CharacterSources";
import { ClipCard } from "../components/ClipCard";
import { ImageTile } from "../components/ImageTile";
import { Lightbox } from "../components/Lightbox";
import { CancelJobButton } from "../components/QueuePanel";
import { Empty, ErrorNote, ProgressBar } from "../components/ui";
import { usePersistentState, useStudio } from "../hooks";
import type { Batch, Character, ClipMeta, ImageMeta, ScriptTemplate } from "../types";

interface PostRow {
  preset_id: string;
  count: number;
}

interface TalkRow {
  template_id: string; // "" = free text
  values: Record<string, string>;
  text: string;
}

const ROLE_LABEL = { post: "Post", talk: "Talking video", export: "9:16 export" };
// rough render times on a 16 GB laptop GPU, for the estimate only
const SECONDS = { image: 15, talk: 240, export: 30 };

function preview(template: ScriptTemplate | undefined, row: TalkRow): string {
  if (!template) return row.text;
  return template.text.replace(/\{(\w+)\}/g, (_, key: string) => row.values[key] || `[${template.fields.find((f) => f.key === key)?.label}]`);
}

function BatchCard({ batch, onOpen }: { batch: Batch; onOpen: (img: ImageMeta) => void }) {
  const outputs = batch.jobs.flatMap((j) => j.job.outputs.map((o) => ({ role: j.role, out: o })));
  const running = batch.jobs.filter((j) => j.job.status === "queued" || j.job.status === "running");
  const failed = batch.jobs.filter((j) => j.job.status === "error");
  return (
    <section className="batch">
      <div className="row row--between">
        <strong>
          Pack · {new Date(batch.created_at * 1000).toLocaleString()} · {batch.jobs.length} jobs
        </strong>
        <a className="btn btn--ghost btn--sm" href={api.batchZipUrl(batch.id)} download>
          Download all (.zip)
        </a>
      </div>
      {!batch.finished && <ProgressBar value={batch.progress} />}
      {running.length > 0 && (
        <ul className="batch__jobs">
          {running.map((j) => (
            <li key={j.job_id} className="row row--between">
              <span className="small">
                {ROLE_LABEL[j.role]} · {j.label} · {j.job.status === "running" ? `${Math.round(j.job.progress * 100)}%` : "queued"}
              </span>
              <CancelJobButton job={j.job} />
            </li>
          ))}
        </ul>
      )}
      {failed.map((j) => (
        <p key={j.job_id} className="error-note">
          {ROLE_LABEL[j.role]} “{j.label}”: {j.job.error}
        </p>
      ))}
      {outputs.length > 0 && (
        <div className="clip-grid">
          {outputs.map(({ role, out }) =>
            "ext" in out ? (
              <ClipCard key={out.id} clip={out as ClipMeta} />
            ) : (
              <ImageTile key={out.id} image={out as ImageMeta} onOpen={() => onOpen(out as ImageMeta)} badge={ROLE_LABEL[role]} />
            ),
          )}
        </div>
      )}
    </section>
  );
}

export function BatchPage({ characterId, navigate }: { characterId?: string; navigate: (path: string) => void }) {
  const { schema } = useStudio();
  const [characters, setCharacters] = useState<Character[] | null>(null);
  const [templates, setTemplates] = useState<ScriptTemplate[]>([]);
  const [posts, setPosts] = usePersistentState<PostRow[]>("studio.batch.posts", () => [
    { preset_id: "coffee", count: 2 },
    { preset_id: "street_style", count: 2 },
    { preset_id: "product", count: 1 },
  ]);
  const [talks, setTalks] = usePersistentState<TalkRow[]>("studio.batch.talks", () => [
    { template_id: "product", values: {}, text: "" },
  ]);
  const [exportTalks, setExportTalks] = usePersistentState("studio.batch.export", () => true);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [lightbox, setLightbox] = useState<ImageMeta | null>(null);

  useEffect(() => {
    api.characters().then(setCharacters, (e: Error) => setError(e.message));
    api.scripts().then(setTemplates, () => {});
  }, []);
  const selected = characters?.find((c) => c.id === characterId) ?? characters?.[0];

  const reload = useCallback(() => {
    if (selected) api.batches(selected.id).then(setBatches, () => {});
  }, [selected]);
  useEffect(() => {
    reload();
    const t = window.setInterval(reload, 2000);
    return () => window.clearInterval(t);
  }, [reload]);

  if (!characters) return <div className="page">{error ? <ErrorNote message={error} /> : <p className="muted">Loading…</p>}</div>;
  if (!selected) {
    return (
      <div className="page">
        <Empty title="No influencer yet">
          <a href="#/builder">Design one in the Builder</a>, then plan a week of content here.
        </Empty>
      </div>
    );
  }

  const images = posts.reduce((n, p) => n + p.count, 0);
  const estimate = images * SECONDS.image + talks.length * (SECONDS.talk + (exportTalks ? SECONDS.export : 0));
  const updateTalk = (i: number, row: TalkRow) => setTalks(talks.map((t, j) => (j === i ? row : t)));

  const submit = async () => {
    setBusy(true);
    setError(null);
    const body: BatchBody = {
      posts: posts.map((p) => ({
        preset_id: p.preset_id,
        prompt: "",
        count: p.count,
        aspect: schema.presets.find((x) => x.id === p.preset_id)?.aspect ?? "4:5",
        seed: null,
        face_detail: true,
      })),
      talks: talks.map((t) => ({ text: t.template_id ? "" : t.text, template_id: t.template_id || null, values: t.values, prompt: "" })),
      export: exportTalks,
      format: "9:16",
      hd: false,
    };
    try {
      await api.createBatch(selected.id, body);
      reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="workspace">
      <aside className="panel">
        <div className="panel__scroll">
          <section className="card">
            <div className="card__title">Influencer</div>
            <CharacterPicker characters={characters} selectedId={selected.id} onPick={(id) => navigate(`/batch/${id}`)} />
          </section>

          <section className="card">
            <div className="card__title">
              <span>Posts</span>
              <span className="muted small">{images} images</span>
            </div>
            <ol className="pack-list">
              {posts.map((row, i) => (
                <li key={i} className="pack-row">
                  <select
                    aria-label={`Post ${i + 1} scene`}
                    value={row.preset_id}
                    onChange={(e) => setPosts(posts.map((p, j) => (j === i ? { ...p, preset_id: e.target.value } : p)))}
                  >
                    {schema.presets.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.category} · {p.label}
                      </option>
                    ))}
                  </select>
                  <select
                    aria-label={`Post ${i + 1} images`}
                    className="select--sm"
                    value={row.count}
                    onChange={(e) => setPosts(posts.map((p, j) => (j === i ? { ...p, count: Number(e.target.value) } : p)))}
                  >
                    {[1, 2, 3, 4].map((n) => (
                      <option key={n} value={n}>
                        ×{n}
                      </option>
                    ))}
                  </select>
                  <button type="button" className="icon-btn" aria-label={`Remove post ${i + 1}`} onClick={() => setPosts(posts.filter((_, j) => j !== i))}>
                    ✕
                  </button>
                </li>
              ))}
            </ol>
            <button type="button" className="btn btn--ghost btn--sm" disabled={posts.length >= 20}
              onClick={() => setPosts([...posts, { preset_id: schema.presets[0].id, count: 1 }])}>
              + Post
            </button>
          </section>

          <section className="card">
            <div className="card__title">
              <span>Talking videos</span>
              <span className="muted small">Turkish script templates</span>
            </div>
            {talks.map((row, i) => {
              const template = templates.find((t) => t.id === row.template_id);
              return (
                <div key={i} className="pack-talk">
                  <div className="pack-row">
                    <select
                      aria-label={`Video ${i + 1} script`}
                      value={row.template_id}
                      onChange={(e) => updateTalk(i, { ...row, template_id: e.target.value })}
                    >
                      {templates.map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.label}
                        </option>
                      ))}
                      <option value="">Own script</option>
                    </select>
                    <button type="button" className="icon-btn" aria-label={`Remove video ${i + 1}`} onClick={() => setTalks(talks.filter((_, j) => j !== i))}>
                      ✕
                    </button>
                  </div>
                  {template ? (
                    template.fields.map((f) => (
                      <input
                        key={f.key}
                        aria-label={f.label}
                        placeholder={f.label}
                        value={row.values[f.key] ?? ""}
                        maxLength={200}
                        onChange={(e) => updateTalk(i, { ...row, values: { ...row.values, [f.key]: e.target.value } })}
                      />
                    ))
                  ) : (
                    <textarea
                      rows={3}
                      maxLength={1500}
                      aria-label={`Video ${i + 1} script text`}
                      value={row.text}
                      placeholder="Merhaba! Bugün size…"
                      onChange={(e) => updateTalk(i, { ...row, text: e.target.value })}
                    />
                  )}
                  {template && <p className="muted small pack-preview">{preview(template, row)}</p>}
                </div>
              );
            })}
            <button type="button" className="btn btn--ghost btn--sm" disabled={talks.length >= 10}
              onClick={() => setTalks([...talks, { template_id: templates[0]?.id ?? "", values: {}, text: "" }])}>
              + Talking video
            </button>
            <label className="checkbox">
              <input type="checkbox" checked={exportTalks} onChange={(e) => setExportTalks(e.target.checked)} />
              <span>Also export each video as a captioned 9:16 post</span>
            </label>
          </section>
        </div>
        <footer className="panel__footer">
          <ErrorNote message={error} />
          <button type="button" className="btn btn--primary btn--block" disabled={busy || (!posts.length && !talks.length)} onClick={submit}>
            {busy ? "Queueing…" : "Queue content pack"}
          </button>
          <p className="muted small">
            {posts.length + talks.length * (exportTalks ? 2 : 1)} jobs · roughly {Math.max(1, Math.round(estimate / 60))} min on a 16 GB GPU.
            Images run first, then the videos, so models are loaded once.
          </p>
        </footer>
      </aside>

      <main className="stage">
        <h2 className="stage__heading">Content packs · {selected.name}</h2>
        {batches.length === 0 ? (
          <Empty title="No packs yet">Plan posts and talking videos on the left, then queue them all at once.</Empty>
        ) : (
          batches.map((b) => <BatchCard key={b.id} batch={b} onOpen={setLightbox} />)
        )}
      </main>
      {lightbox && <Lightbox image={lightbox} onClose={() => setLightbox(null)} />}
    </div>
  );
}
