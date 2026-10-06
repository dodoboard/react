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

export interface Job {
  id: string;
  kind: string;
  status: "queued" | "running" | "done" | "error";
  progress: number;
  images: ImageMeta[];
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
