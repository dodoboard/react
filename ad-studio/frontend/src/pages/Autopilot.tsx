import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Bot, Clock, Pencil, Play, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { FormatPicker, FORMATS, I2VPicker } from "@/components/AvatarPicker";
import { Button, Empty, Field, Modal, PageHeader, Pill, Toggle } from "@/components/ui";
import { api, type Rule } from "@/lib/api";
import { cn, PLATFORMS } from "@/lib/utils";

const BLANK: Partial<Rule> = { name: "Gece üretimi", enabled: true, brand_id: null, kind: "single", collection_type: "top_list", products_per_video: 3, product_ids: [], videos_per_day: 3, run_hour: 2, platform: "tiktok",
  language: "tr", format: "broll", avatar: "", i2v_mode: "off", auto_schedule: true };

function RuleForm({ initial, open, onClose }: { initial: Partial<Rule> | null; open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const { data: allProducts } = useQuery({ queryKey: ["products"], queryFn: () => api.products() });
  const { data: brands } = useQuery({ queryKey: ["brands"], queryFn: api.brands });
  const [r, setR] = useState<Partial<Rule>>(BLANK);
  useEffect(() => { if (open) setR(initial ?? BLANK); }, [open, initial]);
  const save = useMutation({
    mutationFn: () => api.saveRule(r),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["rules"] }); toast.success("Otopilot kaydedildi"); onClose(); },
    onError: (e: Error) => toast.error(e.message),
  });
  const ids = r.product_ids ?? [];
  const products = (allProducts ?? []).filter((p) => !r.brand_id || p.brand_id === r.brand_id);
  return (
    <Modal open={open} onClose={onClose} wide title={r.id ? "Otopilotu düzenle" : "Yeni otopilot"}
      footer={<><Button variant="ghost" onClick={onClose}>Vazgeç</Button><Button variant="primary" loading={save.isPending} onClick={() => save.mutate()}>Kaydet</Button></>}>
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-4">
          <Field label="Ad"><input className="input" value={r.name} onChange={(e) => setR({ ...r, name: e.target.value })} /></Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Firma"><select className="input" value={r.brand_id ?? ""} onChange={(e) => setR({ ...r, brand_id: e.target.value ? Number(e.target.value) : null, product_ids: [] })}>
              <option value="">Tüm firmalar</option>{brands?.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select></Field>
            <Field label="Video tipi"><select className="input" value={r.kind === "collection" ? r.collection_type : "single"}
              onChange={(e) => setR(e.target.value === "single" ? { ...r, kind: "single" } : { ...r, kind: "collection", collection_type: e.target.value })}>
              <option value="single">Tek ürün</option><option value="top_list">Çok ürün · Top liste</option><option value="bundle">Çok ürün · Kombin</option>
              <option value="sale">Çok ürün · İndirim vitrini</option><option value="gift_guide">Çok ürün · Hediye rehberi</option><option value="comparison">Çok ürün · Karşılaştırma</option></select></Field>
          </div>
          {r.kind === "collection" && <Field label={`Video başına ürün: ${r.products_per_video}`}><input type="range" min={2} max={6} value={r.products_per_video} onChange={(e) => setR({ ...r, products_per_video: +e.target.value })} className="w-full accent-violet-500" /></Field>}
          <div className="grid grid-cols-2 gap-4">
            <Field label="Günlük video"><input type="number" min={1} max={30} className="input" value={r.videos_per_day} onChange={(e) => setR({ ...r, videos_per_day: +e.target.value })} /></Field>
            <Field label="Üretim saati" hint="GPU boşken (gece)"><select className="input" value={r.run_hour} onChange={(e) => setR({ ...r, run_hour: +e.target.value })}>
              {Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{String(h).padStart(2, "0")}:00</option>)}</select></Field>
            <Field label="Platform"><select className="input" value={r.platform} onChange={(e) => setR({ ...r, platform: e.target.value })}>{PLATFORMS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}</select></Field>
            <Field label="Dil"><select className="input" value={r.language} onChange={(e) => setR({ ...r, language: e.target.value })}>{[["tr", "Türkçe"], ["en", "English"], ["de", "Deutsch"]].map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
          </div>
          <Toggle checked={!!r.auto_schedule} onChange={(v) => setR({ ...r, auto_schedule: v })} label="Bitenleri otomatik planla" desc="12:00 / 19:00 / 21:00 boş slotlarına, hook skoru yüksek olan önce." />
          <Toggle checked={!!r.enabled} onChange={(v) => setR({ ...r, enabled: v })} label="Aktif" />
          <I2VPicker value={r.i2v_mode ?? "off"} onChange={(v) => setR({ ...r, i2v_mode: v })} />
        </div>
        <div className="space-y-4">
          <div>
            <span className="label">Ürün havuzu ({ids.length ? `${ids.length} seçili` : "tüm aktif ürünler"})</span>
            <div className="grid max-h-56 gap-2 overflow-y-auto pr-1 sm:grid-cols-2">
              {products.map((p) => (
                <button key={p.id} type="button" onClick={() => setR({ ...r, product_ids: ids.includes(p.id) ? ids.filter((x) => x !== p.id) : [...ids, p.id] })}
                  className={cn("flex items-center gap-2 rounded-xl border p-2 text-left text-xs transition", ids.includes(p.id) ? "border-brand bg-brand/10" : "border-line bg-elev/30 hover:border-brand/40")}>
                  <div className="h-9 w-9 shrink-0 overflow-hidden rounded-lg bg-white">{p.image_url && <img src={p.image_url} className="h-full w-full object-contain" />}</div>
                  <span className="line-clamp-2">{p.name}</span>
                </button>
              ))}
            </div>
            <p className="mt-1.5 text-xs text-muted">Ürünler video başı gelire göre ağırlıklı seçilir; %20 keşif payı yeni ürünlere şans verir.</p>
          </div>
          <FormatPicker format={r.format ?? "broll"} avatar={r.avatar ?? ""} onChange={(f, a) => setR({ ...r, format: f, avatar: a })} />
        </div>
      </div>
    </Modal>
  );
}

export default function Autopilot() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["rules"], queryFn: api.rules });
  const { data: brands } = useQuery({ queryKey: ["brands"], queryFn: api.brands });
  const [edit, setEdit] = useState<Partial<Rule> | null>(null);
  const [open, setOpen] = useState(false);
  const run = useMutation({ mutationFn: api.runRule, onSuccess: (r) => { toast.success(`${r.campaigns.length} kampanya başlatıldı`); qc.invalidateQueries({ queryKey: ["rules"] }); }, onError: (e: Error) => toast.error(e.message) });
  const del = useMutation({ mutationFn: api.deleteRule, onSuccess: () => qc.invalidateQueries({ queryKey: ["rules"] }) });
  const toggle = useMutation({ mutationFn: (r: Rule) => api.saveRule({ ...r, enabled: !r.enabled }), onSuccess: () => qc.invalidateQueries({ queryKey: ["rules"] }) });

  return (
    <>
      <PageHeader eyebrow="Otomasyon" title="Otopilot" desc="Her gece seçtiğin ürünlerden kampanya üretir, kazanan hook türlerini öğrenerek yazar, bitenleri en iyi saatlere planlar. Uygulama açık kalmalı."
        actions={<Button variant="primary" icon={<Plus className="h-4 w-4" />} onClick={() => { setEdit(null); setOpen(true); }}>Yeni kural</Button>} />
      {data?.length === 0 && <Empty icon={<Bot className="h-6 w-6" />} title="Otopilot kapalı" desc="Bir kural oluştur: örn. her gece 02:00'de 3 video, TikTok, otomatik planlama." action={<Button variant="primary" onClick={() => setOpen(true)}>Kural oluştur</Button>} />}
      <div className="grid gap-4 lg:grid-cols-2">
        {data?.map((r, i) => (
          <motion.div key={r.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }} className="card p-5">
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className={cn("grid h-11 w-11 place-items-center rounded-xl text-white", r.enabled ? "grad-bg shadow-glow" : "bg-zinc-600")}><Bot className="h-5 w-5" /></div>
                <div><h3 className="font-display text-lg font-bold">{r.name}</h3>
                  <p className="flex items-center gap-1.5 text-xs text-muted"><Clock className="h-3 w-3" />Her gün {String(r.run_hour).padStart(2, "0")}:00 · son: {r.last_run ?? "hiç"}</p></div>
              </div>
              <button onClick={() => toggle.mutate(r)} className={cn("relative h-6 w-11 shrink-0 rounded-full transition", r.enabled ? "grad-bg" : "bg-line")}>
                <span className={cn("absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all", r.enabled ? "right-0.5" : "left-0.5")} />
              </button>
            </div>
            <div className="mt-4 flex flex-wrap gap-1.5">
              <Pill>{r.videos_per_day} video/gün</Pill><Pill>{PLATFORMS.find((p) => p.id === r.platform)?.label}</Pill>
              <Pill>{FORMATS.find((f) => f.id === r.format)?.label}</Pill>
              {r.kind === "collection" && <Pill>{r.products_per_video} ürün/video</Pill>}
              {r.brand_id && <Pill className="text-brand">{brands?.find((b) => b.id === r.brand_id)?.name}</Pill>}
              <Pill>{r.product_ids.length ? `${r.product_ids.length} ürün` : "Tüm ürünler"}</Pill>
              {r.i2v_mode !== "off" && <Pill>i2v: {r.i2v_mode === "hook" ? "hook" : "tümü"}</Pill>}
              {r.auto_schedule && <Pill className="text-sky-500">Oto-plan</Pill>}
            </div>
            <div className="mt-4 grid grid-cols-2 gap-3">
              <div className="rounded-xl bg-elev/50 p-3"><div className="text-xs text-muted">Kampanya</div><div className="font-display text-xl font-extrabold">{r.campaigns}</div></div>
              <div className="rounded-xl bg-elev/50 p-3"><div className="text-xs text-muted">Video</div><div className="font-display text-xl font-extrabold">{r.videos}</div></div>
            </div>
            <div className="mt-4 flex gap-2">
              <Button size="sm" variant="primary" icon={<Play className="h-3.5 w-3.5" />} loading={run.isPending} onClick={() => run.mutate(r.id)}>Şimdi çalıştır</Button>
              <Button size="sm" icon={<Pencil className="h-3.5 w-3.5" />} onClick={() => { setEdit(r); setOpen(true); }}>Düzenle</Button>
              <Button size="sm" variant="danger" className="ml-auto" icon={<Trash2 className="h-3.5 w-3.5" />} onClick={() => confirm("Kural silinsin mi?") && del.mutate(r.id)} />
            </div>
          </motion.div>
        ))}
      </div>
      <RuleForm open={open} initial={edit} onClose={() => setOpen(false)} />
    </>
  );
}
