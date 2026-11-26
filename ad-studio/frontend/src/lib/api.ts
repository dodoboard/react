export type VideoStatus =
  | "queued" | "scripting" | "scripted" | "visuals" | "voice" | "composing" | "done" | "failed" | "cancelled";

export interface Scene { voiceover: string; visual_prompt: string; on_screen_text: string }
export interface AdScript { hook: string; scenes: Scene[]; cta: string; caption: string; hashtags: string[]; title: string }

export type Approval = "draft" | "sent" | "approved" | "revision";
export interface BrandRef { id: number; name: string; logo_url: string | null; color: string }
export interface Brand {
  id: number; name: string; logo_url: string | null; primary_color: string; accent_color: string; font_file: string;
  voice_id: string; tone: string; audience: string; guidelines: string; banned_words: string; must_say: string; cta: string;
  ad_disclosure: string; hashtag: string; website: string; contact_name: string; contact_email: string; monthly_fee: number;
  per_video_fee: number; currency: string; active: boolean; products: number; campaigns: number; videos: number;
  pending_approval: number; fees_month: number; affiliate_total: number; cost_total: number;
}
export interface Charge { id: number; brand_id: number; period: string; kind: string; quantity: number; amount: number; paid: boolean; paid_at: string | null; note: string }
export type I2V = "off" | "hook" | "all";
export type Format = "broll" | "avatar_hook" | "avatar_full";

export interface Product {
  id: number; name: string; description: string; features: string; price: number | null; currency: string;
  affiliate_url: string; platform: string; commission_rate: number | null; image_path: string | null;
  image_url: string | null; cutout_url: string | null; active: boolean; brand_id: number | null; created_at: string;
}

export interface Video {
  id: number; campaign_id: number; variant_index: number; angle: string; hook: string; script: AdScript | null;
  caption: string; status: VideoStatus; step: string; progress: number; error: string; video_url: string | null;
  thumb_url: string | null; duration: number | null; tts_chars: number; render_seconds: number; subid: string;
  ab_label: string; favorite: boolean; platform: string; scheduled_at: string | null; published_at: string | null;
  publish_url: string; created_at: string; updated_at: string; hook_score: number | null; yt_id: string;
  stage_done: string; views?: number | null; campaign_name?: string; approval: Approval; approval_note: string;
  kind?: "single" | "collection"; product_count?: number; brand?: BrandRef | null;
  links?: { product_id: number; name: string; url: string }[]; product_name?: string; tracking_url?: string;
}

export interface Campaign {
  id: number; product_id: number; name: string; language: string; tone: string; audience: string; angle_notes: string;
  visual_style: string; voice_id: string; variants: number; scenes: number; use_i2v: boolean; music: string;
  i2v_mode: I2V; format: Format; avatar: string; autopilot_id: number | null; brand_id: number | null;
  kind: "single" | "collection"; collection_type: string; brand: BrandRef | null;
  products: { id: number; name: string; image_url: string | null }[];
  target_platform: string; created_at: string; product: { id: number; name: string; image_url: string | null } | null;
  counts: Record<VideoStatus, number>; total: number; revenue: number; thumb_url: string | null; videos?: Video[];
}

export interface Health {
  dry_run: boolean; encoder: string; rembg?: boolean; queue: { running: boolean; pending_jobs: number; current: number[] };
  ollama: { ok: boolean; error?: string; models?: number; model_ready?: boolean; demo?: boolean };
  comfy: { ok: boolean; error?: string; gpu?: string; vram_total?: number; vram_free?: number; demo?: boolean };
  tts: { ok: boolean; error?: string; provider?: string; used?: number; limit?: number; tier?: string; demo?: boolean };
}

export interface Config {
  ollama_url: string; ollama_model: string; ollama_temperature: number; comfy_url: string; image_workflow: string;
  video_workflow: string; use_i2v: boolean; i2v_mode: I2V; product_mode: "composite" | "kontext" | "off";
  kontext_workflow: string; avatar_workflow: string; caption_style: "bold_yellow" | "white_box" | "gradient_pop";
  sfx_volume: number; progress_bar: boolean; hook_punch: boolean; price_badge: boolean; hook_tournament: boolean;
  hooks_per_slot: number; image_steps: number; realism: boolean; realism_lora: string; realism_lora_strength: number;
  upscale_model: string; i2v_fast_lora: string; doc_i2v_ratio: number; presenter_chunk: number; identity_lock: boolean;
  lut_ads: string; lut_doc: string; negative_prompt: string; style_suffix: string;
  tts_provider: "elevenlabs" | "chatterbox"; elevenlabs_api_key: string; elevenlabs_voice_id: string; elevenlabs_model: string;
  chatterbox_voice: string; whisper_model: string; video_encoder: "auto" | "h264_nvenc" | "libx264"; subtitle_font: string;
  subtitle_highlight: string; music_volume: number; end_card_seconds: number; brand_name: string; cta_default: string;
  ad_disclosure: string; ai_label: boolean; currency: string; tts_cost_per_1k_chars: number; gpu_watts: number;
  kwh_price: number; youtube_privacy: "private" | "unlisted" | "public"; youtube_auto_upload: boolean; dry_run: boolean;
}

export interface Voice { id: string; name: string; preview_url: string | null; labels?: Record<string, string>; category?: string }
export interface Revenue {
  id: number; day: string; video_id: number | null; campaign_id: number | null; platform: string; amount: number;
  clicks: number; conversions: number; views: number; note: string; video_label: string | null; campaign_name: string | null;
  product_name: string | null; brand_name: string | null; product_id: number | null; brand_id: number | null;
}
export interface Summary {
  currency: string;
  kpi: { month_revenue: number; total_revenue: number; total_cost: number; roi: number | null; videos_done: number;
    videos_active: number; published: number; scheduled: number; clicks: number; conversions: number;
    views: number; avg_retention: number | null; rpm: number | null };
  series: { day: string; revenue: number; cost: number; videos: number; views: number }[];
  hook_retention: { id: number; hook: string; retention: number; score: number | null }[];
  fees: { month: number; total: number; unpaid: number }; profit: number;
  by_brand: { id: number; name: string; color: string; videos: number; affiliate: number; fees: number; cost: number; profit: number }[];
  top_videos: { id: number; hook: string; label: string; angle: string; thumb: string | null; retention: number | null; revenue: number; clicks: number; conversions: number; views: number }[];
  angles: { angle: string; avg: number; videos: number }[];
  platforms: { platform: string; revenue: number }[];
  campaigns: { id: number; name: string; product: string; videos: number; revenue: number; cost: number; roi: number | null }[];
}

export interface Rule {
  id: number; name: string; enabled: boolean; brand_id: number | null; kind: "single" | "collection";
  collection_type: string; products_per_video: number; product_ids: number[]; videos_per_day: number; run_hour: number;
  platform: string; language: string; format: Format; avatar: string; i2v_mode: I2V; auto_schedule: boolean;
  last_run: string | null; campaigns: number; videos: number;
}
export interface Avatar { name: string; url: string }

export interface Character {
  id: number; name: string; persona: string; speaking_style: string; catchphrases: string; opening_line: string;
  closing_line: string; look_prompt: string; avatar: string; voice_id: string; voice_settings: string; language: string;
  avatar_url: string | null; channels: number;
}
export type EpStatus = "queued" | "outline" | "script" | "gate" | "voice" | "visuals" | "compose" | "thumbnail" | "shorts"
  | "ready" | "uploading" | "scheduled" | "published" | "needs_review" | "failed" | "cancelled";
export interface Episode {
  id: number; channel_id: number; topic_id: number | null; kind: "long" | "short"; parent_id: number | null; status: EpStatus;
  progress: number; step: string; error: string; quality_score: number | null; title: string; description: string; tags: string;
  video_url: string | null; thumb_url: string | null; duration: number | null; slot_at: string | null; yt_id: string;
  published_at: string | null; created_at: string; updated_at: string; chapters: { t: number; title: string }[];
  quality: { score: number; hook: number; flow: number; originality: number; accuracy_risk: number; issues: string[] } | null;
  channel_name?: string; script?: { chapters: { title: string; segments: { kind: string; text: string; lower_third: string }[] }[] } | null;
  srt_url?: string | null;
}
export interface Channel {
  id: number; name: string; niche: string; language: string; character_id: number | null; format: "long" | "shorts" | "both";
  target_minutes: number; visual_style: string; music: string; privacy: string; category_id: string; default_tags: string;
  playlist_id: string; schedule_json: string; lead_days: number; daily_cap: number; min_quality: number; paused: boolean; run_hour: number;
  character: Character | null; connected: boolean; backlog: number; episodes: number; published: number; in_production: number;
  needs_review: number; next: Episode | null; next_slots: string[]; views: number;
}
export interface Topic { id: number; channel_id: number; title: string; angle: string; hook: string; score: number; sensitive: boolean; sensitive_reason: string; status: "idea" | "approved" | "rejected" | "used" }

export interface DoctorCheck { id: string; group: string; label: string; status: "ok" | "warn" | "fail" | "skip"; detail: string; fix: string }
export interface SmokeResult { steps: { name: string; ok: boolean; seconds: number; detail: string }[]; video_url: string | null; image_url: string | null }

const qb = (url: string, brandId?: number | null) =>
  brandId ? `${url}${url.includes("?") ? "&" : "?"}brand_id=${brandId}` : url;

export class ApiError extends Error {}

async function req<T>(method: string, url: string, body?: unknown): Promise<T> {
  const isForm = body instanceof FormData;
  const r = await fetch(url, {
    method,
    headers: body && !isForm ? { "Content-Type": "application/json" } : undefined,
    body: body ? (isForm ? body : JSON.stringify(body)) : undefined,
  });
  if (!r.ok) {
    let msg = `${r.status}`;
    try {
      const j = await r.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j);
    } catch { /* non-json */ }
    throw new ApiError(msg);
  }
  return r.json() as Promise<T>;
}

const file = (f: File) => { const fd = new FormData(); fd.append("file", f); return fd; };

export const api = {
  health: () => req<Health>("GET", "/api/health"),
  config: () => req<Config>("GET", "/api/config"),
  saveConfig: (patch: Partial<Config>) => req<Config>("PUT", "/api/config", patch),
  ollamaModels: () => req<{ name: string; size: number }[]>("GET", "/api/ollama/models"),
  voices: () => req<Voice[]>("GET", "/api/voices"),
  uploadVoice: (f: File) => req("POST", "/api/voices/upload", file(f)),
  music: () => req<{ name: string; size: number }[]>("GET", "/api/music"),
  uploadMusic: (f: File) => req("POST", "/api/music", file(f)),
  deleteMusic: (n: string) => req("DELETE", `/api/music/${encodeURIComponent(n)}`),
  workflows: () => req<string[]>("GET", "/api/workflows"),
  uploadWorkflow: (f: File) => req("POST", "/api/workflows", file(f)),

  products: (brandId?: number | null) => req<Product[]>("GET", qb("/api/products", brandId)),
  createProduct: (p: Partial<Product>) => req<Product>("POST", "/api/products", p),
  updateProduct: (id: number, p: Partial<Product>) => req<Product>("PUT", `/api/products/${id}`, p),
  deleteProduct: (id: number) => req("DELETE", `/api/products/${id}`),
  productImage: (id: number, f: File) => req<Product>("POST", `/api/products/${id}/image`, file(f)),
  autofill: (url: string) => req<Partial<Product> & { image_url?: string }>("POST", "/api/products/autofill", { url }),

  campaigns: (brandId?: number | null) => req<Campaign[]>("GET", qb("/api/campaigns", brandId)),
  campaign: (id: number) => req<Campaign>("GET", `/api/campaigns/${id}`),
  createCampaign: (b: Record<string, unknown>) => req<Campaign>("POST", "/api/campaigns", b),
  renderCampaign: (id: number) => req<{ queued: number[] }>("POST", `/api/campaigns/${id}/render`),
  deleteCampaign: (id: number) => req("DELETE", `/api/campaigns/${id}`),

  videos: (q = "", brandId?: number | null) => req<Video[]>("GET", qb(`/api/videos${q}`, brandId)),
  video: (id: number) => req<Video>("GET", `/api/videos/${id}`),
  saveScript: (id: number, s: AdScript) => req<Video>("PUT", `/api/videos/${id}/script`, s),
  render: (id: number) => req("POST", `/api/videos/${id}/render`),
  rescript: (id: number, render = false) => req("POST", `/api/videos/${id}/rescript?render=${render}`),
  revoice: (id: number) => req("POST", `/api/videos/${id}/revoice`),
  cancel: (id: number) => req("POST", `/api/videos/${id}/cancel`),
  patchVideo: (id: number, b: Record<string, unknown>) => req<Video>("PATCH", `/api/videos/${id}`, b),
  deleteVideo: (id: number) => req("DELETE", `/api/videos/${id}`),

  revenue: (brandId?: number | null) => req<Revenue[]>("GET", qb("/api/revenue", brandId)),
  addRevenue: (b: Record<string, unknown>) => req("POST", "/api/revenue", b),
  deleteRevenue: (id: number) => req("DELETE", `/api/revenue/${id}`),
  importRevenue: (f: File) => req<{ added: number; matched: number }>("POST", "/api/revenue/import", file(f)),
  summary: (days = 30, brandId?: number | null) => req<Summary>("GET", qb(`/api/analytics/summary?days=${days}`, brandId)),
  brands: () => req<Brand[]>("GET", "/api/brands"),
  brand: (id: number) => req<Brand>("GET", `/api/brands/${id}`),
  saveBrand: (b: Partial<Brand>) => b.id ? req<Brand>("PUT", `/api/brands/${b.id}`, b) : req<Brand>("POST", "/api/brands", b),
  deleteBrand: (id: number) => req("DELETE", `/api/brands/${id}`),
  brandLogo: (id: number, f: File) => req<Brand>("POST", `/api/brands/${id}/logo`, file(f)),
  brandFont: (id: number, f: File) => req<Brand>("POST", `/api/brands/${id}/font`, file(f)),
  charges: (id: number) => req<Charge[]>("GET", `/api/brands/${id}/charges`),
  generateCharges: (id: number, period?: string) => req<Charge[]>("POST", `/api/brands/${id}/charges/generate${period ? `?period=${period}` : ""}`),
  addCharge: (id: number, b: Partial<Charge>) => req<Charge>("POST", `/api/brands/${id}/charges`, b),
  markCharge: (cid: number, paid: boolean) => req<Charge>("PATCH", `/api/brands/charges/${cid}?paid=${paid}`),
  deleteCharge: (cid: number) => req("DELETE", `/api/brands/charges/${cid}`),

  ytStatus: () => req<{ installed: boolean; has_secret: boolean; connected: boolean; analytics: boolean }>("GET", "/api/youtube/status"),
  ytSync: () => req<{ rows: number }>("POST", "/api/youtube/analytics/sync"),
  cutout: (id: number) => req<Product>("POST", `/api/products/${id}/cutout`),
  avatars: () => req<Avatar[]>("GET", "/api/avatars"),
  uploadAvatar: (f: File) => req<Avatar>("POST", "/api/avatars", file(f)),
  generateAvatar: (description: string) => req<Avatar>("POST", "/api/avatars/generate", { description }),
  deleteAvatar: (n: string) => req("DELETE", `/api/avatars/${encodeURIComponent(n)}`),
  characters: () => req<Character[]>("GET", "/api/docu/characters"),
  saveCharacter: (c: Partial<Character>) => c.id ? req<Character>("PUT", `/api/docu/characters/${c.id}`, c) : req<Character>("POST", "/api/docu/characters", c),
  deleteCharacter: (id: number) => req("DELETE", `/api/docu/characters/${id}`),
  generatePersona: (b: { niche: string; name?: string; vibe?: string; language?: string }) => req<Partial<Character>>("POST", "/api/docu/characters/generate", b),
  previewVoice: (id: number, text = "") => req<{ url: string }>("POST", `/api/docu/characters/${id}/preview`, { text }),
  channels: () => req<Channel[]>("GET", "/api/docu/channels"),
  channel: (id: number) => req<Channel>("GET", `/api/docu/channels/${id}`),
  saveChannel: (c: Partial<Channel>) => c.id ? req<Channel>("PUT", `/api/docu/channels/${c.id}`, c) : req<Channel>("POST", "/api/docu/channels", c),
  deleteChannel: (id: number) => req("DELETE", `/api/docu/channels/${id}`),
  pauseChannel: (id: number, paused: boolean) => req<Channel>("POST", `/api/docu/channels/${id}/pause?paused=${paused}`),
  connectChannel: (id: number) => req<{ connected: boolean; channel: { title: string } }>("POST", `/api/docu/channels/${id}/connect`),
  channelYT: (id: number) => req<{ connected: boolean; channel?: { title: string; thumbnail: string; subscribers: number }; error?: string }>("GET", `/api/docu/channels/${id}/youtube`),
  channelStats: (id: number) => req<{ series: { day: string; views: number }[]; top: { id: number; title: string; kind: string; views: number; retention: number | null }[] }>("GET", `/api/docu/channels/${id}/stats`),
  topics: (cid: number) => req<Topic[]>("GET", `/api/docu/channels/${cid}/topics`),
  generateTopics: (cid: number, n = 10) => req<Topic[]>("POST", `/api/docu/channels/${cid}/topics/generate?n=${n}`),
  addTopic: (cid: number, title: string, angle = "") => req<Topic>("POST", `/api/docu/channels/${cid}/topics`, { title, angle }),
  patchTopic: (id: number, b: Partial<Topic>) => req<Topic>("PATCH", `/api/docu/topics/${id}`, b),
  episodes: (cid?: number) => req<Episode[]>("GET", `/api/docu/episodes${cid ? `?channel_id=${cid}` : ""}`),
  episode: (id: number) => req<Episode>("GET", `/api/docu/episodes/${id}`),
  createEpisode: (cid: number, b: { kind: "long" | "short"; topic_id?: number }) => req<Episode>("POST", `/api/docu/channels/${cid}/episodes`, b),
  retryEpisode: (id: number, full = false) => req("POST", `/api/docu/episodes/${id}/retry?full=${full}`),
  approveEpisode: (id: number) => req("POST", `/api/docu/episodes/${id}/approve`),
  cancelEpisode: (id: number) => req("POST", `/api/docu/episodes/${id}/cancel`),
  publishNow: (id: number) => req<{ yt_id: string }>("POST", `/api/docu/episodes/${id}/publish-now`),
  deleteEpisode: (id: number) => req("DELETE", `/api/docu/episodes/${id}`),
  quota: () => req<{ used: number; limit: number; episode_cost: number; uploads_left: number }>("GET", "/api/docu/quota"),
  upcoming: () => req<Episode[]>("GET", "/api/docu/upcoming"),
  doctor: (deep = false) => req<{ status: string; dry_run: boolean; checks: DoctorCheck[] }>("GET", `/api/doctor?deep=${deep}`),
  smoke: () => req<SmokeResult>("POST", "/api/doctor/smoke"),
  rules: () => req<Rule[]>("GET", "/api/autopilot"),
  saveRule: (r: Partial<Rule>) => r.id ? req<Rule>("PUT", `/api/autopilot/${r.id}`, r) : req<Rule>("POST", "/api/autopilot", r),
  deleteRule: (id: number) => req("DELETE", `/api/autopilot/${id}`),
  runRule: (id: number) => req<{ campaigns: number[] }>("POST", `/api/autopilot/${id}/run`),
  ytConnect: () => req("POST", "/api/youtube/connect"),
  ytSecret: (f: File) => req("POST", "/api/youtube/secret", file(f)),
  ytUpload: (id: number) => req<{ url: string }>("POST", `/api/youtube/upload/${id}`),
};
