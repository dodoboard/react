import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, GripVertical } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { VideoModal } from "@/components/VideoCard";
import { Button, PageHeader } from "@/components/ui";
import { useBrand } from "@/lib/brand";
import { api, type Video } from "@/lib/api";
import { cn } from "@/lib/utils";

const DAYS = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"];
const BEST_HOURS = [12, 19, 21]; // short-form peak engagement windows (local time)
const key = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

export default function Calendar() {
  const qc = useQueryClient();
  const { brandId } = useBrand();
  const { data } = useQuery({ queryKey: ["videos", "calendar", brandId], queryFn: () => api.videos("?status=done&limit=500", brandId) });
  const [month, setMonth] = useState(() => { const d = new Date(); d.setDate(1); return d; });
  const [drag, setDrag] = useState<number | null>(null);
  const [over, setOver] = useState<string | null>(null);
  const [open, setOpen] = useState<number | null>(null);

  const schedule = useMutation({
    mutationFn: ({ id, at }: { id: number; at: string | null }) => api.patchVideo(id, at ? { scheduled_at: at } : { clear_schedule: true }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["videos"] }),
    onError: (e: Error) => toast.error(e.message),
  });

  const cells = useMemo(() => {
    const start = new Date(month);
    start.setDate(1 - ((month.getDay() + 6) % 7));
    return Array.from({ length: 42 }, (_, i) => { const d = new Date(start); d.setDate(start.getDate() + i); return d; });
  }, [month]);

  const byDay = useMemo(() => {
    const m: Record<string, Video[]> = {};
    for (const v of data ?? []) {
      const at = v.published_at ?? v.scheduled_at;
      if (at) (m[at.slice(0, 10)] ??= []).push(v);
    }
    return m;
  }, [data]);
  const unscheduled = (data ?? []).filter((v) => !v.scheduled_at && !v.published_at);

  const drop = (d: Date) => {
    if (drag === null) return;
    const count = byDay[key(d)]?.length ?? 0;
    const hour = BEST_HOURS[count % BEST_HOURS.length];
    schedule.mutate({ id: drag, at: `${key(d)}T${String(hour).padStart(2, "0")}:00:00` });
    setDrag(null); setOver(null);
  };

  return (
    <>
      <PageHeader eyebrow="Planlama" title="Yayın takvimi" desc="Videoları günlere sürükle. Saatler kısa video için en yüksek etkileşim pencerelerine (12:00, 19:00, 21:00) otomatik dağıtılır."
        actions={<div className="flex items-center gap-2">
          <Button size="sm" icon={<ChevronLeft className="h-4 w-4" />} onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))} />
          <span className="w-36 text-center font-display font-bold capitalize">{month.toLocaleDateString("tr-TR", { month: "long", year: "numeric" })}</span>
          <Button size="sm" icon={<ChevronRight className="h-4 w-4" />} onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1))} />
        </div>} />
      <div className="grid gap-6 xl:grid-cols-[260px_1fr]">
        <div className="card h-fit p-4"
          onDragOver={(e) => e.preventDefault()} onDrop={() => { if (drag !== null) schedule.mutate({ id: drag, at: null }); setDrag(null); }}>
          <h3 className="mb-1 font-display font-bold">Planlanmamış</h3>
          <p className="mb-3 text-xs text-muted">{unscheduled.length} hazır video · buraya bırakırsan plandan çıkar</p>
          <div className="max-h-[60vh] space-y-2 overflow-y-auto pr-1">
            {unscheduled.map((v) => (
              <div key={v.id} draggable onDragStart={() => setDrag(v.id)} onDragEnd={() => setDrag(null)}
                className="flex cursor-grab items-center gap-2.5 rounded-xl border border-line bg-elev/40 p-2 transition hover:border-brand/40 active:cursor-grabbing">
                <GripVertical className="h-4 w-4 shrink-0 text-muted" />
                <div className="h-12 w-7 shrink-0 overflow-hidden rounded-md bg-elev">{v.thumb_url && <img src={v.thumb_url} className="h-full w-full object-cover" />}</div>
                <div className="min-w-0"><p className="truncate text-xs font-medium">{v.hook}</p><p className="truncate text-[10px] text-muted">{v.product_name} · {v.ab_label}</p></div>
              </div>
            ))}
          </div>
        </div>
        <div className="card overflow-hidden">
          <div className="grid grid-cols-7 border-b border-line bg-elev/30">{DAYS.map((d) => <div key={d} className="py-2.5 text-center text-xs font-semibold uppercase tracking-wider text-muted">{d}</div>)}</div>
          <div className="grid grid-cols-7">
            {cells.map((d) => {
              const k = key(d);
              const inMonth = d.getMonth() === month.getMonth();
              const today = k === key(new Date());
              const items = byDay[k] ?? [];
              return (
                <div key={k} onDragOver={(e) => { e.preventDefault(); setOver(k); }} onDragLeave={() => setOver(null)} onDrop={() => drop(d)}
                  className={cn("min-h-[110px] border-b border-r border-line/60 p-1.5 transition", !inMonth && "bg-elev/20 opacity-50", over === k && "bg-brand/10 ring-2 ring-inset ring-brand/50")}>
                  <div className={cn("mb-1 grid h-6 w-6 place-items-center rounded-full text-xs font-semibold", today ? "grad-bg text-white" : "text-muted")}>{d.getDate()}</div>
                  <div className="space-y-1">
                    {items.map((v) => (
                      <button key={v.id} draggable={!v.published_at} onDragStart={() => setDrag(v.id)} onClick={() => setOpen(v.id)}
                        className={cn("flex w-full items-center gap-1.5 truncate rounded-md px-1.5 py-1 text-left text-[10px] font-medium",
                          v.published_at ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-300" : "bg-brand/15 text-violet-700 dark:text-violet-200")}>
                        <span className="font-mono opacity-70">{(v.published_at ?? v.scheduled_at)!.slice(11, 16)}</span><span className="truncate">{v.hook}</span>
                      </button>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
      <VideoModal v={data?.find((x) => x.id === open) ?? null} onClose={() => setOpen(null)} />
    </>
  );
}
