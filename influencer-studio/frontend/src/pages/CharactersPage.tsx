import { useEffect, useState } from "react";
import { api } from "../api";
import { ErrorNote } from "../components/ui";
import type { Character } from "../types";

export function CharactersPage() {
  const [characters, setCharacters] = useState<Character[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.characters().then(setCharacters, (e: Error) => setError(e.message));
  }, []);

  return (
    <div className="page">
      <header className="page__header">
        <h1>Your influencers</h1>
      </header>
      <ErrorNote message={error} />
      <div className="character-grid">
        <a className="character-card character-card--new" href="#/builder">
          <span className="plus">＋</span>
          <span>New influencer</span>
        </a>
        {characters?.map((c) => (
          <a key={c.id} className="character-card" href={`#/characters/${c.id}`}>
            <img src={c.portrait_url} alt={c.name} loading="lazy" />
            <div className="character-card__meta">
              <strong>{c.name}</strong>
              <span className="muted small">
                {c.image_count ?? 0} images{c.lora ? " · LoRA" : ""}
              </span>
            </div>
          </a>
        ))}
      </div>
    </div>
  );
}
