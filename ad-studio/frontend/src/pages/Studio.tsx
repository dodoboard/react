import { useMutation, useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowLeft, ArrowRight, Check, Clapperboard, Music2, Package, Pause, Play, Plus, Rocket, Video } from "lucide-react";
import { useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Button, Field, PageHeader, Pill, Toggle } from "@/components/ui";
import { api } from "@/lib/api";
import { ANGLES, cn, money, PLATFORMS } from "@/lib/utils";
import { ProductForm } from "./Products";

const STEPS = ["Ürün", "Hedef & Mesaj", "Görsel & Ses", "Üretim"];
const TONES = ["enerjik", "samimi", "lüks", "esprili", "güven veren", "acil / fırsat", "eğitici"];
const STYLES = [
  { id: "premium studio", label: "Premium stüdyo", desc: "minimal, soft light, high-end product photography" },
  { id: "ugc lifestyle", label: "UGC / Lifestyle", desc: "authentic smartphone photo, real home, natural light, candid" },
  { id: "bold neon", label: "Cesur neon", desc: "vibrant neon colors, dramatic rim light, dark background, energetic" },
  { id: "cozy aesthetic", label: "Cozy estetik", desc: "warm tones, pastel, aesthetic interior, golden hour" },
  { id: "tech futuristic", label: "Teknoloji", desc: "futuristic, sleek metallic surfaces, blue accent lights, clean" },
  { id: "outdoor adventure", label: "Dış mekân", desc: "outdoor adventure, nature, cinematic wide shots, sunlight" },
];
const LANGS = [["tr", "Türkçe"], ["en", "English"], ["de", "Deutsch"], ["ar", "العربية"]];

function Chip({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" onClick={onClick} className={cn("rounded-xl border px-3.5 py-2 text-sm font-medium transition",
      on ? "border-brand bg-brand/15 text-fg shadow-glow" : "border-line bg-elev/40 text-muted hover:border-brand/40 hover:text-fg")}>{children}</button>
  );
}

export default function Studio() {
  const nav = useNavigate();
  const [params] = useSearchParams();
  const [step, setStep] = useState(0);
  const [newOpen, setNewOpen] = useState(false);
  const { data: products } = useQuery({ queryKey: ["products"], queryFn: api.products });
  const { data: voices } = useQuery({ queryKey: ["voices"], queryFn: api.voices, retry: false });
  const { data: music } = useQuery({ queryKey: ["music"], queryFn: api.music });
  const { data: cfg } = useQuery({ queryKey: ["config"], queryFn: api.config });
  const [f, setF] = useState({
    product_id: Number(params.get("product")) || 0, name: "", language: "tr", tone: "enerjik", audience: "", angle_notes: "",
    visual_style: STYLES[0].desc, style_id: STYLES[0].id, voice_id: "", variants: 4, scenes: 4, use_i2v: false, music: "",
    target_platform: "tiktok", angles: [] as string[], auto_render: true,
  });
  const audio = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState<string | null>(null);
  const product = products?.find((p) => p.id === f.product_id);

  const create = useMutation({
    mutationFn: () => api.createCampaign({ ...f, style_id: undefined }),
    onSuccess: (c) => { toast.success("Kampanya başlatıldı", { description: `${c.total} varyant üretim hattında` }); nav(`/campaigns/${c.id}`); },
    onError: (e: Error) => toast.error(e.message),
  });

  const play = (id: string, url: string | null) => {
    if (!url) return;
    audio.current?.pause();
    if (playing === id) { setPlaying(null); return; }
    audio.current = new Audio(url);
    audio.current.onended = () => setPlaying(null);
    audio.current.play();
    setPlaying(id);
  };

  const canNext = step === 0 ? !!f.product_id : true;
  const perVideoMin = (f.use_i2v ? 2.2 : 0.25) * f.scenes + 0.6;

  return (
    <>
      <PageHeader eyebrow="Kampanya Stüdyosu" title="Yeni reklam kampanyası" desc="Birkaç adımda çoklu A/B varyantlı, seslendirilmiş ve altyazılı dikey videolar üret." />

      <div className="mb-8 flex items-center gap-2 overflow-x-auto pb-1">
        {STEPS.map((s, i) => (
          <button key={s} onClick={() => (i < step || canNext) && setStep(i)} className="flex shrink-0 items-center gap-2">
            <span className={cn("grid h-8 w-8 place-items-center rounded-full text-xs font-bold transition",
              i < step ? "grad-bg text-white" : i === step ? "border-2 border-brand text-brand" : "border border-line text-muted")}>
              {i < step ? <Check className="h-4 w-4" /> : i + 1}
            </span>
            <span className={cn("text-sm font-medium", i === step ? "text-fg" : "text-muted")}>{s}</span>
            {i < STEPS.length - 1 && <span className={cn("mx-2 h-px w-8 sm:w-16", i < step ? "bg-brand" : "bg-line")} />}
          </button>
        ))}
      </div>

      <div className="grid gap-6 xl:grid-cols-[1fr_340px]">
        <div className="card min-h-[460px] p-6">
          <AnimatePresence mode="wait">
            <motion.div key={step} initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -16 }} transition={{ duration: 0.2 }}>
              {step === 0 && (
                <div>
                  <h3 className="mb-4 font-display text-lg font-bold">Hangi ürünü tanıtıyoruz?</h3>
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {products?.map((p) => (
                      <button key={p.id} onClick={() => setF({ ...f, product_id: p.id })}
                        className={cn("flex items-center gap-3 rounded-2xl border p-3 text-left transition", f.product_id === p.id ? "border-brand bg-brand/10 shadow-glow" : "border-line bg-elev/30 hover:border-brand/40")}>
                        <div className="grid h-14 w-14 shrink-0 place-items-center overflow-hidden rounded-xl bg-white">{p.image_url ? <img src={p.image_url} className="h-full w-full object-contain" /> : <Package className="h-5 w-5 text-zinc-400" />}</div>
                        <div className="min-w-0"><div className="truncate text-sm font-semibold">{p.name}</div><div className="text-xs text-muted">{p.price ? money(p.price, p.currency) : p.platform}</div></div>
                      </button>
                    ))}
                    <button onClick={() => setNewOpen(true)} className="flex items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-line p-3 text-sm font-medium text-muted transition hover:border-brand/50 hover:text-fg"><Plus className="h-4 w-4" /> Yeni ürün</button>
                  </div>
                </div>
              )}
              {step === 1 && (
                <div className="space-y-6">
                  <div>
                    <span className="label">Platform</span>
                    <div className="flex flex-wrap gap-2">{PLATFORMS.map((p) => <Chip key={p.id} on={f.target_platform === p.id} onClick={() => setF({ ...f, target_platform: p.id })}>{p.label}</Chip>)}</div>
                  </div>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <Field label="Dil"><select className="input" value={f.language} onChange={(e) => setF({ ...f, language: e.target.value })}>{LANGS.map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
                    <Field label="Hedef kitle"><input className="input" value={f.audience} onChange={(e) => setF({ ...f, audience: e.target.value })} placeholder="ör. 18-30 yaş, öğrenci, oyuncu" /></Field>
                  </div>
                  <div><span className="label">Ton</span><div className="flex flex-wrap gap-2">{TONES.map((t) => <Chip key={t} on={f.tone === t} onClick={() => setF({ ...f, tone: t })}>{t}</Chip>)}</div></div>
                  <div>
                    <span className="label">Hook yaklaşımları (A/B) — boş bırakırsan otomatik karışık</span>
                    <div className="flex flex-wrap gap-2">
                      {Object.entries(ANGLES).map(([k, v]) => <Chip key={k} on={f.angles.includes(k)} onClick={() => setF({ ...f, angles: f.angles.includes(k) ? f.angles.filter((x) => x !== k) : [...f.angles, k] })}>{v}</Chip>)}
                    </div>
                  </div>
                  <Field label="Ek yönlendirme (opsiyonel)"><textarea className="input" value={f.angle_notes} onChange={(e) => setF({ ...f, angle_notes: e.target.value })} placeholder="ör. Kargo bedava vurgusu yap, rakip markayı anma" /></Field>
                </div>
              )}
              {step === 2 && (
                <div className="space-y-6">
                  <div>
                    <span className="label">Görsel stil</span>
                    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                      {STYLES.map((s) => (
                        <button key={s.id} onClick={() => setF({ ...f, style_id: s.id, visual_style: s.desc })}
                          className={cn("rounded-2xl border p-3.5 text-left transition", f.style_id === s.id ? "border-brand bg-brand/10 shadow-glow" : "border-line bg-elev/30 hover:border-brand/40")}>
                          <div className="text-sm font-semibold">{s.label}</div><div className="mt-1 line-clamp-2 text-[11px] text-muted">{s.desc}</div>
                        </button>
                      ))}
                    </div>
                  </div>
                  <Toggle checked={f.use_i2v} onChange={(v) => setF({ ...f, use_i2v: v })} label="Hareketli sahneler (Wan 2.2 image-to-video)"
                    desc="Her sahne 5 sn'lik AI video klibe dönüşür. Çok daha etkileyici, ama RTX 5080'de sahne başı ~1.5-3 dk." />
                  <div>
                    <span className="label">Ses ({cfg?.tts_provider === "chatterbox" ? "Lokal Chatterbox" : "ElevenLabs"})</span>
                    <div className="grid max-h-64 gap-2 overflow-y-auto pr-1 sm:grid-cols-2">
                      <button onClick={() => setF({ ...f, voice_id: "" })} className={cn("rounded-xl border p-3 text-left text-sm", !f.voice_id ? "border-brand bg-brand/10" : "border-line bg-elev/30")}>Varsayılan ses (Ayarlar)</button>
                      {voices?.map((v) => (
                        <div key={v.id} onClick={() => setF({ ...f, voice_id: v.id })} role="button"
                          className={cn("flex cursor-pointer items-center gap-3 rounded-xl border p-3 transition", f.voice_id === v.id ? "border-brand bg-brand/10" : "border-line bg-elev/30 hover:border-brand/40")}>
                          {v.preview_url && <button onClick={(e) => { e.stopPropagation(); play(v.id, v.preview_url); }} className="grid h-8 w-8 shrink-0 place-items-center rounded-full grad-bg text-white">
                            {playing === v.id ? <Pause className="h-3.5 w-3.5" /> : <Play className="ml-0.5 h-3.5 w-3.5" />}</button>}
                          <div className="min-w-0"><div className="truncate text-sm font-medium">{v.name}</div>
                            <div className="truncate text-[11px] text-muted">{Object.values(v.labels ?? {}).slice(0, 3).join(" · ") || v.category}</div></div>
                        </div>
                      ))}
                    </div>
                  </div>
                  <Field label="Fon müziği" hint="data/music klasörüne telifsiz müzik ekle (Ayarlar'dan yüklenebilir). Konuşmada otomatik kısılır.">
                    <select className="input" value={f.music} onChange={(e) => setF({ ...f, music: e.target.value })}>
                      <option value="">Rastgele ({music?.length ?? 0} parça)</option><option value="none">Müzik yok</option>
                      {music?.map((m) => <option key={m.name} value={m.name}>{m.name}</option>)}
                    </select>
                  </Field>
                </div>
              )}
              {step === 3 && (
                <div className="space-y-6">
                  <Field label="Kampanya adı"><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder={product ? `${product.name} · ${new Date().toLocaleDateString("tr-TR")}` : ""} /></Field>
                  <div className="grid gap-6 sm:grid-cols-2">
                    <div>
                      <div className="flex justify-between"><span className="label">Varyant sayısı</span><span className="font-display text-2xl font-extrabold grad-text">{f.variants}</span></div>
                      <input type="range" min={1} max={12} value={f.variants} onChange={(e) => setF({ ...f, variants: +e.target.value })} className="w-full accent-violet-500" />
                      <p className="text-xs text-muted">Her biri farklı hook — kazananı gelir verisi seçer.</p>
                    </div>
                    <div>
                      <div className="flex justify-between"><span className="label">Sahne sayısı</span><span className="font-display text-2xl font-extrabold grad-text">{f.scenes}</span></div>
                      <input type="range" min={2} max={7} value={f.scenes} onChange={(e) => setF({ ...f, scenes: +e.target.value })} className="w-full accent-violet-500" />
                      <p className="text-xs text-muted">3-5 sahne, 20-35 sn video için ideal.</p>
                    </div>
                  </div>
                  <Toggle checked={f.auto_render} onChange={(v) => setF({ ...f, auto_render: v })} label="Senaryoları onaylamadan direkt render et"
                    desc="Kapalıysa önce senaryolar yazılır, sen inceleyip düzenledikten sonra render edersin." />
                </div>
              )}
            </motion.div>
          </AnimatePresence>
        </div>

        <div className="space-y-4">
          <div className="card sticky top-24 p-5">
            <h3 className="mb-4 font-display font-bold">Özet</h3>
            <div className="mb-4 flex items-center gap-3 rounded-xl bg-elev/50 p-3">
              <div className="grid h-12 w-12 shrink-0 place-items-center overflow-hidden rounded-lg bg-white">{product?.image_url ? <img src={product.image_url} className="h-full w-full object-contain" /> : <Package className="h-5 w-5 text-zinc-400" />}</div>
              <div className="min-w-0 text-sm font-semibold"><div className="truncate">{product?.name ?? "Ürün seçilmedi"}</div><div className="text-xs font-normal text-muted">{product?.price ? money(product.price, product.currency) : ""}</div></div>
            </div>
            <dl className="space-y-2.5 text-sm">
              {[["Platform", PLATFORMS.find((p) => p.id === f.target_platform)?.label], ["Ton", f.tone], ["Stil", STYLES.find((s) => s.id === f.style_id)?.label],
                ["Hook'lar", f.angles.length ? f.angles.map((a) => ANGLES[a]).join(", ") : "Otomatik"], ["Hareket", f.use_i2v ? "Wan 2.2 video" : "Ken Burns"]].map(([k, v]) => (
                <div key={k} className="flex justify-between gap-4"><dt className="text-muted">{k}</dt><dd className="truncate text-right font-medium">{v}</dd></div>
              ))}
            </dl>
            <div className="my-4 h-px bg-line" />
            <div className="flex flex-wrap gap-1.5">
              <Pill><Clapperboard className="h-3 w-3" />{f.variants} video</Pill>
              <Pill><Video className="h-3 w-3" />{f.variants * f.scenes} sahne</Pill>
              <Pill><Music2 className="h-3 w-3" />{f.music === "none" ? "Müziksiz" : "Müzikli"}</Pill>
            </div>
            <p className="mt-3 text-xs text-muted">Tahmini süre: ~{Math.ceil(perVideoMin * f.variants)} dk (RTX 5080)</p>
            <div className="mt-5 flex gap-2">
              {step > 0 && <Button icon={<ArrowLeft className="h-4 w-4" />} onClick={() => setStep(step - 1)}>Geri</Button>}
              {step < STEPS.length - 1
                ? <Button variant="primary" className="flex-1" disabled={!canNext} onClick={() => setStep(step + 1)}>Devam <ArrowRight className="h-4 w-4" /></Button>
                : <Button variant="primary" className="flex-1" size="lg" icon={<Rocket className="h-4 w-4" />} loading={create.isPending} disabled={!f.product_id} onClick={() => create.mutate()}>Üretimi başlat</Button>}
            </div>
          </div>
        </div>
      </div>
      <ProductForm open={newOpen} initial={null} onClose={() => setNewOpen(false)} onSaved={(p) => setF((x) => ({ ...x, product_id: p.id }))} />
    </>
  );
}
