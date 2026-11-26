import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { CalendarClock, Plus, Tv, UserRound, Youtube } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Button, Empty, Field, Modal, PageHeader, Pill, Segmented, Toggle } from "@/components/ui";
import { api, type Channel } from "@/lib/api";
import { cn, num } from "@/lib/utils";

const DAYS: [string, string][] = [["*", "Her gün"], ["mon", "Pzt"], ["tue", "Sal"], ["wed", "Çar"], ["thu", "Per"], ["fri", "Cum"], ["sat", "Cmt"], ["sun", "Paz"]];
type Sched = { long: [string, number][]; shorts: [string, number][] };
const BLANK: Partial<Channel> = { name: "", niche: "", language: "tr", character_id: null, format: "both", target_minutes: 8, privacy: "public",
  category_id: "27", default_tags: "", playlist_id: "", lead_days: 2, daily_cap: 3, min_quality: 7, paused: false, run_hour: 1,
  visual_style: "cinematic documentary photography, natural light, rich detail, 35mm film look",
  schedule_json: JSON.stringify({ long: [["tue", 19], ["fri", 19]], shorts: [["*", 12]] }) };

function SlotEditor({ label, value, onChange }: { label: string; value: [string, number][]; onChange: (v: [string, number][]) => void }) {
  const [day, setDay] = useState("tue");
  const [hour, setHour] = useState(19);
  return (
    <div>
      <span className="label">{label}</span>
      <div className="mb-2 flex flex-wrap gap-1.5">
        {value.map(([d, h], i) => (
          <button key={i} onClick={() => onChange(value.filter((_, j) => j !== i))} className="rounded-full border border-brand/40 bg-brand/10 px-2.5 py-1 text-xs font-medium hover:line-through">
            {DAYS.find((x) => x[0] === d)?.[1]} {String(h).padStart(2, "0")}:00 ×</button>
        ))}
        {value.length === 0 && <span className="text-xs text-muted">Slot yok</span>}
      </div>
      <div className="flex gap-2">
        <select className="input w-32" value={day} onChange={(e) => setDay(e.target.value)}>{DAYS.map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
        <select className="input w-24" value={hour} onChange={(e) => setHour(+e.target.value)}>{Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{String(h).padStart(2, "0")}:00</option>)}</select>
        <Button size="sm" onClick={() => onChange([...value, [day, hour]])}>Ekle</Button>
      </div>
    </div>
  );
}

export function ChannelForm({ initial, open, onClose }: { initial: Partial<Channel> | null; open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const [c, setC] = useState<Partial<Channel>>(BLANK);
  const [sch, setSch] = useState<Sched>({ long: [], shorts: [] });
  const [step, setStep] = useState(0);
  const { data: chars } = useQuery({ queryKey: ["characters"], queryFn: api.characters, enabled: open });
  useEffect(() => {
    if (!open) return;
    const v = initial ?? BLANK;
    setC(v);
    setStep(0);
    try { setSch(JSON.parse(v.schedule_json || "{}")); } catch { setSch({ long: [], shorts: [] }); }
  }, [open, initial]);
  const save = useMutation({
    mutationFn: () => api.saveChannel({ ...c, schedule_json: JSON.stringify(sch) }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["channels"] }); toast.success("Kanal kaydedildi"); onClose(); },
    onError: (e: Error) => toast.error(e.message),
  });
  const set = (k: keyof Channel) => (e: { target: { value: string } }) => setC({ ...c, [k]: e.target.value });
  const steps = ["Niş", "Format & takvim", "Karakter", "Otomasyon"];
  return (
    <Modal open={open} onClose={onClose} wide title={c.id ? `${c.name} — ayarlar` : "Yeni belgesel kanalı"}
      footer={<>
        {step > 0 && <Button variant="ghost" onClick={() => setStep(step - 1)}>Geri</Button>}
        {step < steps.length - 1 ? <Button variant="primary" disabled={!c.name || !c.niche} onClick={() => setStep(step + 1)}>Devam</Button>
          : <Button variant="primary" loading={save.isPending} onClick={() => save.mutate()}>Kaydet</Button>}
      </>}>
      <div className="mb-5"><Segmented value={String(step)} onChange={(v) => setStep(+v)} options={steps.map((s, i) => ({ id: String(i), label: `${i + 1}. ${s}` }))} /></div>
      {step === 0 && (
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Kanal adı"><input className="input" value={c.name} onChange={set("name")} placeholder="ör. Kayıp Tarih" /></Field>
          <Field label="Dil"><select className="input" value={c.language} onChange={set("language")}>{[["tr", "Türkçe"], ["en", "English"], ["de", "Deutsch"], ["es", "Español"]].map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
          <Field label="Niş" className="sm:col-span-2" hint="Ne kadar spesifik o kadar iyi: 'antik mühendislik harikaları', 'okyanus keşifleri', 'kayıp şehirler'."><textarea className="input" value={c.niche} onChange={set("niche")} /></Field>
          <Field label="Görsel stil (EN)" className="sm:col-span-2"><input className="input text-xs" value={c.visual_style} onChange={set("visual_style")} /></Field>
        </div>
      )}
      {step === 1 && (
        <div className="space-y-5">
          <div><span className="label">Format</span>
            <Segmented value={c.format ?? "both"} onChange={(v) => setC({ ...c, format: v })} options={[{ id: "long", label: "Uzun belgesel" }, { id: "shorts", label: "Sadece Shorts" }, { id: "both", label: "İkisi (Shorts uzun bölümden kesilir)" }]} /></div>
          {c.format !== "shorts" && <Field label={`Uzun bölüm süresi: ${c.target_minutes} dk`} hint="8+ dk: video ortasına reklam eklenebilir (mid-roll)."><input type="range" min={4} max={20} step={1} value={c.target_minutes} onChange={(e) => setC({ ...c, target_minutes: +e.target.value })} className="w-full accent-violet-500" /></Field>}
          <div className="grid gap-5 sm:grid-cols-2">
            {c.format !== "shorts" && <SlotEditor label="Uzun bölüm yayın slotları" value={sch.long ?? []} onChange={(v) => setSch({ ...sch, long: v })} />}
            {c.format !== "long" && <SlotEditor label="Shorts yayın slotları" value={sch.shorts ?? []} onChange={(v) => setSch({ ...sch, shorts: v })} />}
          </div>
        </div>
      )}
      {step === 2 && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {chars?.map((ch) => (
            <button key={ch.id} onClick={() => setC({ ...c, character_id: ch.id })} className={cn("flex items-center gap-3 rounded-2xl border p-3 text-left transition", c.character_id === ch.id ? "border-brand bg-brand/10 shadow-glow" : "border-line bg-elev/30 hover:border-brand/40")}>
              <div className="h-16 w-12 shrink-0 overflow-hidden rounded-lg bg-elev">{ch.avatar_url && <img src={ch.avatar_url} className="h-full w-full object-cover" />}</div>
              <div className="min-w-0"><div className="truncate font-semibold">{ch.name}</div><div className="line-clamp-2 text-xs text-muted">{ch.persona}</div></div>
            </button>
          ))}
          <Link to="/characters" className="flex items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-line p-3 text-sm text-muted hover:text-fg"><UserRound className="h-4 w-4" />Karakter oluştur</Link>
        </div>
      )}
      {step === 3 && (
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={`Kalite eşiği: ${c.min_quality}`} hint="Jüri puanı bunun altındaysa bölüm yayınlanmaz, incelemeye düşer."><input type="range" min={5} max={9.5} step={0.5} value={c.min_quality} onChange={(e) => setC({ ...c, min_quality: +e.target.value })} className="w-full accent-violet-500" /></Field>
          <Field label="Günlük üretim limiti"><input type="number" min={1} max={10} className="input" value={c.daily_cap} onChange={(e) => setC({ ...c, daily_cap: +e.target.value })} /></Field>
          <Field label="Kaç gün önceden üret"><input type="number" min={1} max={14} className="input" value={c.lead_days} onChange={(e) => setC({ ...c, lead_days: +e.target.value })} /></Field>
          <Field label="Üretim saati (gece)"><select className="input" value={c.run_hour} onChange={(e) => setC({ ...c, run_hour: +e.target.value })}>{Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{String(h).padStart(2, "0")}:00</option>)}</select></Field>
          <Field label="Gizlilik"><select className="input" value={c.privacy} onChange={set("privacy")}><option value="public">Herkese açık</option><option value="unlisted">Liste dışı</option><option value="private">Özel</option></select></Field>
          <Field label="Oynatma listesi ID (opsiyonel)"><input className="input font-mono text-xs" value={c.playlist_id} onChange={set("playlist_id")} placeholder="PL…" /></Field>
          <Field label="Varsayılan etiketler" className="sm:col-span-2"><input className="input" value={c.default_tags} onChange={set("default_tags")} placeholder="belgesel, tarih, gizem" /></Field>
          <div className="sm:col-span-2"><Toggle checked={!c.paused} onChange={(v) => setC({ ...c, paused: !v })} label="Tam otomatik çalışsın" desc="Konu seçer, üretir, kaliteyi denetler ve slot saatinde YouTube'da yayınlar." /></div>
          <p className="rounded-xl bg-amber-500/10 p-3 text-xs text-amber-600 sm:col-span-2 dark:text-amber-300">YouTube, şablon hissi veren tekrarlayan içerikleri ve hassas konulardaki AI personaları para kazanmaya kapatabilir. Sistem hassas konuları engeller ve kalite jürisi uygular; yine de ilk haftalarda bölümleri izlemenizi öneririz.</p>
        </div>
      )}
    </Modal>
  );
}

export default function Channels() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["channels"], queryFn: api.channels, refetchInterval: 30_000 });
  const { data: quota } = useQuery({ queryKey: ["quota"], queryFn: api.quota, refetchInterval: 60_000 });
  const [open, setOpen] = useState(false);
  const pause = useMutation({ mutationFn: (c: Channel) => api.pauseChannel(c.id, !c.paused), onSuccess: () => qc.invalidateQueries({ queryKey: ["channels"] }) });
  return (
    <>
      <PageHeader eyebrow="Belgesel" title="YouTube kanalları" desc="Her kanal bir niş ve bir sunucu karakterle tam otomatik çalışır: konu → senaryo → kalite kontrol → video → zamanlanmış yayın."
        actions={<Button variant="primary" icon={<Plus className="h-4 w-4" />} onClick={() => setOpen(true)}>Yeni kanal</Button>} />
      {quota && (
        <div className="card mb-6 flex flex-wrap items-center gap-4 p-4 text-sm">
          <Youtube className="h-5 w-5 text-red-500" />
          <span>Bugünkü API kotası</span>
          <div className="h-2 min-w-[160px] flex-1 overflow-hidden rounded-full bg-elev"><div className="h-full rounded-full bg-red-500" style={{ width: `${Math.min(100, (quota.used / quota.limit) * 100)}%` }} /></div>
          <span className="font-mono text-xs text-muted">{num(quota.used)} / {num(quota.limit)}</span>
          <Pill>{quota.uploads_left} yükleme hakkı kaldı</Pill>
        </div>
      )}
      {data?.length === 0 && <Empty icon={<Tv className="h-6 w-6" />} title="Henüz kanal yok" desc="Önce bir karakter oluştur, sonra kanalı kur ve YouTube hesabını bağla." action={<Button variant="primary" onClick={() => setOpen(true)}>Kanal kur</Button>} />}
      <div className="grid gap-5 lg:grid-cols-2">
        {data?.map((c, i) => (
          <motion.div key={c.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }} className="card overflow-hidden">
            <Link to={`/channels/${c.id}`} className="flex gap-4 p-5">
              <div className="h-28 w-20 shrink-0 overflow-hidden rounded-xl bg-elev">{c.character?.avatar_url && <img src={c.character.avatar_url} className="h-full w-full object-cover" />}</div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2"><h3 className="truncate font-display text-lg font-bold">{c.name}</h3>
                  {c.connected ? <Pill className="text-red-500"><Youtube className="h-3 w-3" />Bağlı</Pill> : <Pill className="text-amber-500">YouTube bağlı değil</Pill>}</div>
                <p className="truncate text-xs text-muted">{c.niche} · sunucu {c.character?.name ?? "—"}</p>
                <div className="mt-3 grid grid-cols-4 gap-2 text-center">
                  {[["Yayında", c.published], ["Üretimde", c.in_production], ["Konu", c.backlog], ["İzlenme", num(c.views)]].map(([k, v]) => (
                    <div key={k} className="rounded-xl bg-elev/50 py-1.5"><div className="font-display font-extrabold">{v}</div><div className="text-[10px] uppercase tracking-wider text-muted">{k}</div></div>
                  ))}
                </div>
                {c.next && <p className="mt-3 flex items-center gap-1.5 truncate text-xs"><CalendarClock className="h-3.5 w-3.5 text-brand" />Sıradaki: <b className="truncate">{c.next.title}</b> · {new Date(c.next.slot_at!).toLocaleString("tr-TR", { weekday: "short", hour: "2-digit", minute: "2-digit" })}</p>}
                {c.needs_review > 0 && <p className="mt-1 text-xs text-orange-500">{c.needs_review} bölüm incelemede</p>}
              </div>
            </Link>
            <div className="flex items-center justify-between border-t border-line px-5 py-3">
              <span className="text-xs text-muted">{c.format === "both" ? "Uzun + Shorts" : c.format === "long" ? "Uzun belgesel" : "Shorts"} · {c.target_minutes} dk</span>
              <button onClick={() => pause.mutate(c)} className="flex items-center gap-2 text-xs font-medium">
                {c.paused ? "Durduruldu" : "Otomatik"}
                <span className={cn("relative h-5 w-9 rounded-full transition", c.paused ? "bg-line" : "grad-bg")}><span className={cn("absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-all", c.paused ? "left-0.5" : "right-0.5")} /></span>
              </button>
            </div>
          </motion.div>
        ))}
      </div>
      <ChannelForm open={open} initial={null} onClose={() => setOpen(false)} />
    </>
  );
}
