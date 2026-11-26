import { useMutation, useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { AlertTriangle, CheckCircle2, CircleDashed, Copy, FlaskConical, RefreshCw, Stethoscope, XCircle } from "lucide-react";
import { toast } from "sonner";
import { Button, PageHeader, Pill, Skeleton } from "@/components/ui";
import { api, type DoctorCheck } from "@/lib/api";
import { cn } from "@/lib/utils";

const ICON = {
  ok: <CheckCircle2 className="h-5 w-5 text-emerald-500" />,
  warn: <AlertTriangle className="h-5 w-5 text-amber-500" />,
  fail: <XCircle className="h-5 w-5 text-rose-500" />,
  skip: <CircleDashed className="h-5 w-5 text-muted" />,
};

function Row({ c }: { c: DoctorCheck }) {
  const cmd = /^(python|pip|ollama|winget)\b/.test(c.fix);
  return (
    <div className="flex gap-3 border-b border-line/50 px-5 py-3.5 last:border-0">
      <div className="mt-0.5 shrink-0">{ICON[c.status]}</div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2"><span className="font-medium">{c.label}</span>{c.detail && <span className="text-xs text-muted">{c.detail}</span>}</div>
        {c.fix && (
          <div className="mt-1.5 flex items-center gap-2">
            {cmd ? <code className="min-w-0 flex-1 truncate rounded-lg bg-elev px-2.5 py-1.5 font-mono text-xs">{c.fix}</code>
              : <p className="text-xs text-muted">{c.fix}</p>}
            {cmd && <button onClick={() => { navigator.clipboard.writeText(c.fix); toast.success("Kopyalandı"); }} className="rounded-lg p-1.5 text-muted hover:text-fg"><Copy className="h-3.5 w-3.5" /></button>}
          </div>
        )}
      </div>
    </div>
  );
}

export default function Doctor() {
  const { data, refetch, isFetching } = useQuery({ queryKey: ["doctor"], queryFn: () => api.doctor(false) });
  const deep = useMutation({ mutationFn: () => api.doctor(true), onSuccess: () => refetch() });
  const smoke = useMutation({ mutationFn: api.smoke, onError: (e: Error) => toast.error(e.message) });
  const groups = data ? [...new Set(data.checks.map((c) => c.group))] : [];
  const count = (s: string) => data?.checks.filter((c) => c.status === s).length ?? 0;

  return (
    <>
      <PageHeader eyebrow="Sistem" title="Sistem Durumu" desc="Bu makinede her şey gerçekten çalışıyor mu? FFmpeg, fontlar, Ollama, ComfyUI node'ları ve model dosyaları, ses ve YouTube tek ekranda."
        actions={<>
          <Button icon={<RefreshCw className={cn("h-4 w-4", (isFetching || deep.isPending) && "animate-spin")} />} onClick={() => deep.mutate()}>Derin kontrol</Button>
          <Button variant="primary" icon={<FlaskConical className="h-4 w-4" />} loading={smoke.isPending} onClick={() => smoke.mutate()}>Gerçek testi çalıştır</Button>
        </>} />
      <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
        {(["ok", "warn", "fail", "skip"] as const).map((s) => (
          <div key={s} className="card flex items-center gap-3 p-4">{ICON[s]}<div><div className="font-display text-2xl font-extrabold">{count(s)}</div>
            <div className="text-[11px] uppercase tracking-wider text-muted">{{ ok: "Hazır", warn: "Uyarı", fail: "Eksik", skip: "Atlandı" }[s]}</div></div></div>
        ))}
      </div>
      {data?.dry_run && <div className="mb-6 rounded-2xl border border-amber-500/30 bg-amber-500/10 p-4 text-sm">Uygulama DEMO modunda çalışıyor; kontroller yine de gerçek makineyi denetler. Gerçek üretim için .env → ADF_DRY_RUN=0.</div>}

      {smoke.data && (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="card mb-6 grid gap-5 p-5 lg:grid-cols-[1fr_360px]">
          <div>
            <h3 className="mb-3 flex items-center gap-2 font-display font-bold"><Stethoscope className="h-4 w-4 text-brand" />Duman testi</h3>
            <div className="space-y-2">{smoke.data.steps.map((s) => (
              <div key={s.name} className="flex items-start gap-3 text-sm">{s.ok ? ICON.ok : ICON.fail}
                <div className="min-w-0 flex-1"><div className="font-medium">{s.name} <span className="font-mono text-xs text-muted">{s.seconds} sn</span></div>
                  <div className="break-words text-xs text-muted">{s.detail}</div></div></div>
            ))}</div>
          </div>
          <div className="space-y-3">
            {smoke.data.video_url ? <video src={smoke.data.video_url} controls className="w-full rounded-xl bg-black" />
              : smoke.data.image_url ? <img src={smoke.data.image_url} className="w-full rounded-xl" /> : <div className="grid aspect-video place-items-center rounded-xl bg-elev text-sm text-muted">Çıktı yok</div>}
          </div>
        </motion.div>
      )}

      <div className="grid gap-6 xl:grid-cols-2">
        {!data && Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-48" />)}
        {groups.map((g) => {
          const items = data!.checks.filter((c) => c.group === g);
          const worst = items.some((c) => c.status === "fail") ? "fail" : items.some((c) => c.status === "warn") ? "warn" : "ok";
          return (
            <div key={g} className="card overflow-hidden">
              <div className="flex items-center justify-between border-b border-line px-5 py-3"><h3 className="font-display font-bold">{g}</h3>
                <Pill className={cn(worst === "ok" ? "text-emerald-500" : worst === "warn" ? "text-amber-500" : "text-rose-500")}>{worst === "ok" ? "Hazır" : worst === "warn" ? "Uyarı" : "Eksik var"}</Pill></div>
              {items.map((c) => <Row key={c.id} c={c} />)}
            </div>
          );
        })}
      </div>
      <p className="mt-6 text-xs text-muted">Eksik modeller için: <code className="rounded bg-elev px-1.5 py-0.5">python scripts/setup_models.py --comfy &lt;ComfyUI klasörü&gt;</code> — ardından bu sayfayı yenileyin.</p>
    </>
  );
}
