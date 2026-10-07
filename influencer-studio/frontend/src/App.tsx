import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { StudioContext, useHashRoute } from "./hooks";
import { BuilderPage } from "./pages/BuilderPage";
import { CharacterPage } from "./pages/CharacterPage";
import { CharactersPage } from "./pages/CharactersPage";
import { CreatePage } from "./pages/CreatePage";
import { MotionPage } from "./pages/MotionPage";
import type { Health, Schema } from "./types";

const NAV = [
  { path: "builder", label: "Builder" },
  { path: "characters", label: "Influencers" },
  { path: "create", label: "Create" },
  { path: "motion", label: "Motion" },
];

function HealthPill({ health }: { health: Health | null }) {
  if (!health) return <span className="pill">Checking…</span>;
  if (!health.comfy) return <span className="pill pill--bad" title={health.error}>ComfyUI offline</span>;
  if (health.missing_models.length)
    return (
      <span className="pill pill--warn" title={health.missing_models.map((m) => `models/${m.folder}/${m.file}`).join("\n")}>
        {health.missing_models.length} model file(s) missing
      </span>
    );
  return (
    <span className="pill pill--ok" title={health.gpu}>
      {health.profile.label}
    </span>
  );
}

function SetupBanner({ health }: { health: Health | null }) {
  if (!health || (health.comfy && !health.missing_models.length)) return null;
  return (
    <div className="banner" role="status">
      {!health.comfy ? (
        <>
          ComfyUI is not reachable. Start it (e.g. <code>run_nvidia_gpu.bat</code>) and check <code>STUDIO_COMFY_URL</code>.
        </>
      ) : (
        <>
          Missing for {health.profile.label}:{" "}
          {health.missing_models.map((m) => (
            <code key={m.file}>
              models/{m.folder}/{m.file}
            </code>
          ))}{" "}
          Run <code>python scripts/download_models.py --comfy &lt;ComfyUI dir&gt;</code>.
        </>
      )}
    </div>
  );
}

export function App() {
  const [route, navigate] = useHashRoute();
  const [schema, setSchema] = useState<Schema | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [fatal, setFatal] = useState<string | null>(null);

  const refreshHealth = useCallback(() => {
    api.health().then(setHealth, () => setHealth(null));
  }, []);

  useEffect(() => {
    api.schema().then(setSchema, (e: Error) => setFatal(e.message));
    refreshHealth();
    const t = window.setInterval(refreshHealth, 15000);
    return () => window.clearInterval(t);
  }, [refreshHealth]);

  if (fatal) return <div className="fatal">Studio backend is not running ({fatal}). Start it with <code>python -m studio</code>.</div>;
  if (!schema) return <div className="fatal muted">Loading studio…</div>;

  const [section = "builder", param] = route;
  const page =
    section === "characters" && param ? (
      <CharacterPage key={param} id={param} navigate={navigate} />
    ) : section === "characters" ? (
      <CharactersPage />
    ) : section === "create" ? (
      <CreatePage characterId={param} navigate={navigate} />
    ) : section === "motion" ? (
      <MotionPage characterId={param} navigate={navigate} />
    ) : (
      <BuilderPage navigate={navigate} />
    );

  return (
    <StudioContext.Provider value={{ schema, health, refreshHealth }}>
      <header className="topbar">
        <a className="brand" href="#/builder">
          <span className="brand__mark">◆</span> <span className="brand__text">Influencer Studio</span>
        </a>
        <nav>
          {NAV.map((n) => (
            <a key={n.path} href={`#/${n.path}`} className={section === n.path ? "is-active" : ""}>
              {n.label}
            </a>
          ))}
        </nav>
        <HealthPill health={health} />
      </header>
      <SetupBanner health={health} />
      {page}
    </StudioContext.Provider>
  );
}
