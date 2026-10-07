import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type MotionCommon } from "../api";
import { ClipCard, ClipJobView } from "../components/ClipCard";
import { MediaLibrary, formatSeconds } from "../components/MediaLibrary";
import { Chip, Empty, ErrorNote, Segmented } from "../components/ui";
import { usePersistentState } from "../hooks";
import type { Character, CharacterDetail, ClipMeta, ImageMeta, MotionHealth, MotionSchema, Orientation, Resolution } from "../types";

type Mode = "dance" | "music" | "motion";

const MODES: { value: Mode; label: string; hint: string }[] = [
  { value: "dance", label: "Dance video", hint: "Your influencer performs the moves and camera of a reference clip (Wan-Animate-2)." },
  { value: "music", label: "Music dance", hint: "Choreography generated from a song's beat, in a chosen style (Wan-Dancer)." },
  { value: "motion", label: "Motion", hint: "5-second moves from a preset or your own description (Wan 2.2)." },
];
const MUSIC_LENGTHS = [5, 10, 15, 20, 25, 30];

function sizeFor(schema: MotionSchema, resolution: Resolution, orientation: Orientation, w: number, h: number) {
  let o = orientation;
  if (o === "auto") {
    const r = h ? w / h : 1;
    o = r > 1.15 ? "landscape" : r < 0.87 ? "portrait" : "square";
  }
  return schema.resolutions[resolution][o];
}

export function MotionPage({ characterId, navigate }: { characterId?: string; navigate: (path: string) => void }) {
  const [schema, setSchema] = useState<MotionSchema | null>(null);
  const [health, setHealth] = useState<MotionHealth | null>(null);
  const [characters, setCharacters] = useState<Character[] | null>(null);
  const [detail, setDetail] = useState<CharacterDetail | null>(null);
  const [clips, setClips] = useState<ClipMeta[]>([]);
  const [sourceId, setSourceId] = useState<string | null>(null);
  const [mode, setMode] = usePersistentState<Mode>("studio.motion.mode", () => "dance");
  const [resolution, setResolution] = usePersistentState<Resolution>("studio.motion.resolution", () => "480p");
  const [orientation, setOrientation] = useState<Orientation>("auto");
  const [smooth, setSmooth] = useState(false);
  // dance
  const [driver, setDriver] = useState<ClipMeta | null>(null);
  const [danceStart, setDanceStart] = useState(0);
  const [danceSeconds, setDanceSeconds] = useState(5);
  const [poseStrength, setPoseStrength] = useState(1);
  const [keepAudio, setKeepAudio] = useState(true);
  // music
  const [music, setMusic] = useState<ClipMeta | null>(null);
  const [musicStart, setMusicStart] = useState(0);
  const [musicSeconds, setMusicSeconds] = useState(10);
  const [style, setStyle] = useState("kpop");
  const [energy, setEnergy] = useState("medium");
  const [quality, setQuality] = useState(false);
  // motion
  const [presetId, setPresetId] = useState<string | null>("groove");
  const [prompt, setPrompt] = useState("");

  const [jobs, setJobs] = useState<{ id: string; aspect: number }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.motionSchema().then(setSchema, (e: Error) => setError(e.message));
    api.motionHealth().then(setHealth, () => {});
    api.characters().then(setCharacters, (e: Error) => setError(e.message));
  }, []);

  const selected = characters?.find((c) => c.id === characterId) ?? characters?.[0];
  const reload = useCallback(() => {
    if (!selected) return;
    api.character(selected.id).then(setDetail, () => {});
    api.characterClips(selected.id).then(setClips, () => {});
  }, [selected]);
  useEffect(() => {
    setDetail(null);
    setSourceId(null);
    setJobs([]);
    reload();
  }, [reload]);

  const sources = useMemo(
    () => (detail?.images ?? []).filter((i) => i.kind === "content" || i.kind === "reference"),
    [detail],
  );
  useEffect(() => {
    if (!detail || sourceId) return;
    setSourceId(sources.find((i) => i.kind === "content")?.id ?? detail.portrait_id);
  }, [detail, sources, sourceId]);
  const source: ImageMeta | undefined = sources.find((i) => i.id === sourceId);

  // keep ranges valid when the selected media changes
  useEffect(() => {
    if (!driver) return;
    setDanceStart((s) => Math.min(s, Math.max(0, driver.duration - 1)));
    setDanceSeconds((s) => Math.max(1, Math.min(s, 20, Math.floor(driver.duration))));
  }, [driver]);
  useEffect(() => {
    if (!music) return;
    setMusicStart((s) => Math.min(s, Math.max(0, music.duration - 5)));
  }, [music]);

  if (!schema || !characters) return <div className="page">{error ? <ErrorNote message={error} /> : <p className="muted">Loading…</p>}</div>;
  if (characters.length === 0) {
    return (
      <div className="page">
        <Empty title="No influencer yet">
          <a href="#/builder">Design one in the Builder</a>, then bring them to life here.
        </Empty>
      </div>
    );
  }

  const danceMax = driver ? Math.max(1, Math.min(schema.limits.dance_seconds, driver.duration - danceStart)) : 1;
  const musicAvailable = music ? music.duration - musicStart : 0;
  const musicLengths = MUSIC_LENGTHS.filter((s) => s <= musicAvailable + 0.05);
  const size = sizeFor(
    schema,
    resolution,
    orientation,
    mode === "dance" && driver ? driver.width : (source?.width ?? 1),
    mode === "dance" && driver ? driver.height : (source?.height ?? 1),
  );
  const missing = health?.modes[mode] ?? [];
  const missingSmooth = smooth ? (health?.modes.smooth ?? []) : [];

  const ready =
    !!selected &&
    !!source &&
    (mode === "dance" ? !!driver : mode === "music" ? !!music && musicLengths.includes(musicSeconds) : !!presetId || !!prompt.trim());

  const generate = async () => {
    if (!selected || !source) return;
    setBusy(true);
    setError(null);
    const common: MotionCommon = { source_image_id: source.id, resolution, orientation, smooth, seed: null };
    try {
      const job =
        mode === "dance"
          ? await api.dance(selected.id, {
              ...common,
              driver_id: driver!.id,
              start: danceStart,
              seconds: Math.min(danceSeconds, danceMax),
              pose_strength: poseStrength,
              keep_audio: keepAudio,
            })
          : mode === "music"
            ? await api.musicDance(selected.id, {
                ...common,
                music_id: music!.id,
                start: musicStart,
                seconds: musicSeconds,
                style,
                energy,
                quality,
              })
            : await api.motionPreset(selected.id, { ...common, preset_id: presetId, prompt });
      setJobs((prev) => [{ id: job.id, aspect: size.width / size.height }, ...prev]);
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
            <div className="avatar-row">
              {characters.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  className={`avatar${c.id === selected?.id ? " avatar--active" : ""}`}
                  onClick={() => navigate(`/motion/${c.id}`)}
                  title={c.name}
                >
                  <img src={c.portrait_url} alt={c.name} />
                  <span>{c.name}</span>
                </button>
              ))}
            </div>
            <span className="field__label">Start frame</span>
            <div className="source-row">
              {sources.map((img) => (
                <button
                  key={img.id}
                  type="button"
                  className={`source${img.id === sourceId ? " source--active" : ""}`}
                  onClick={() => setSourceId(img.id)}
                  aria-pressed={img.id === sourceId}
                  title={img.caption}
                >
                  <img src={img.url} alt={img.caption || "Character image"} loading="lazy" />
                </button>
              ))}
            </div>
            <p className="muted small">Full-body shots from Create move best. The face is taken from this image.</p>
          </section>

          <section className="card">
            <Segmented label="Mode" value={mode} options={MODES.map((m) => ({ value: m.value, label: m.label }))} onChange={setMode} />
            <p className="muted small">{MODES.find((m) => m.value === mode)!.hint}</p>

            {mode === "dance" && (
              <>
                <MediaLibrary kind="driver" selected={driver} onSelect={setDriver} />
                {driver && (
                  <>
                    <label className="field">
                      <span className="field__label">
                        Start <span className="accent">{formatSeconds(danceStart)}</span>
                      </span>
                      <input
                        type="range"
                        min={0}
                        max={Math.max(0, driver.duration - 1)}
                        step={0.1}
                        value={danceStart}
                        onChange={(e) => setDanceStart(Number(e.target.value))}
                      />
                    </label>
                    <label className="field">
                      <span className="field__label">
                        Length <span className="accent">{Math.min(danceSeconds, danceMax).toFixed(0)} s</span>
                        <span className="muted"> · max {schema.limits.dance_seconds} s</span>
                      </span>
                      <input
                        type="range"
                        min={1}
                        max={Math.floor(danceMax)}
                        step={1}
                        value={Math.min(danceSeconds, Math.floor(danceMax))}
                        onChange={(e) => setDanceSeconds(Number(e.target.value))}
                      />
                    </label>
                    <label className="field">
                      <span className="field__label">
                        Follow the moves <span className="accent">{poseStrength.toFixed(2)}</span>
                      </span>
                      <input type="range" min={0.5} max={1.5} step={0.05} value={poseStrength} onChange={(e) => setPoseStrength(Number(e.target.value))} />
                    </label>
                    {driver.has_audio && (
                      <label className="checkbox">
                        <input type="checkbox" checked={keepAudio} onChange={(e) => setKeepAudio(e.target.checked)} />
                        <span>Keep the clip's music</span>
                      </label>
                    )}
                  </>
                )}
                <p className="muted small">Use clips you own or have the rights to. One person, full body, steady camera works best.</p>
              </>
            )}

            {mode === "music" && (
              <>
                <MediaLibrary kind="music" selected={music} onSelect={setMusic} />
                {music && (
                  <>
                    <label className="field">
                      <span className="field__label">
                        Start <span className="accent">{formatSeconds(musicStart)}</span>
                      </span>
                      <input
                        type="range"
                        min={0}
                        max={Math.max(0, music.duration - 5)}
                        step={0.5}
                        value={musicStart}
                        onChange={(e) => setMusicStart(Number(e.target.value))}
                      />
                    </label>
                    <div className="field">
                      <span className="field__label">Length</span>
                      <Segmented
                        size="sm"
                        label="Length"
                        value={musicSeconds}
                        options={MUSIC_LENGTHS.map((s) => ({ value: s, label: `${s}s` }))}
                        onChange={setMusicSeconds}
                      />
                      {!musicLengths.includes(musicSeconds) && (
                        <span className="error-note">Only {musicAvailable.toFixed(1)} s of music after the start point.</span>
                      )}
                    </div>
                  </>
                )}
                <div className="field">
                  <span className="field__label">Dance style</span>
                  <div className="chips">
                    {schema.styles.map((s) => (
                      <Chip key={s.id} active={style === s.id} onClick={() => setStyle(s.id)}>
                        {s.label}
                      </Chip>
                    ))}
                  </div>
                </div>
                <div className="field">
                  <span className="field__label">Energy</span>
                  <Segmented size="sm" label="Energy" value={energy} options={schema.energies.map((e) => ({ value: e.id, label: e.label }))} onChange={setEnergy} />
                </div>
                <label className="checkbox">
                  <input type="checkbox" checked={quality} onChange={(e) => setQuality(e.target.checked)} />
                  <span>Quality choreography pass (25 steps, much slower)</span>
                </label>
              </>
            )}

            {mode === "motion" && (
              <>
                <div className="chips">
                  {schema.presets.map((p) => (
                    <Chip key={p.id} active={presetId === p.id} onClick={() => setPresetId(presetId === p.id ? null : p.id)}>
                      {p.label}
                    </Chip>
                  ))}
                </div>
                <label className="field">
                  <span className="field__label">{presetId ? "Add details" : "Describe the movement"}</span>
                  <textarea
                    rows={2}
                    maxLength={500}
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    placeholder={presetId ? "e.g. in slow motion, confetti falling" : "e.g. twirls an umbrella in the rain"}
                  />
                </label>
              </>
            )}
          </section>

          <section className="card">
            <div className="row row--between">
              <Segmented size="sm" label="Resolution" value={resolution} options={[{ value: "480p", label: "480p" }, { value: "720p", label: "720p" }]} onChange={setResolution} />
              <Segmented
                size="sm"
                label="Orientation"
                value={orientation}
                options={[
                  { value: "auto", label: "Auto" },
                  { value: "portrait", label: "9:16" },
                  { value: "landscape", label: "16:9" },
                  { value: "square", label: "1:1" },
                ]}
                onChange={setOrientation}
              />
            </div>
            <label className="checkbox">
              <input type="checkbox" checked={smooth} onChange={(e) => setSmooth(e.target.checked)} />
              <span>Smooth motion: double the frame rate with FILM interpolation</span>
            </label>
            <p className="muted small">
              Output {size.width}×{size.height}. 480p is the sweet spot on 16 GB GPUs; 720p needs roughly twice the time and memory.
            </p>
          </section>
        </div>

        <footer className="panel__footer">
          {(missing.length > 0 || missingSmooth.length > 0) && (
            <p className="error-note">
              Missing models: {[...missing, ...missingSmooth].map((m) => m.file).join(", ")}. Run{" "}
              <code>python scripts/download_models.py --comfy &lt;ComfyUI&gt; --video {mode}</code>
            </p>
          )}
          <ErrorNote message={error} />
          <button type="button" className="btn btn--primary btn--block" disabled={!ready || busy} onClick={generate}>
            {busy ? "Preparing…" : mode === "dance" ? "Generate dance" : mode === "music" ? "Generate music dance" : "Generate motion"}
          </button>
        </footer>
      </aside>

      <main className="stage">
        {jobs.map((j) => (
          <ClipJobView key={j.id} jobId={j.id} aspect={j.aspect} onDone={reload} />
        ))}
        <h2 className="stage__heading">Videos{selected ? ` · ${selected.name}` : ""}</h2>
        {clips.length === 0 ? (
          <Empty title="No videos yet">Pick a start frame and a mode, then generate. Renders run one at a time on your GPU.</Empty>
        ) : (
          <div className="clip-grid">
            {clips.map((clip) => (
              <ClipCard
                key={clip.id}
                clip={clip}
                actions={
                  <button
                    type="button"
                    className="btn btn--ghost btn--sm btn--danger"
                    onClick={async () => {
                      if (!window.confirm("Delete this video?")) return;
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
