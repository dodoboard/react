import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type TalkBody, type VoiceOptions } from "../api";
import { CharacterPicker, SourcePicker, resolveOrientation, sourceImages } from "../components/CharacterSources";
import { ClipCard, ClipJobView } from "../components/ClipCard";
import { MediaLibrary } from "../components/MediaLibrary";
import { Chip, Empty, ErrorNote, ProgressBar, Segmented } from "../components/ui";
import { useJob, usePersistentState } from "../hooks";
import type { Character, CharacterDetail, ClipMeta, Job, Orientation, VoiceHealth, VoiceSchema } from "../types";

type SpeechSource = "script" | "recording";

const CHARS_PER_SECOND = 14; // typical TTS pace; numbers expand when spoken, so this is a lower bound
const EXAMPLE = "Merhaba! Bugün size bu sonbaharın en sevdiğim üç kombinini göstereceğim. Hazırsanız başlayalım!";

function SpeechPreview({ jobId, onDone }: { jobId: string; onDone: (job: Job<ClipMeta>) => void }) {
  const job = useJob<ClipMeta>(jobId, onDone);
  if (job?.status === "error") return <ErrorNote message={job.error} />;
  if (job?.status === "done" && job.outputs[0])
    return <audio className="media-preview" src={job.outputs[0].url} controls autoPlay />;
  return (
    <div className="job__status">
      <span>{!job ? "Submitting…" : job.status === "queued" ? "Queued…" : `Synthesizing · ${Math.round(job.progress * 100)}%`}</span>
      <ProgressBar value={job?.progress ?? 0} />
    </div>
  );
}

function TtsWarning({ health }: { health: VoiceHealth | null }) {
  if (!health) return null;
  if (!health.tts.ok)
    return (
      <p className="error-note">
        The TTS server is not running. Start <code>tts\start.bat</code> (or <code>tts/start.sh</code>), or use a recording.
      </p>
    );
  return health.tts.error ? <p className="error-note">TTS model failed to load: {health.tts.error}</p> : null;
}

export function TalkPage({ characterId, navigate }: { characterId?: string; navigate: (path: string) => void }) {
  const [schema, setSchema] = useState<VoiceSchema | null>(null);
  const [health, setHealth] = useState<VoiceHealth | null>(null);
  const [characters, setCharacters] = useState<Character[] | null>(null);
  const [detail, setDetail] = useState<CharacterDetail | null>(null);
  const [clips, setClips] = useState<ClipMeta[]>([]);
  const [sourceId, setSourceId] = useState<string | null>(null);

  const [speechSource, setSpeechSource] = usePersistentState<SpeechSource>("studio.talk.source", () => "script");
  const [language, setLanguage] = usePersistentState("studio.talk.language", () => "tr");
  const [script, setScript] = usePersistentState("studio.talk.script", () => "");
  const [exaggeration, setExaggeration] = useState(0.5);
  const [cfgWeight, setCfgWeight] = useState(0.5);
  const [speech, setSpeech] = useState<ClipMeta | null>(null);
  const [speechRefresh, setSpeechRefresh] = useState(0);
  const [previewJob, setPreviewJob] = useState<string | null>(null);

  const [prompt, setPrompt] = useState("");
  const [orientation, setOrientation] = usePersistentState<Orientation>("studio.talk.orientation", () => "portrait");
  const [smooth, setSmooth] = useState(false);
  const [jobs, setJobs] = useState<{ id: string; aspect: number }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.voiceSchema().then(setSchema, (e: Error) => setError(e.message));
    api.characters().then(setCharacters, (e: Error) => setError(e.message));
    const poll = () => api.voiceHealth().then(setHealth, () => {});
    poll();
    const t = window.setInterval(poll, 10000); // the TTS server is often started after the studio
    return () => window.clearInterval(t);
  }, []);

  const selected = characters?.find((c) => c.id === characterId) ?? characters?.[0];
  const selectedId = selected?.id;
  const reload = useCallback(() => {
    if (!selectedId) return;
    api.character(selectedId).then(setDetail, () => {});
    api.characterClips(selectedId).then((all) => setClips(all.filter((c) => c.kind === "talk" || c.kind === "speech")), () => {});
  }, [selectedId]);
  useEffect(() => {
    setDetail(null);
    setSourceId(null);
    setSpeech(null);
    setPreviewJob(null);
    setJobs([]);
    reload();
  }, [reload]);

  const sources = useMemo(() => sourceImages(detail?.images), [detail]);
  useEffect(() => {
    if (detail && !sourceId) setSourceId(detail.portrait_id); // the portrait is usually the best-framed face
  }, [detail, sourceId]);
  const source = sources.find((i) => i.id === sourceId);

  // MediaLibrary reloads when this identity changes, so keep it stable per character.
  const assignVoice = useCallback(
    async (clip: ClipMeta | null) => {
      if (!selectedId) return;
      setError(null);
      try {
        setDetail(await api.updateCharacter(selectedId, { voice_id: clip?.id ?? "" }));
      } catch (e) {
        setError((e as Error).message);
      }
    },
    [selectedId],
  );

  const speechDone = useCallback(() => {
    setSpeechRefresh((n) => n + 1);
    reload();
  }, [reload]);

  if (!schema || !characters)
    return <div className="page">{error ? <ErrorNote message={error} /> : <p className="muted">Loading…</p>}</div>;
  if (characters.length === 0) {
    return (
      <div className="page">
        <Empty title="No influencer yet">
          <a href="#/builder">Design one in the Builder</a>, then give them a voice here.
        </Empty>
      </div>
    );
  }

  const limit = schema.limits.talk_seconds;
  const estimate = Math.ceil(script.trim().length / CHARS_PER_SECOND);
  const size = schema.resolutions[resolveOrientation(orientation, source?.width ?? 1, source?.height ?? 1)];
  const voiceOptions: VoiceOptions = { language, exaggeration, cfg_weight: cfgWeight, seed: null };
  const speechTooLong = !!speech && speech.duration > limit + 0.5;
  const ready =
    !!selected && !!source && (speechSource === "script" ? !!script.trim() : !!speech && !speechTooLong);
  const talkClips = clips.filter((c) => c.kind === "talk");
  const speechClips = clips.filter((c) => c.kind === "speech");

  const preview = async () => {
    if (!selected) return;
    setError(null);
    try {
      setPreviewJob((await api.speak({ ...voiceOptions, text: script, character_id: selected.id })).id);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const generate = async () => {
    if (!selected || !source) return;
    setBusy(true);
    setError(null);
    const body: TalkBody = {
      ...voiceOptions,
      source_image_id: source.id,
      orientation,
      smooth,
      prompt,
      text: speechSource === "script" ? script : "",
      speech_id: speechSource === "recording" ? (speech?.id ?? null) : null,
    };
    try {
      const job = await api.talk(selected.id, body);
      setJobs((prev) => [{ id: job.id, aspect: size.width / size.height }, ...prev]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const lipSync = (clip: ClipMeta) => {
    setSpeechSource("recording");
    setSpeech(clip);
  };

  return (
    <div className="workspace">
      <aside className="panel">
        <div className="panel__scroll">
          <section className="card">
            <div className="card__title">Influencer</div>
            <CharacterPicker characters={characters} selectedId={selected?.id} onPick={(id) => navigate(`/talk/${id}`)} />
            <span className="field__label">Start frame</span>
            <SourcePicker images={sources} selectedId={sourceId} onPick={setSourceId} />
            <p className="muted small">Front-facing shots with the mouth clearly visible lip-sync best.</p>
          </section>

          <section className="card">
            <div className="card__title">
              <span>Voice{selected ? ` of ${selected.name}` : ""}</span>
              <span className="muted small">{detail?.voice_id ? "cloned" : "built-in"}</span>
            </div>
            <div className="chips">
              <Chip active={!!detail && !detail.voice_id} onClick={() => assignVoice(null)}>
                Built-in voice
              </Chip>
            </div>
            <MediaLibrary
              kind="voice"
              selectedId={detail?.voice_id ?? null}
              onSelect={assignVoice}
              autoSelect={false}
              recordSeconds={20}
            />
            <p className="muted small">
              {schema.limits.voice_seconds - 5}–{schema.limits.voice_seconds} s of clear speech, one speaker, no music. Clone only
              voices you own or have permission to use. Every output carries an inaudible AI watermark.
            </p>
          </section>

          <section className="card">
            <Segmented
              label="Speech"
              value={speechSource}
              options={[
                { value: "script", label: "Write a script" },
                { value: "recording", label: "Use a recording" },
              ]}
              onChange={setSpeechSource}
            />
            {speechSource === "script" ? (
              <>
                <label className="field">
                  <span className="field__label">Language</span>
                  <select value={language} onChange={(e) => setLanguage(e.target.value)}>
                    {schema.languages.map((l) => (
                      <option key={l.id} value={l.id}>
                        {l.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span className="field__label">
                    Script{" "}
                    <span className={estimate > limit ? "error-text" : "muted"}>
                      · ≈ {estimate} s / {limit} s
                    </span>
                  </span>
                  <textarea rows={5} maxLength={1500} value={script} onChange={(e) => setScript(e.target.value)} placeholder={EXAMPLE} />
                </label>
                {estimate > limit && (
                  <span className="error-note">Talking videos are limited to {limit} s. Shorten the script or split it into parts.</span>
                )}
                {language === "tr" && (
                  <p className="muted small">Numbers, %, prices, times and abbreviations are read out in Turkish (e.g. “%25” → “yüzde yirmi beş”).</p>
                )}
                <label className="field">
                  <span className="field__label">
                    Expressiveness <span className="accent">{exaggeration.toFixed(2)}</span>
                  </span>
                  <input type="range" min={0.25} max={1.5} step={0.05} value={exaggeration} onChange={(e) => setExaggeration(Number(e.target.value))} />
                </label>
                <label className="field">
                  <span className="field__label">
                    Pacing <span className="accent">{cfgWeight.toFixed(2)}</span>
                    <span className="muted"> · lower is slower and calmer</span>
                  </span>
                  <input type="range" min={0} max={1} step={0.05} value={cfgWeight} onChange={(e) => setCfgWeight(Number(e.target.value))} />
                </label>
                <button type="button" className="btn btn--ghost" disabled={!script.trim()} onClick={preview}>
                  ▶ Preview voice
                </button>
                {previewJob && <SpeechPreview key={previewJob} jobId={previewJob} onDone={speechDone} />}
              </>
            ) : (
              <>
                <MediaLibrary
                  kind="speech"
                  selectedId={speech?.id ?? null}
                  onSelect={setSpeech}
                  characterId={selected?.id}
                  recordSeconds={limit}
                  refreshKey={speechRefresh}
                />
                {speechTooLong && <span className="error-note">This take is {speech.duration.toFixed(0)} s; talking videos are limited to {limit} s.</span>}
                <p className="muted small">Voice previews land here too, so you can lip-sync the exact take you liked.</p>
              </>
            )}
          </section>

          <section className="card">
            <label className="field">
              <span className="field__label">Expression &amp; setting</span>
              <textarea
                rows={2}
                maxLength={300}
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="e.g. warm smile, nods while talking, cozy café behind her"
              />
            </label>
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
            <label className="checkbox">
              <input type="checkbox" checked={smooth} onChange={(e) => setSmooth(e.target.checked)} />
              <span>Smooth motion: double the frame rate with FILM interpolation</span>
            </label>
            <p className="muted small">
              Output {size.width}×{size.height} at {schema.limits.fps * (smooth ? 2 : 1)} fps. InfiniteTalk renders 480p in ~3 s windows; every
              second of speech adds rendering time.
            </p>
          </section>
        </div>

        <footer className="panel__footer">
          {speechSource === "script" && <TtsWarning health={health} />}
          {health && health.missing_models.length > 0 && (
            <p className="error-note">
              Missing models: {health.missing_models.map((m) => m.file).join(", ")}. Run{" "}
              <code>python scripts/download_models.py --comfy &lt;ComfyUI&gt; --video talk</code>
            </p>
          )}
          <ErrorNote message={error} />
          <button type="button" className="btn btn--primary btn--block" disabled={!ready || busy} onClick={generate}>
            {busy ? "Preparing…" : "Make it talk"}
          </button>
        </footer>
      </aside>

      <main className="stage">
        {jobs.map((j) => (
          <ClipJobView key={j.id} jobId={j.id} aspect={j.aspect} onDone={speechDone} />
        ))}
        <h2 className="stage__heading">Talking videos{selected ? ` · ${selected.name}` : ""}</h2>
        {talkClips.length === 0 ? (
          <Empty title="No talking videos yet">Write a script or pick a recording, then press “Make it talk”.</Empty>
        ) : (
          <div className="clip-grid">
            {talkClips.map((clip) => (
              <ClipCard key={clip.id} clip={clip} actions={<DeleteClip clip={clip} onDeleted={reload} />} />
            ))}
          </div>
        )}
        {speechClips.length > 0 && (
          <>
            <h2 className="stage__heading">Speech takes</h2>
            <div className="clip-grid">
              {speechClips.map((clip) => (
                <ClipCard
                  key={clip.id}
                  clip={clip}
                  actions={
                    <>
                      <button type="button" className="btn btn--ghost btn--sm" onClick={() => lipSync(clip)}>
                        Lip-sync this
                      </button>
                      <DeleteClip
                        clip={clip}
                        onDeleted={() => {
                          if (speech?.id === clip.id) setSpeech(null);
                          speechDone();
                        }}
                      />
                    </>
                  }
                />
              ))}
            </div>
          </>
        )}
      </main>
    </div>
  );
}

function DeleteClip({ clip, onDeleted }: { clip: ClipMeta; onDeleted: () => void }) {
  return (
    <button
      type="button"
      className="btn btn--ghost btn--sm btn--danger"
      onClick={async () => {
        if (!window.confirm(`Delete this ${clip.kind === "talk" ? "video" : "take"}?`)) return;
        await api.deleteClip(clip.id);
        onDeleted();
      }}
    >
      Delete
    </button>
  );
}
