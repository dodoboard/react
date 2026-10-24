import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type ExportBody, type ExportItem } from "../api";
import { CharacterPicker } from "../components/CharacterSources";
import { ClipCard, ClipJobView } from "../components/ClipCard";
import { CueEditor } from "../components/CueEditor";
import { MediaLibrary, formatSeconds } from "../components/MediaLibrary";
import { Empty, ErrorNote, Segmented } from "../components/ui";
import { usePersistentState } from "../hooks";
import type { Character, ClipMeta, ExportFormat, Option } from "../types";

const VIDEO_KINDS: ReadonlySet<string> = new Set(["talk", "dance", "music_dance", "motion"]);
const KIND_LABEL: Record<string, string> = { talk: "Talk", dance: "Dance", music_dance: "Music dance", motion: "Motion" };
const FORMATS: { value: ExportFormat; label: string; ratio: number }[] = [
  { value: "9:16", label: "9:16", ratio: 9 / 16 },
  { value: "4:5", label: "4:5", ratio: 4 / 5 },
  { value: "1:1", label: "1:1", ratio: 1 },
  { value: "16:9", label: "16:9", ratio: 16 / 9 },
];
const MAX_SECONDS = 180;

function itemLength(item: ExportItem, clip: ClipMeta | undefined): number {
  return clip ? Math.max(0, (item.end ?? clip.duration) - item.start) : 0;
}

function TimelineRow(props: {
  item: ExportItem;
  clip: ClipMeta;
  index: number;
  count: number;
  languages: Option[];
  onChange: (item: ExportItem) => void;
  onMove: (delta: number) => void;
  onRemove: () => void;
}) {
  const { item, clip } = props;
  const [captions, setCaptions] = useState(false);
  const end = item.end ?? clip.duration;
  return (
    <li className="timeline__item">
      <div className="timeline__head">
        <video src={`${clip.url}#t=0.5`} muted preload="metadata" playsInline />
        <div className="timeline__meta">
          <strong>
            {props.index + 1}. {KIND_LABEL[clip.kind] ?? clip.kind}
            {clip.meta?.hd ? " · HD" : ""}
          </strong>
          <span className="muted small" title={clip.caption}>
            {formatSeconds(item.start)}–{formatSeconds(end)} · {clip.caption}
          </span>
        </div>
        <span className="timeline__buttons">
          <button type="button" className="icon-btn" aria-label="Move up" disabled={props.index === 0} onClick={() => props.onMove(-1)}>
            ↑
          </button>
          <button type="button" className="icon-btn" aria-label="Move down" disabled={props.index === props.count - 1} onClick={() => props.onMove(1)}>
            ↓
          </button>
          <button type="button" className="icon-btn" aria-label="Remove from timeline" onClick={props.onRemove}>
            ✕
          </button>
        </span>
      </div>
      <div className="timeline__trim">
        <label className="field">
          <span className="field__label">
            In <span className="accent">{item.start.toFixed(1)} s</span>
          </span>
          <input
            type="range"
            min={0}
            max={Math.max(0, end - 0.5)}
            step={0.1}
            value={item.start}
            onChange={(e) => props.onChange({ ...item, start: Number(e.target.value) })}
          />
        </label>
        <label className="field">
          <span className="field__label">
            Out <span className="accent">{end.toFixed(1)} s</span>
          </span>
          <input
            type="range"
            min={item.start + 0.5}
            max={clip.duration}
            step={0.1}
            value={end}
            onChange={(e) => {
              const v = Number(e.target.value);
              props.onChange({ ...item, end: v >= clip.duration - 0.05 ? null : v });
            }}
          />
        </label>
      </div>
      <button type="button" className="link-btn small" onClick={() => setCaptions(!captions)} aria-expanded={captions}>
        {captions ? "Hide captions" : "Captions…"}
      </button>
      {captions && <CueEditor clip={clip} languages={props.languages} />}
    </li>
  );
}

export function ExportPage(props: { characterId?: string; addClipId?: string; navigate: (path: string) => void }) {
  const [characters, setCharacters] = useState<Character[] | null>(null);
  const [languages, setLanguages] = useState<Option[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.characters().then(setCharacters, (e: Error) => setError(e.message));
    api.voiceSchema().then((s) => setLanguages(s.languages), () => {});
  }, []);

  if (!characters) return <div className="page">{error ? <ErrorNote message={error} /> : <p className="muted">Loading…</p>}</div>;
  if (characters.length === 0) {
    return (
      <div className="page">
        <Empty title="No influencer yet">
          <a href="#/builder">Design one in the Builder</a>, make videos in Motion or Talk, then edit them together here.
        </Empty>
      </div>
    );
  }
  const selected = characters.find((c) => c.id === props.characterId) ?? characters[0];
  // keyed: the timeline is stored per influencer
  return (
    <ExportWorkspace
      key={selected.id}
      selected={selected}
      characters={characters}
      languages={languages}
      addClipId={props.addClipId}
      navigate={props.navigate}
    />
  );
}

function ExportWorkspace(props: {
  selected: Character;
  characters: Character[];
  languages: Option[];
  addClipId?: string;
  navigate: (path: string) => void;
}) {
  const { selected, characters, languages, addClipId, navigate } = props;
  const [clips, setClips] = useState<ClipMeta[]>([]);
  const [items, setItems] = usePersistentState<ExportItem[]>(`studio.export.${selected.id}`, () => []);
  const [format, setFormat] = usePersistentState<ExportFormat>("studio.export.format", () => "9:16");
  const [hd, setHd] = usePersistentState("studio.export.hd", () => false);
  const [subtitles, setSubtitles] = usePersistentState("studio.export.subtitles", () => true);
  const [style, setStyle] = usePersistentState<"reels" | "minimal">("studio.export.style", () => "reels");
  const [position, setPosition] = usePersistentState<"lower" | "middle">("studio.export.position", () => "lower");
  const [withMusic, setWithMusic] = useState(false);
  const [music, setMusic] = useState<ClipMeta | null>(null);
  const [musicStart, setMusicStart] = useState(0);
  const [volume, setVolume] = useState(-16);
  const [duck, setDuck] = useState(true);
  const [jobs, setJobs] = useState<{ id: string; aspect: number }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = useCallback(() => {
    api.characterClips(selected.id).then(setClips, (e: Error) => setError(e.message));
  }, [selected.id]);
  useEffect(reload, [reload]);

  const byId = useMemo(() => new Map(clips.map((c) => [c.id, c])), [clips]);
  const videos = clips.filter((c) => VIDEO_KINDS.has(c.kind));
  const exports = clips.filter((c) => c.kind === "export");
  const timeline = items.filter((i) => byId.has(i.clip_id));
  const total = timeline.reduce((sum, i) => sum + itemLength(i, byId.get(i.clip_id)), 0);

  const add = useCallback(
    (clip: ClipMeta) => setItems((prev) => [...prev, { clip_id: clip.id, start: 0, end: null }]),
    [setItems],
  );
  // "Export" from the Talk / Motion pages arrives as #/export/<character>/<clip>
  useEffect(() => {
    const clip = addClipId ? byId.get(addClipId) : undefined;
    if (!clip) return;
    if (!items.some((i) => i.clip_id === clip.id)) add(clip);
    navigate(`/export/${selected.id}`);
  }, [addClipId, byId, items, add, navigate, selected.id]);

  const update = (index: number, item: ExportItem) => setItems(timeline.map((x, i) => (i === index ? item : x)));
  const move = (index: number, delta: number) => {
    const next = [...timeline];
    [next[index], next[index + delta]] = [next[index + delta], next[index]];
    setItems(next);
  };

  const run = async () => {
    setBusy(true);
    setError(null);
    const body: ExportBody = {
      character_id: selected.id,
      items: timeline,
      format,
      hd,
      subtitles: { enabled: subtitles, style, position },
      music: withMusic && music ? { clip_id: music.id, start: musicStart, volume_db: volume, duck } : null,
    };
    try {
      const job = await api.exportVideo(body);
      setJobs((prev) => [{ id: job.id, aspect: FORMATS.find((f) => f.value === format)!.ratio }, ...prev]);
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
            <CharacterPicker characters={characters} selectedId={selected.id} onPick={(id) => navigate(`/export/${id}`)} />
          </section>

          <section className="card">
            <div className="card__title">
              <span>Timeline</span>
              <span className={`small ${total > MAX_SECONDS ? "error-text" : "muted"}`}>
                {formatSeconds(total)} / {formatSeconds(MAX_SECONDS)}
              </span>
            </div>
            {timeline.length === 0 ? (
              <p className="muted small">Add clips below. They play one after another; trim each with In / Out.</p>
            ) : (
              <ol className="timeline">
                {timeline.map((item, i) => (
                  <TimelineRow
                    key={`${item.clip_id}-${i}`}
                    item={item}
                    clip={byId.get(item.clip_id)!}
                    index={i}
                    count={timeline.length}
                    languages={languages}
                    onChange={(next) => update(i, next)}
                    onMove={(d) => move(i, d)}
                    onRemove={() => setItems(timeline.filter((_, j) => j !== i))}
                  />
                ))}
              </ol>
            )}
            <span className="field__label">Add clips</span>
            {videos.length === 0 ? (
              <p className="muted small">
                No videos yet: make some in <a href={`#/motion/${selected.id}`}>Motion</a> or <a href={`#/talk/${selected.id}`}>Talk</a>.
              </p>
            ) : (
              <div className="clip-picker">
                {videos.map((clip) => (
                  <button key={clip.id} type="button" className="clip-picker__item" onClick={() => add(clip)} title={clip.caption}>
                    <video src={`${clip.url}#t=0.5`} muted preload="metadata" playsInline />
                    <span>
                      {KIND_LABEL[clip.kind] ?? clip.kind}
                      {clip.meta?.hd ? " · HD" : ""} · {clip.duration.toFixed(0)}s
                    </span>
                  </button>
                ))}
              </div>
            )}
          </section>

          <section className="card">
            <div className="field">
              <span className="field__label">Format</span>
              <Segmented size="sm" label="Format" value={format} options={FORMATS} onChange={setFormat} />
            </div>
            <label className="checkbox">
              <input type="checkbox" checked={hd} onChange={(e) => setHd(e.target.checked)} />
              <span>HD: upscale clips to 1080p first (slower; reuses earlier HD copies)</span>
            </label>
          </section>

          <section className="card">
            <label className="checkbox">
              <input type="checkbox" checked={subtitles} onChange={(e) => setSubtitles(e.target.checked)} />
              <span>Burn in captions</span>
            </label>
            {subtitles && (
              <div className="row row--between">
                <Segmented
                  size="sm"
                  label="Caption style"
                  value={style}
                  options={[
                    { value: "reels", label: "Reels" },
                    { value: "minimal", label: "Minimal" },
                  ]}
                  onChange={setStyle}
                />
                <Segmented
                  size="sm"
                  label="Caption position"
                  value={position}
                  options={[
                    { value: "lower", label: "Lower" },
                    { value: "middle", label: "Middle" },
                  ]}
                  onChange={setPosition}
                />
              </div>
            )}
            <p className="muted small">
              Talk videos are captioned from their script. For other clips open “Captions…” on the timeline and recognize the speech.
            </p>
          </section>

          <section className="card">
            <label className="checkbox">
              <input type="checkbox" checked={withMusic} onChange={(e) => setWithMusic(e.target.checked)} />
              <span>Background music</span>
            </label>
            {withMusic && (
              <>
                <MediaLibrary kind="music" selectedId={music?.id ?? null} onSelect={setMusic} />
                {music && (
                  <label className="field">
                    <span className="field__label">
                      Song starts at <span className="accent">{formatSeconds(musicStart)}</span>
                    </span>
                    <input
                      type="range"
                      min={0}
                      max={Math.max(0, music.duration - 1)}
                      step={0.5}
                      value={Math.min(musicStart, music.duration)}
                      onChange={(e) => setMusicStart(Number(e.target.value))}
                    />
                  </label>
                )}
                <label className="field">
                  <span className="field__label">
                    Music level <span className="accent">{volume} dB</span>
                  </span>
                  <input type="range" min={-30} max={0} step={1} value={volume} onChange={(e) => setVolume(Number(e.target.value))} />
                </label>
                <label className="checkbox">
                  <input type="checkbox" checked={duck} onChange={(e) => setDuck(e.target.checked)} />
                  <span>Lower the music while someone speaks</span>
                </label>
              </>
            )}
          </section>
        </div>

        <footer className="panel__footer">
          <ErrorNote message={error} />
          <button
            type="button"
            className="btn btn--primary btn--block"
            disabled={!timeline.length || total > MAX_SECONDS || busy || (withMusic && !music)}
            onClick={run}
          >
            {busy ? "Preparing…" : `Export ${format} video`}
          </button>
          <p className="muted small">1080p H.264, 30 fps, mastered to −14 LUFS for Instagram, TikTok and YouTube.</p>
        </footer>
      </aside>

      <main className="stage">
        {jobs.map((j) => (
          <ClipJobView key={j.id} jobId={j.id} aspect={j.aspect} onDone={reload} />
        ))}
        <h2 className="stage__heading">Exports · {selected.name}</h2>
        {exports.length === 0 ? (
          <Empty title="No exports yet">Build a timeline on the left and export it as one post-ready video.</Empty>
        ) : (
          <div className="clip-grid">
            {exports.map((clip) => (
              <ClipCard
                key={clip.id}
                clip={clip}
                actions={
                  <button
                    type="button"
                    className="btn btn--ghost btn--sm btn--danger"
                    onClick={async () => {
                      if (!window.confirm("Delete this export?")) return;
                      await api.deleteClip(clip.id);
                      reload();
                    }}
                  >
                    Delete
                  </button>
                }
              />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
