import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Ban, Check, Clock, ExternalLink, Film, Play, RefreshCw, Send, ShieldAlert, Trash2, Youtube } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { api, type EpStatus, type Episode } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button, Modal, Pill, Progress, Segmented } from "./ui";

export const EP_STATUS: Record<EpStatus, { label: string; tone: string; active?: boolean }> = {
  queued: { label: "Sırada", tone: "bg-slate-500/15 text-slate-600 dark:text-slate-300", active: true },
  outline: { label: "Taslak", tone: "bg-sky-500/15 text-sky-600 dark:text-sky-300", active: true },
  script: { label: "Senaryo", tone: "bg-sky-500/15 text-sky-600 dark:text-sky-300", active: true },
  gate: { label: "Kalite", tone: "bg-indigo-500/15 text-indigo-600 dark:text-indigo-300", active: true },
  voice: { label: "Ses", tone: "bg-fuchsia-500/15 text-fuchsia-600 dark:text-fuchsia-300", active: true },
  visuals: { label: "Görsel", tone: "bg-violet-500/15 text-violet-600 dark:text-violet-300", active: true },
  compose: { label: "Montaj", tone: "bg-cyan-500/15 text-cyan-600 dark:text-cyan-300", active: true },
  thumbnail: { label: "Kapak", tone: "bg-cyan-500/15 text-cyan-600 dark:text-cyan-300", active: true },
  shorts: { label: "Shorts", tone: "bg-cyan-500/15 text-cyan-600 dark:text-cyan-300", active: true },
  ready: { label: "Hazır", tone: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-300" },
  uploading: { label: "Yükleniyor", tone: "bg-rose-500/15 text-rose-600 dark:text-rose-300", active: true },
  scheduled: { label: "Planlandı", tone: "bg-amber-500/15 text-amber-600 dark:text-amber-300" },
  published: { label: "Yayında", tone: "bg-red-600/15 text-red-600 dark:text-red-400" },
  needs_review: { label: "İnceleme", tone: "bg-orange-500/15 text-orange-600 dark:text-orange-300" },
  failed: { label: "Hata", tone: "bg-rose-500/15 text-rose-600 dark:text-rose-300" },
  cancelled: { label: "İptal", tone: "bg-zinc-500/15 text-zinc-500" },
};

export function EpBadge({ s }: { s: EpStatus }) {
  const x = EP_STATUS[s] ?? EP_STATUS.queued;
  return <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-semibold", x.tone)}>
    <span className={cn("h-1.5 w-1.5 rounded-full bg-current", x.active && "animate-pulse")} />{x.label}</span>;
}

const fmt = (iso: string | null) => iso ? new Date(iso).toLocaleString("tr-TR", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "";
const mmss = (t: number) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}`;

export function EpisodeCard({ e, onOpen }: { e: Episode; onOpen: () => void }) {
  const active = EP_STATUS[e.status]?.active;
  const short = e.kind === "short";
  return (
    <motion.button layout onClick={onOpen} whileHover={{ y: -3 }} className="card group flex flex-col overflow-hidden text-left transition hover:border-brand/40 hover:shadow-glow">
      <div className={cn("relative overflow-hidden bg-elev", short ? "aspect-video" : "aspect-video")}>
        {e.thumb_url ? <img src={e.thumb_url} className="h-full w-full object-cover transition duration-500 group-hover:scale-105" />
          : <div className="grid h-full place-items-center bg-gradient-to-br from-zinc-800 to-zinc-950 p-4 text-center">
            <p className="font-display text-sm font-bold text-white/80">{e.title || "Konu seçiliyor…"}</p></div>}
        <div className="absolute left-2.5 top-2.5 flex gap-1.5"><EpBadge s={e.status} />
          <span className="rounded-full bg-black/60 px-2 py-0.5 text-[10px] font-bold uppercase text-white">{short ? "Shorts" : "Belgesel"}</span></div>
        {e.duration && <span className="absolute bottom-2 right-2 rounded bg-black/75 px-1.5 py-0.5 font-mono text-[10px] text-white">{mmss(e.duration)}</span>}
      </div>
      <div className="flex flex-1 flex-col gap-2 p-3">
        <p className="line-clamp-2 text-[13px] font-semibold leading-snug">{e.title || "—"}</p>
        <div className="flex flex-wrap gap-1">
          {e.quality_score != null && <Pill className={cn(e.quality_score >= 8 ? "text-emerald-500" : e.quality_score >= 7 ? "text-amber-500" : "text-rose-400")}>★ {e.quality_score.toFixed(1)}</Pill>}
          {e.slot_at && <Pill><Clock className="h-3 w-3" />{fmt(e.slot_at)}</Pill>}
          {e.yt_id && <Pill className="text-red-500"><Youtube className="h-3 w-3" />YouTube</Pill>}
        </div>
        {active && <><Progress value={e.progress} /><p className="truncate text-[11px] text-muted">{e.step}</p></>}
        {(e.status === "failed" || e.status === "needs_review") && <p className="line-clamp-2 text-[11px] text-orange-500">{e.error}</p>}
      </div>
    </motion.button>
  );
}

export function EpisodeModal({ id, onClose }: { id: number | null; onClose: () => void }) {
  const qc = useQueryClient();
  const { data: e } = useQuery({ queryKey: ["episode", id], queryFn: () => api.episode(id!), enabled: !!id });
  const [tab, setTab] = useState<"watch" | "script">("watch");
  const inv = () => { qc.invalidateQueries({ queryKey: ["episodes"] }); qc.invalidateQueries({ queryKey: ["episode", id] }); qc.invalidateQueries({ queryKey: ["channels"] }); };
  const act = (fn: () => Promise<unknown>, ok: string) => ({ mutationFn: fn, onSuccess: () => { inv(); toast.success(ok); }, onError: (x: Error) => toast.error(x.message) });
  const retry = useMutation(act(() => api.retryEpisode(id!), "Yeniden kuyruğa alındı"));
  const approve = useMutation(act(() => api.approveEpisode(id!), "Onaylandı — üretim devam ediyor"));
  const pub = useMutation(act(() => api.publishNow(id!), "YouTube'a yüklendi"));
  const cancel = useMutation(act(() => api.cancelEpisode(id!), "İptal edildi"));
  const del = useMutation(act(() => api.deleteEpisode(id!), "Silindi"));
  if (!e) return <Modal open={false} onClose={onClose} title="">{null}</Modal>;
  const active = EP_STATUS[e.status]?.active;
  return (
    <Modal open={!!id} onClose={onClose} wide title={<span className="flex items-center gap-3"><span className="line-clamp-1">{e.title}</span><EpBadge s={e.status} /></span>}>
      <div className="mb-4"><Segmented value={tab} onChange={setTab} options={[{ id: "watch", label: "İzle & yayın" }, { id: "script", label: "Senaryo" }]} /></div>
      {tab === "watch" ? (
        <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
          <div className="space-y-4">
            <div className={cn("overflow-hidden rounded-2xl bg-black", e.kind === "short" ? "mx-auto aspect-[9/16] max-w-[300px]" : "aspect-video")}>
              {e.video_url ? <video key={e.video_url} src={e.video_url} poster={e.thumb_url ?? undefined} controls className="h-full w-full" />
                : <div className="grid h-full place-items-center p-6 text-sm text-white/70">{active ? <div className="w-full max-w-sm space-y-3"><Progress value={e.progress} /><p className="text-center">{e.step}</p></div> : "Video yok"}</div>}
            </div>
            {e.chapters.length > 0 && (
              <div className="card p-4"><div className="label">Bölümler</div>
                <div className="grid gap-1 sm:grid-cols-2">{e.chapters.map((c) => <div key={c.t} className="flex gap-3 text-sm"><span className="w-12 font-mono text-xs text-muted">{mmss(c.t)}</span>{c.title}</div>)}</div>
              </div>
            )}
          </div>
          <div className="space-y-4">
            {e.thumb_url && <img src={e.thumb_url} className="w-full rounded-xl border border-line" />}
            {e.quality && (
              <div className="card space-y-2 p-4 text-sm">
                <div className="flex items-center justify-between"><span className="label mb-0">Kalite jürisi</span><span className="font-display text-xl font-extrabold">{e.quality.score.toFixed(1)}</span></div>
                {([["Hook", e.quality.hook], ["Akış", e.quality.flow], ["Özgünlük", e.quality.originality], ["Doğruluk riski", e.quality.accuracy_risk]] as const).map(([k, v]) => (
                  <div key={k} className="flex items-center gap-2 text-xs"><span className="w-24 text-muted">{k}</span>
                    <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-elev"><div className={cn("h-full rounded-full", k === "Doğruluk riski" ? "bg-rose-500" : "grad-bg")} style={{ width: `${v * 10}%` }} /></div></div>
                ))}
                {e.quality.issues.length > 0 && <ul className="list-disc pl-4 text-xs text-muted">{e.quality.issues.slice(0, 4).map((x) => <li key={x}>{x}</li>)}</ul>}
              </div>
            )}
            <div className="space-y-1 text-sm">
              {e.slot_at && <div className="flex justify-between"><span className="text-muted">Yayın slotu</span><span>{fmt(e.slot_at)}</span></div>}
              {e.published_at && <div className="flex justify-between"><span className="text-muted">Yayınlandı</span><span>{fmt(e.published_at)}</span></div>}
            </div>
            <div className="flex flex-wrap gap-2">
              {e.yt_id && !e.yt_id.startsWith("dry") && <a href={`https://youtu.be/${e.yt_id}`} target="_blank" rel="noreferrer"><Button icon={<ExternalLink className="h-4 w-4" />}>YouTube'da aç</Button></a>}
              {e.status === "ready" && !e.yt_id && <Button variant="primary" icon={<Send className="h-4 w-4" />} loading={pub.isPending} onClick={() => pub.mutate()}>Şimdi yayınla</Button>}
              {e.status === "needs_review" && <Button variant="primary" icon={<ShieldAlert className="h-4 w-4" />} loading={approve.isPending} onClick={() => approve.mutate()}>İnceledim, devam et</Button>}
              {active ? <Button variant="danger" icon={<Ban className="h-4 w-4" />} onClick={() => cancel.mutate()}>İptal</Button>
                : ["failed", "cancelled", "needs_review"].includes(e.status) && <Button icon={<RefreshCw className="h-4 w-4" />} onClick={() => retry.mutate()}>Tekrar dene</Button>}
              {!active && !e.yt_id && <Button variant="ghost" icon={<Trash2 className="h-4 w-4" />} onClick={() => { if (confirm("Bölüm silinsin mi?")) { del.mutate(); onClose(); } }}>Sil</Button>}
            </div>
          </div>
        </div>
      ) : (
        <div className="space-y-5">
          {e.script?.chapters.map((c, ci) => (
            <div key={ci}>
              <h4 className="mb-2 font-display font-bold">{ci + 1}. {c.title}</h4>
              <div className="space-y-1.5">
                {c.segments.map((s, si) => (
                  <div key={si} className="flex gap-3 text-sm">
                    <span className={cn("mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-md", s.kind === "presenter" ? "grad-bg text-white" : "bg-elev text-muted")}>
                      {s.kind === "presenter" ? <Play className="h-3 w-3" /> : <Film className="h-3 w-3" />}</span>
                    <p className="leading-relaxed">{s.text}{s.lower_third && <span className="ml-2 rounded bg-elev px-1.5 py-0.5 text-[11px] text-muted">{s.lower_third}</span>}</p>
                  </div>
                ))}
              </div>
            </div>
          ))}
          {!e.script && <p className="text-sm text-muted">Senaryo henüz yazılmadı.</p>}
          {e.srt_url && <a href={e.srt_url} className="inline-flex items-center gap-1 text-sm text-brand"><Check className="h-4 w-4" />Altyazı (SRT)</a>}
        </div>
      )}
    </Modal>
  );
}
