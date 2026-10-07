export type Level = "average" | "notable" | "extreme";
export type GroupId = "base" | "face" | "body" | "style";

export interface Option {
  id: string;
  label: string;
}

export interface Attribute {
  id: string;
  label: string;
  group: GroupId;
  max_select: number;
  leveled: boolean;
  options: Option[];
}

export interface Preset {
  id: string;
  label: string;
  category: string;
  scene: string;
  aspect: string;
}

export interface Schema {
  levels: Level[];
  age: { min: number; max: number; default: number };
  groups: { id: GroupId; label: string }[];
  attributes: Attribute[];
  presets: Preset[];
  angles: { id: string; label: string }[];
  aspects: Record<string, { width: number; height: number }>;
  max_refs: number;
}

export interface Selection {
  values: string[];
  level: Level;
}

export interface CharacterSpec {
  selections: Record<string, Selection>;
  age: number;
  extra: string;
}

export type ImageKind = "upload" | "candidate" | "reference" | "content";

export interface ImageMeta {
  id: string;
  character_id: string | null;
  kind: ImageKind;
  caption: string;
  prompt: string;
  seed: number | null;
  width: number;
  height: number;
  created_at: number;
  url: string;
}

export interface Job<T = ImageMeta> {
  id: string;
  kind: string;
  status: "queued" | "running" | "done" | "error";
  progress: number;
  outputs: T[];
  error: string | null;
  queue_position: number | null;
}

export interface Character {
  id: string;
  name: string;
  spec: CharacterSpec;
  portrait_id: string;
  portrait_url: string;
  reference_ids: string[];
  lora: string;
  lora_strength: number;
  voice_id: string | null;
  created_at: number;
  image_count?: number;
}

export interface CharacterDetail extends Character {
  images: ImageMeta[];
}

export interface Health {
  comfy: boolean;
  error?: string;
  profile: { id: string; label: string; license: string; max_refs: number };
  missing_models: { folder: string; file: string }[];
  gpu?: string;
  vram_total?: number;
}

export type MediaKind = "driver" | "music" | "voice" | "speech";
export type ClipKind = MediaKind | "dance" | "music_dance" | "motion" | "talk";

export interface ClipMeta {
  id: string;
  character_id: string | null;
  kind: ClipKind;
  ext: string;
  name: string;
  caption: string;
  prompt: string;
  seed: number | null;
  width: number;
  height: number;
  fps: number;
  duration: number;
  has_audio: boolean;
  source_image_id: string | null;
  created_at: number;
  url: string;
  media_type: string;
}

export type Resolution = "480p" | "720p";
export type Orientation = "auto" | "portrait" | "landscape" | "square";

export interface MotionSchema {
  resolutions: Record<Resolution, Record<Exclude<Orientation, "auto">, { width: number; height: number }>>;
  styles: Option[];
  energies: Option[];
  presets: Option[];
  limits: { dance_seconds: number; music_seconds: number; fps: number };
}

export interface MotionHealth {
  comfy: boolean;
  modes: Record<"dance" | "music" | "motion" | "smooth", { folder: string; file: string }[]>;
}

export interface VoiceSchema {
  languages: Option[];
  limits: { talk_seconds: number; fps: number; voice_seconds: number };
  resolutions: Record<Exclude<Orientation, "auto">, { width: number; height: number }>;
}

export interface VoiceHealth {
  tts: { ok: boolean; loaded?: boolean; device?: string | null; error?: string | null };
  comfy: boolean;
  missing_models: { folder: string; file: string }[];
}
