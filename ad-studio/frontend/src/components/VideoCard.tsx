import { useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  Ban, Check, Copy, Download, ExternalLink, Heart, Mic, Pencil, Play, Plus, RefreshCw, Trash2, Wand2, Youtube,
} from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { type AdScript, api, type Video } from "@/lib/api";
import { ANGLES, cn, PLATFORMS, STATUS } from "@/lib/utils";
import { Button, Field, Modal, PhoneFrame, Pill, Progress, Segmented, StatusBadge } from "./ui";

export function useVideoActions() {
  const qc = useQueryClient();
  const refresh = () => { qc.invalidateQueries({ queryKey: ["videos"] }); qc.invalidateQueries({ queryKey: ["campaign"] }); qc.invalidateQueries({ queryKey: ["campaigns"] }); };
  const wrap = <A,>(fn: (a: A) => Promise<unknown>, ok?: string) =>
    useMutation({ mutationFn: fn, onSuccess: () => { refresh(); if (ok) toast.success(ok); }, onError: (e: Error) => toast.error(e.message) });
  return {
    render: wrap((id: number) => api.render(id), "Render kuyruğa alındı"),
    rescript: wrap((id: number) => api.rescript(id), "Yeni senaryo yazılıyor"),
    revoice: wrap((id: number) => api.revoice(id), "Yeniden seslendiriliyor"),
    cancel: wrap((id: number) => api.cancel(id)),
    remove: wrap((id: number) => api.deleteVideo(id), "Silindi"),
    patch: wrap(({ id, ...b }: { id: number } & Record<string, unknown>) => api.patchVideo(id, b)),
    yt: wrap((id: number) => api.ytUpload(id), "YouTube'a yüklendi"),
  };
}

export function VideoCard({ v, onOpen }: { v: Video; onOpen: () => void }) {
  const active = STATUS[v.status].active;
  return (
    <motion.button layout onClick={onOpen} whileHover={{ y: -3 }}
      className="card group relative flex flex-col overflow-hidden text-left transition hover:border-brand/40 hover:shadow-glow">
      <div className="relative aspect-[9/14] overflow-hidden bg-elev">
        {v.thumb_url ? (
          <img src={v.thumb_url} className="h-full w-full object-cover transition duration-500 group-hover:scale-105" loading="lazy" />
        ) : (
          <div className="grid h-full w-full place-items-center bg-gradient-to-br from-brand/20 via-transparent to-brand-2/20 p-5 text-center">
            <p className="font-display text-sm font-bold leading-snug text-fg/80">{v.hook || "Senaryo yazılıyor…"}</p>
          </div>
        )}
        <div className="absolute inset-x-0 top-0 flex items-start justify-between p-2.5">
          <StatusBadge status={v.status} />
          <span className="rounded-lg bg-black/60 px-2 py-0.5 text-[11px] font-bold text-white backdrop-blur">{v.ab_label}</span>
        </div>
        {v.status === "done" && (
          <div className="absolute inset-0 grid place-items-center bg-black/0 opacity-0 transition group-hover:bg-black/30 group-hover:opacity-100">
            <div className="grid h-12 w-12 place-items-center rounded-full bg-white/90 text-black shadow-xl"><Play className="ml-0.5 h-5 w-5 fill-current" /></div>
          </div>
        )}
        {v.duration && <span className="absolute bottom-2 right-2 rounded-md bg-black/70 px-1.5 py-0.5 font-mono text-[10px] text-white">{v.duration.toFixed(1)}s</span>}
        {v.favorite && <Heart className="absolute bottom-2 left-2 h-4 w-4 fill-rose-500 text-rose-500" />}
      </div>
      <div className="space-y-2 p-3">
        <p className="line-clamp-2 text-[13px] font-medium leading-snug">{v.hook || "—"}</p>
        <div className="flex flex-wrap items-center gap-1">
          <Pill>{ANGLES[v.angle] ?? v.angle}</Pill>
          {v.published_at && <Pill className="border-emerald-500/30 text-emerald-500">Yayında</Pill>}
          {v.scheduled_at && !v.published_at && <Pill className="border-sky-500/30 text-sky-500">Planlı</Pill>}
        </div>
        {active && (<><Progress value={v.progress} /><p className="truncate text-[11px] text-muted">{v.step}</p></>)}
        {v.status === "failed" && <p className="line-clamp-2 text-[11px] text-rose-400">{v.error}</p>}
      </div>
    </motion.button>
  );
}

function ScriptEditor({ v, onSaved }: { v: Video; onSaved: () => void }) {
  const [s, setS] = useState<AdScript | null>(v.script);
  const qc = useQueryClient();
  useEffect(() => setS(v.script), [v.script]);
  const save = useMutation({
    mutationFn: async (render: boolean) => { await api.saveScript(v.id, s!); if (render) await api.render(v.id); },
    onSuccess: (_, render) => { toast.success(render ? "Kaydedildi, render başladı" : "Senaryo kaydedildi"); qc.invalidateQueries({ queryKey: ["videos"] }); qc.invalidateQueries({ queryKey: ["campaign"] }); onSaved(); },
    onError: (e: Error) => toast.error(e.message),
  });
  if (!s) return <p className="text-sm text-muted">Senaryo henüz yok.</p>;
  const words = [s.hook, ...s.scenes.map((x) => x.voiceover), s.cta].join(" ").split(/\s+/).filter(Boolean).length;
  const setScene = (i: number, k: keyof AdScript["scenes"][0], val: string) =>
    setS({ ...s, scenes: s.scenes.map((x, j) => (j === i ? { ...x, [k]: val } : x)) });
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between text-xs text-muted">
        <span>{words} kelime · ~{Math.round(words / 2.6)} sn seslendirme</span>
        <span className={cn(words > 95 && "text-amber-500")}>{words > 95 ? "Uzun — kısaltmayı düşün" : "İdeal aralık 55-90"}</span>
      </div>
      <Field label="Hook (ilk 2 saniye)"><textarea className="input min-h-[60px] font-medium" value={s.hook} onChange={(e) => setS({ ...s, hook: e.target.value })} /></Field>
      {s.scenes.map((sc, i) => (
        <div key={i} className="rounded-xl border border-line bg-elev/30 p-3.5">
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-muted"><span className="grid h-5 w-5 place-items-center rounded-md grad-bg text-[10px] text-white">{i + 1}</span> Sahne</div>
          <div className="grid gap-3 md:grid-cols-2">
            <Field label="Seslendirme"><textarea className="input min-h-[72px]" value={sc.voiceover} onChange={(e) => setScene(i, "voiceover", e.target.value)} /></Field>
            <Field label="Görsel prompt (EN)"><textarea className="input min-h-[72px] font-mono text-xs" value={sc.visual_prompt} onChange={(e) => setScene(i, "visual_prompt", e.target.value)} /></Field>
          </div>
          <Field label="Ekran yazısı" className="mt-3"><input className="input" value={sc.on_screen_text} onChange={(e) => setScene(i, "on_screen_text", e.target.value)} /></Field>
        </div>
      ))}
      <div className="grid gap-3 md:grid-cols-2">
        <Field label="CTA"><input className="input" value={s.cta} onChange={(e) => setS({ ...s, cta: e.target.value })} /></Field>
        <Field label="Başlık (YouTube)"><input className="input" value={s.title} onChange={(e) => setS({ ...s, title: e.target.value })} /></Field>
      </div>
      <Field label="Açıklama"><textarea className="input" value={s.caption} onChange={(e) => setS({ ...s, caption: e.target.value })} /></Field>
      <Field label="Hashtag'ler (virgülle)"><input className="input" value={s.hashtags.join(", ")} onChange={(e) => setS({ ...s, hashtags: e.target.value.split(",").map((x) => x.trim()).filter(Boolean) })} /></Field>
      <div className="flex justify-end gap-2 pt-2">
        <Button onClick={() => save.mutate(false)} loading={save.isPending}>Kaydet</Button>
        <Button variant="primary" icon={<Wand2 className="h-4 w-4" />} onClick={() => save.mutate(true)} loading={save.isPending}>Kaydet & Render</Button>
      </div>
    </div>
  );
}

export function VideoModal({ v, onClose }: { v: Video | null; onClose: () => void }) {
  const a = useVideoActions();
  const [tab, setTab] = useState<"preview" | "script">("preview");
  const [copied, setCopied] = useState(false);
  const [when, setWhen] = useState("");
  useEffect(() => {
    if (v) { setTab(v.status === "scripted" ? "script" : "preview"); setWhen(v.scheduled_at?.slice(0, 16) ?? ""); }
  }, [v?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!v) return <Modal open={false} onClose={onClose} title="">{null}</Modal>;
  const fullCaption = [v.script?.title, v.caption, v.tracking_url].filter(Boolean).join("\n\n");
  const busy = STATUS[v.status].active;
  return (
    <Modal open={!!v} onClose={onClose} wide title={<span className="flex items-center gap-3">Video #{v.id} <StatusBadge status={v.status} /></span>}>
      <div className="mb-5"><Segmented value={tab} onChange={setTab} options={[{ id: "preview", label: "Önizleme & Yayın" }, { id: "script", label: "Senaryo Düzenle" }]} /></div>
      {tab === "script" ? <ScriptEditor v={v} onSaved={() => setTab("preview")} /> : (
        <div className="grid gap-8 md:grid-cols-[300px_1fr]">
          <PhoneFrame>
            {v.video_url ? <video key={v.video_url + v.updated_at} src={v.video_url} poster={v.thumb_url ?? undefined} controls autoPlay playsInline className="h-full w-full object-cover" />
              : <div className="grid h-full place-items-center p-6 text-center text-sm text-muted">{busy ? <div className="w-full space-y-3"><Progress value={v.progress} /><p>{v.step}</p></div> : "Henüz render edilmedi"}</div>}
          </PhoneFrame>
          <div className="space-y-5">
            <div>
              <div className="label">Hook</div>
              <p className="font-display text-xl font-bold leading-snug">{v.hook}</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                <Pill>{ANGLES[v.angle] ?? v.angle}</Pill><Pill>Varyant {v.ab_label}</Pill><Pill>subid: <span className="font-mono">{v.subid}</span></Pill>
                {v.duration && <Pill>{v.duration.toFixed(1)} sn</Pill>}
              </div>
            </div>
            <div>
              <div className="mb-1.5 flex items-center justify-between"><span className="label mb-0">Paylaşım metni</span>
                <button className="flex items-center gap-1 text-xs font-medium text-brand" onClick={() => { navigator.clipboard.writeText(fullCaption); setCopied(true); setTimeout(() => setCopied(false), 1500); }}>
                  {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}{copied ? "Kopyalandı" : "Kopyala"}
                </button>
              </div>
              <pre className="max-h-44 overflow-auto whitespace-pre-wrap rounded-xl border border-line bg-elev/40 p-3 font-sans text-[13px] leading-relaxed text-fg/90">{fullCaption}</pre>
            </div>
            <div className="grid gap-3 rounded-xl border border-line bg-elev/30 p-4 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
              <Field label="Platform">
                <select className="input" value={v.platform} onChange={(e) => a.patch.mutate({ id: v.id, platform: e.target.value })}>
                  {PLATFORMS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
                </select>
              </Field>
              <Field label="Yayın zamanı"><input type="datetime-local" className="input" value={when} onChange={(e) => setWhen(e.target.value)} /></Field>
              <Button icon={<Plus className="h-4 w-4" />} disabled={!when} onClick={() => a.patch.mutate({ id: v.id, scheduled_at: when })}>Planla</Button>
            </div>
            <div className="flex flex-wrap gap-2">
              {v.video_url && <a href={`/api/videos/${v.id}/package`}><Button variant="primary" icon={<Download className="h-4 w-4" />}>Yayın paketi (.zip)</Button></a>}
              {v.video_url && v.platform === "youtube" && !v.published_at && <Button icon={<Youtube className="h-4 w-4" />} loading={a.yt.isPending} onClick={() => a.yt.mutate(v.id)}>YouTube'a yükle</Button>}
              {v.video_url && !v.published_at && <Button icon={<Check className="h-4 w-4" />} onClick={() => a.patch.mutate({ id: v.id, published_at: new Date().toISOString().slice(0, 19) })}>Yayınlandı işaretle</Button>}
              {v.publish_url && <a href={v.publish_url} target="_blank" rel="noreferrer"><Button icon={<ExternalLink className="h-4 w-4" />}>Yayını aç</Button></a>}
              <Button variant="ghost" icon={<Heart className={cn("h-4 w-4", v.favorite && "fill-rose-500 text-rose-500")} />} onClick={() => a.patch.mutate({ id: v.id, favorite: !v.favorite })}>Favori</Button>
            </div>
            <div className="flex flex-wrap gap-2 border-t border-line pt-4">
              {busy ? <Button variant="danger" icon={<Ban className="h-4 w-4" />} onClick={() => a.cancel.mutate(v.id)}>İptal</Button> : (<>
                <Button size="sm" icon={<Pencil className="h-3.5 w-3.5" />} onClick={() => setTab("script")}>Düzenle</Button>
                <Button size="sm" icon={<RefreshCw className="h-3.5 w-3.5" />} onClick={() => a.render.mutate(v.id)}>{v.status === "scripted" ? "Render et" : "Yeniden render"}</Button>
                {v.video_url && <Button size="sm" icon={<Mic className="h-3.5 w-3.5" />} onClick={() => a.revoice.mutate(v.id)}>Sesi yenile</Button>}
                <Button size="sm" icon={<Wand2 className="h-3.5 w-3.5" />} onClick={() => a.rescript.mutate(v.id)}>Yeni senaryo</Button>
                <Button size="sm" variant="danger" className="ml-auto" icon={<Trash2 className="h-3.5 w-3.5" />} onClick={() => { if (confirm("Video silinsin mi?")) { a.remove.mutate(v.id); onClose(); } }}>Sil</Button>
              </>)}
            </div>
          </div>
        </div>
      )}
    </Modal>
  );
}
