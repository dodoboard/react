import type { Character, CharacterDetail, CharacterSpec, Health, ImageMeta, Job, Schema } from "./types";

function formatDetail(detail: unknown): string {
  if (Array.isArray(detail)) {
    return detail.map((d: { msg?: string }) => (d.msg ?? "").replace(/^Value error, /, "")).join("; ");
  }
  return typeof detail === "string" ? detail : "Request failed";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    let message = res.statusText;
    try {
      message = formatDetail((await res.json()).detail);
    } catch {
      /* non-JSON error body */
    }
    throw new Error(message);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export interface BuilderBody {
  spec: CharacterSpec;
  face_image_id: string | null;
  consent: boolean;
  count: number;
  aspect: string;
  seed: number | null;
}

export interface ContentBody {
  preset_id: string | null;
  prompt: string;
  count: number;
  aspect: string;
  seed: number | null;
}

export interface CharacterPatch {
  name?: string;
  reference_ids?: string[];
  lora?: string;
  lora_strength?: number;
}

export const api = {
  schema: () => request<Schema>("/api/schema"),
  health: () => request<Health>("/api/health"),
  loras: () => request<string[]>("/api/loras"),
  promptPreview: (spec: CharacterSpec, with_face: boolean) =>
    request<{ prompt: string }>("/api/prompt-preview", json("POST", { spec, with_face })),
  upload: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<ImageMeta>("/api/uploads", { method: "POST", body: form });
  },
  generateCandidates: (body: BuilderBody) => request<Job>("/api/builder/generate", json("POST", body)),
  job: (id: string) => request<Job>(`/api/jobs/${id}`),
  characters: () => request<Character[]>("/api/characters"),
  character: (id: string) => request<CharacterDetail>(`/api/characters/${id}`),
  createCharacter: (name: string, spec: CharacterSpec, image_id: string) =>
    request<Character>("/api/characters", json("POST", { name, spec, image_id })),
  updateCharacter: (id: string, patch: CharacterPatch) =>
    request<CharacterDetail>(`/api/characters/${id}`, json("PATCH", patch)),
  deleteCharacter: (id: string) => request<void>(`/api/characters/${id}`, { method: "DELETE" }),
  identityPack: (id: string, angles: string[]) =>
    request<Job>(`/api/characters/${id}/identity-pack`, json("POST", { angles })),
  content: (id: string, body: ContentBody) => request<Job>(`/api/characters/${id}/content`, json("POST", body)),
  deleteImage: (id: string) => request<void>(`/api/images/${id}`, { method: "DELETE" }),
  datasetUrl: (id: string) => `/api/characters/${id}/dataset.zip`,
};
