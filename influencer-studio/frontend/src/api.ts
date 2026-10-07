import type {
  Character,
  CharacterDetail,
  CharacterSpec,
  ClipMeta,
  Health,
  ImageMeta,
  Job,
  MotionHealth,
  MotionSchema,
  Orientation,
  Resolution,
  Schema,
} from "./types";

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

export interface MotionCommon {
  source_image_id: string;
  resolution: Resolution;
  orientation: Orientation;
  smooth: boolean;
  seed: number | null;
}

export interface DanceBody extends MotionCommon {
  driver_id: string;
  start: number;
  seconds: number;
  pose_strength: number;
  keep_audio: boolean;
}

export interface MusicDanceBody extends MotionCommon {
  music_id: string;
  start: number;
  seconds: number;
  style: string;
  energy: string;
  quality: boolean;
}

export interface MotionPresetBody extends MotionCommon {
  preset_id: string | null;
  prompt: string;
}

/** XHR upload so large dance clips can report progress. */
function uploadWithProgress<T>(url: string, file: File, onProgress: (fraction: number) => void): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onload = () => {
      let body: { detail?: unknown } | T | null = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        /* non-JSON body */
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as T);
      else reject(new Error(formatDetail((body as { detail?: unknown } | null)?.detail ?? xhr.statusText)));
    };
    xhr.onerror = () => reject(new Error("Upload failed"));
    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
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
  job: <T = ImageMeta>(id: string) => request<Job<T>>(`/api/jobs/${id}`),
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

  motionSchema: () => request<MotionSchema>("/api/motion/schema"),
  motionHealth: () => request<MotionHealth>("/api/motion/health"),
  mediaUploads: (kind: "driver" | "music") => request<ClipMeta[]>(`/api/motion/uploads?kind=${kind}`),
  uploadMedia: (kind: "driver" | "music", file: File, onProgress: (f: number) => void) =>
    uploadWithProgress<ClipMeta>(`/api/motion/uploads?kind=${kind}`, file, onProgress),
  dance: (characterId: string, body: DanceBody) =>
    request<Job<ClipMeta>>(`/api/characters/${characterId}/motion/dance`, json("POST", body)),
  musicDance: (characterId: string, body: MusicDanceBody) =>
    request<Job<ClipMeta>>(`/api/characters/${characterId}/motion/music`, json("POST", body)),
  motionPreset: (characterId: string, body: MotionPresetBody) =>
    request<Job<ClipMeta>>(`/api/characters/${characterId}/motion/preset`, json("POST", body)),
  characterClips: (characterId: string) => request<ClipMeta[]>(`/api/characters/${characterId}/clips`),
  deleteClip: (id: string) => request<void>(`/api/clips/${id}`, { method: "DELETE" }),
};
