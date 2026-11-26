import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { Ban, Check, FileText, Film, ImageIcon, ListVideo, Mic, RefreshCw } from "lucide-react";
import { useState } from "react";
import { useVideoActions, VideoModal } from "@/components/VideoCard";
import { Button, Empty, PageHeader, Progress, Segmented, StatusBadge } from "@/components/ui";
import { useBrand } from "@/lib/brand";
import { api, type VideoStatus } from "@/lib/api";
import { ago, cn, STATUS } from "@/lib/utils";

const PIPE: { key: VideoStatus; label: string; icon: typeof FileText }[] = [
  { key: "scripting", label: "Senaryo", icon: FileText },
  { key: "visuals", label: "Görsel", icon: ImageIcon },
  { key: "voice", label: "Ses", icon: Mic },
  { key: "composing", label: "Montaj", icon: Film },
];
const ORDER: VideoStatus[] = ["queued", "scripting", "scripted", "visuals", "voice", "composing", "done"];

function Stages({ status }: { status: VideoStatus }) {
  const cur = ORDER.indexOf(status);
  return (
    <div className="flex items-center gap-1">
      {PIPE.map((p, i) => {
        const idx = ORDER.indexOf(p.key);
        const done = status === "done" || cur > idx;
        const now = status === p.key;
        return (
          <div key={p.key} className="flex items-center gap-1">
            <span title={p.label} className={cn("grid h-7 w-7 place-items-center rounded-lg transition",
              done ? "grad-bg text-white" : now ? "border border-brand bg-brand/15 text-brand" : "border border-line text-muted/50")}>
              {done ? <Check className="h-3.5 w-3.5" /> : <p.icon className={cn("h-3.5 w-3.5", now && "animate-pulse")} />}
            </span>
            {i < PIPE.length - 1 && <span className={cn("h-px w-3", done ? "bg-brand" : "bg-line")} />}
          </div>
        );
      })}
    </div>
  );
}

export default function Queue() {
  const { brandId } = useBrand();
  const [filter, setFilter] = useState<"active" | "failed" | "all">("active");
  const q = filter === "active" ? "?status=queued,scripting,visuals,voice,composing" : filter === "failed" ? "?status=failed,cancelled" : "?limit=100";
  const { data } = useQuery({ queryKey: ["videos", "queue", filter, brandId], queryFn: () => api.videos(q, brandId), refetchInterval: 15_000 });
  const { data: h } = useQuery({ queryKey: ["health"], queryFn: api.health });
  const a = useVideoActions();
  const [open, setOpen] = useState<number | null>(null);
  const list = filter === "active" ? data?.filter((v) => STATUS[v.status].active) : data;

  return (
    <>
      <PageHeader eyebrow="Canlı" title="Üretim kuyruğu" desc="Tek GPU worker: senaryolar toplu yazılır, LLM VRAM'den boşaltılır, sonra görseller ComfyUI'da sırayla üretilir."
        actions={<Segmented value={filter} onChange={setFilter} options={[{ id: "active", label: "Aktif" }, { id: "failed", label: "Hatalı" }, { id: "all", label: "Tümü" }]} />} />
      {h && <div className="mb-4 text-xs text-muted">{h.queue.running ? `Çalışıyor · ${h.queue.current.length} video bu partide` : "Boşta"} · {h.queue.pending_jobs} parti bekliyor</div>}
      {list?.length === 0 && <Empty icon={<ListVideo className="h-6 w-6" />} title={filter === "failed" ? "Hata yok" : "Kuyruk boş"} desc="Yeni bir kampanya başlattığında videolar burada canlı ilerler." />}
      <div className="space-y-2.5">
        <AnimatePresence initial={false}>
          {list?.map((v) => (
            <motion.div key={v.id} layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, x: 20 }}
              className="card flex flex-col gap-4 p-4 sm:flex-row sm:items-center">
              <button onClick={() => setOpen(v.id)} className="flex min-w-0 flex-1 items-center gap-4 text-left">
                <div className="h-16 w-10 shrink-0 overflow-hidden rounded-lg bg-elev">{v.thumb_url && <img src={v.thumb_url} className="h-full w-full object-cover" />}</div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2"><span className="font-mono text-xs text-muted">#{v.id}</span><StatusBadge status={v.status} /><span className="truncate text-xs text-muted">{v.campaign_name}</span></div>
                  <p className="mt-1 truncate text-sm font-medium">{v.hook || "Senaryo bekleniyor…"}</p>
                  {v.status === "failed" ? <p className="truncate text-xs text-rose-400">{v.error}</p> : <p className="text-xs text-muted">{v.step} · {ago(v.updated_at)}</p>}
                </div>
              </button>
              <div className="flex items-center gap-4">
                <Stages status={v.status} />
                <div className="w-28"><Progress value={v.progress} /><div className="mt-1 text-right font-mono text-[10px] text-muted">{Math.round(v.progress)}%</div></div>
                {STATUS[v.status].active ? <Button size="sm" variant="ghost" icon={<Ban className="h-3.5 w-3.5" />} onClick={() => a.cancel.mutate(v.id)} />
                  : (v.status === "failed" || v.status === "cancelled") && <Button size="sm" icon={<RefreshCw className="h-3.5 w-3.5" />} onClick={() => a.render.mutate(v.id)}>Tekrar</Button>}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
      <VideoModal v={data?.find((x) => x.id === open) ?? null} onClose={() => setOpen(null)} />
    </>
  );
}
