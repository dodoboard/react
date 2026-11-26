import clsx, { type ClassValue } from "clsx";
import type { VideoStatus } from "./api";

export const cn = (...c: ClassValue[]) => clsx(c);

export const money = (v: number, cur = "TRY") =>
  new Intl.NumberFormat("tr-TR", { style: "currency", currency: cur, maximumFractionDigits: v >= 1000 ? 0 : 2 }).format(v || 0);

export const num = (v: number) => new Intl.NumberFormat("tr-TR").format(v || 0);

export const ago = (iso: string) => {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "az önce";
  if (s < 3600) return `${Math.floor(s / 60)} dk önce`;
  if (s < 86400) return `${Math.floor(s / 3600)} sa önce`;
  return new Date(iso).toLocaleDateString("tr-TR", { day: "numeric", month: "short" });
};

export const STATUS: Record<VideoStatus, { label: string; tone: string; active?: boolean }> = {
  queued: { label: "Sırada", tone: "bg-slate-500/15 text-slate-700 dark:text-slate-300 ring-slate-400/20", active: true },
  scripting: { label: "Senaryo", tone: "bg-sky-500/15 text-sky-700 dark:text-sky-300 ring-sky-400/20", active: true },
  scripted: { label: "İncele", tone: "bg-amber-500/15 text-amber-700 dark:text-amber-300 ring-amber-400/25" },
  visuals: { label: "Görsel", tone: "bg-violet-500/15 text-violet-700 dark:text-violet-300 ring-violet-400/25", active: true },
  voice: { label: "Ses", tone: "bg-fuchsia-500/15 text-fuchsia-700 dark:text-fuchsia-300 ring-fuchsia-400/25", active: true },
  composing: { label: "Montaj", tone: "bg-cyan-500/15 text-cyan-700 dark:text-cyan-300 ring-cyan-400/25", active: true },
  done: { label: "Hazır", tone: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 ring-emerald-400/25" },
  failed: { label: "Hata", tone: "bg-rose-500/15 text-rose-700 dark:text-rose-300 ring-rose-400/25" },
  cancelled: { label: "İptal", tone: "bg-zinc-500/15 text-zinc-700 dark:text-zinc-400 ring-zinc-400/20" },
};

export const ANGLES: Record<string, string> = {
  problem: "Problem → Çözüm",
  curiosity: "Merak boşluğu",
  pov: "POV hikâye",
  social_proof: "Sosyal kanıt",
  comparison: "Karşılaştırma",
  listicle: "Liste",
  pattern_interrupt: "Kalıp kırıcı",
  deal: "Fırsat",
};

export const PLATFORMS = [
  { id: "tiktok", label: "TikTok" },
  { id: "reels", label: "Instagram Reels" },
  { id: "youtube", label: "YouTube Shorts" },
];

export const gb = (b?: number) => (b ? (b / 1024 ** 3).toFixed(1) : "0");
