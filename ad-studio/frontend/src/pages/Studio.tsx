import { useMutation, useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, Check, Clapperboard, Music2, Package, Pause, Play, Plus, Rocket, Video } from "lucide-react";
import { useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { FormatPicker, FORMATS, I2VPicker } from "@/components/AvatarPicker";
import { BrandMark } from "@/components/BrandSwitcher";
import { Button, Field, PageHeader, Pill, Segmented, Toggle } from "@/components/ui";
import { useBrand } from "@/lib/brand";
import { api, type Format, type I2V } from "@/lib/api";
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
const COLLECTIONS = [
  { id: "top_list", label: "Top liste", desc: "En iyi N ürün, #1 #2…" },
  { id: "bundle", label: "Kombin / set", desc: "Birlikte kullanılan ürünler" },
  { id: "comparison", label: "Karşılaştırma", desc: "Hangisi kime uygun" },
  { id: "sale", label: "İndirim vitrini", desc: "Fiyat odaklı fırsatlar" },
  { id: "gift_guide", label: "Hediye rehberi", desc: "Kime ne alınır" },
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
  const { brandId } = useBrand();
  const { data: brands } = useQuery({ queryKey: ["brands"], queryFn: api.brands });
  const [step, setStep] = useState(0);
  const [newOpen, setNewOpen] = useState(false);
  const { data: products } = useQuery({ queryKey: ["products"], queryFn: () => api.products() });
  const { data: voices } = useQuery({ queryKey: ["voices"], queryFn: api.voices, retry: false });
  const { data: music } = useQuery({ queryKey: ["music"], queryFn: api.music });
  const { data: cfg } = useQuery({ queryKey: ["config"], queryFn: api.config });
  const [f, setF] = useState({
    product_id: Number(params.get("product")) || 0, product_ids: [] as number[], kind: "single" as "single" | "collection",
    collection_type: "top_list", brand_id: (Number(params.get("brand")) || brandId || null) as number | null, name: "", language: "tr", tone: "enerjik", audience: "", angle_notes: "",
    visual_style: STYLES[0].desc, style_id: STYLES[0].id, voice_id: "", variants: 4, scenes: 4, i2v_mode: "off" as I2V,
    format: "broll" as Format, avatar: "", music: "",
    target_platform: "tiktok", angles: [] as string[], auto_render: true,
  });
  const audio = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState<string | null>(null);
  const product = products?.find((p) => p.id === (f.kind === "collection" ? f.product_ids[0] : f.product_id));
  const pool = (products ?? []).filter((p) => !f.brand_id || p.brand_id === f.brand_id);
  const pickBrand = (id: number | null) => {
    const b = brands?.find((x) => x.id === id);
    setF((x) => ({ ...x, brand_id: id, product_id: 0, product_ids: [],
      tone: b?.tone || x.tone, audience: b?.audience || x.audience, voice_id: b?.voice_id || x.voice_id }));
  };
  const pickProduct = (pid: number) => setF((x) => {
    if (x.kind !== "collection") return { ...x, product_id: pid };
    const has = x.product_ids.includes(pid);
    if (!has && x.product_ids.length >= 6) { toast.error("En fazla 6 ürün"); return x; }
    return { ...x, product_ids: has ? x.product_ids.filter((y) => y !== pid) : [...x.product_ids, pid] };
  });
  const move = (i: number, d: number) => setF((x) => {
    const a = [...x.product_ids];
    [a[i], a[i + d]] = [a[i + d], a[i]];
    return { ...x, product_ids: a };
  });

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

  const ready = f.kind === "collection" ? f.product_ids.length >= 2 : !!f.product_id;
  const canNext = step === 0 ? ready : step === 2 ? f.format === "broll" || !!f.avatar : true;
  const nScenes = f.kind === "collection" ? Math.max(2, f.product_ids.length) : f.scenes;
  const perVideoMin = (f.i2v_mode === "all" ? 2.2 * nScenes : f.i2v_mode === "hook" ? 2.2 : 0) + 0.25 * nScenes + 0.6
    + (f.format === "avatar_full" ? 8 * nScenes : f.format === "avatar_hook" ? 8 : 0);

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
                <div className="space-y-6">
                  <div>
                    <span className="label">Firma</span>
                    <div className="flex flex-wrap gap-2">
                      <Chip on={!f.brand_id} onClick={() => pickBrand(null)}>Firmasız / tümü</Chip>
                      {brands?.filter((b) => b.active).map((b) => (
                        <Chip key={b.id} on={f.brand_id === b.id} onClick={() => pickBrand(b.id)}>
                          <span className="flex items-center gap-2"><BrandMark b={{ name: b.name, logo_url: b.logo_url, color: b.primary_color }} size={18} />{b.name}</span>
                        </Chip>
                      ))}
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <h3 className="font-display text-lg font-bold">{f.kind === "collection" ? "Videoda hangi ürünler olsun?" : "Hangi ürünü tanıtıyoruz?"}</h3>
                    <Segmented value={f.kind} onChange={(k) => setF({ ...f, kind: k, product_ids: k === "collection" && f.product_id ? [f.product_id] : f.product_ids })}
                      options={[{ id: "single", label: "Tek ürün" }, { id: "collection", label: "Çok ürün (tek video)" }]} />
                  </div>
                  {f.kind === "collection" && (
                    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
                      {COLLECTIONS.map((c) => (
                        <button key={c.id} onClick={() => setF({ ...f, collection_type: c.id })}
                          className={cn("rounded-2xl border p-3 text-left transition", f.collection_type === c.id ? "border-brand bg-brand/10 shadow-glow" : "border-line bg-elev/30 hover:border-brand/40")}>
                          <div className="text-sm font-semibold">{c.label}</div><div className="mt-0.5 text-[11px] text-muted">{c.desc}</div>
                        </button>
                      ))}
                    </div>
                  )}
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {pool.map((p) => {
                      const idx = f.product_ids.indexOf(p.id);
                      const on = f.kind === "collection" ? idx >= 0 : f.product_id === p.id;
                      return (
                        <button key={p.id} onClick={() => pickProduct(p.id)}
                          className={cn("relative flex items-center gap-3 rounded-2xl border p-3 text-left transition", on ? "border-brand bg-brand/10 shadow-glow" : "border-line bg-elev/30 hover:border-brand/40")}>
                          <div className="grid h-14 w-14 shrink-0 place-items-center overflow-hidden rounded-xl bg-white">{p.image_url ? <img src={p.image_url} className="h-full w-full object-contain" /> : <Package className="h-5 w-5 text-zinc-400" />}</div>
                          <div className="min-w-0"><div className="truncate text-sm font-semibold">{p.name}</div><div className="text-xs text-muted">{p.price ? money(p.price, p.currency) : p.platform}</div></div>
                          {f.kind === "collection" && idx >= 0 && <span className="absolute right-2 top-2 grid h-6 w-6 place-items-center rounded-full grad-bg text-xs font-bold text-white">{idx + 1}</span>}
                        </button>
                      );
                    })}
                    <button onClick={() => setNewOpen(true)} className="flex items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-line p-3 text-sm font-medium text-muted transition hover:border-brand/50 hover:text-fg"><Plus className="h-4 w-4" /> Yeni ürün</button>
                  </div>
                  {f.kind === "collection" && f.product_ids.length > 0 && (
                    <div className="rounded-2xl border border-line bg-elev/30 p-3">
                      <span className="label">Videodaki sıra ({f.product_ids.length}/6)</span>
                      <div className="space-y-1.5">
                        {f.product_ids.map((pid, i) => {
                          const p = products?.find((x) => x.id === pid);
                          return (
                            <div key={pid} className="flex items-center gap-2 rounded-xl bg-panel/70 px-2 py-1.5 text-sm">
                              <span className="grid h-6 w-6 place-items-center rounded-full grad-bg text-xs font-bold text-white">{i + 1}</span>
                              <span className="flex-1 truncate">{p?.name}</span>
                              <button disabled={i === 0} onClick={() => move(i, -1)} className="rounded-md p-1 text-muted hover:text-fg disabled:opacity-30"><ArrowUp className="h-3.5 w-3.5" /></button>
                              <button disabled={i === f.product_ids.length - 1} onClick={() => move(i, 1)} className="rounded-md p-1 text-muted hover:text-fg disabled:opacity-30"><ArrowDown className="h-3.5 w-3.5" /></button>
                            </div>
                          );
                        })}
                      </div>
                      {f.product_ids.length < 2 && <p className="mt-2 text-xs text-amber-500">En az 2 ürün seç.</p>}
                    </div>
                  )}
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
                  <FormatPicker format={f.format} avatar={f.avatar} onChange={(format, avatar) => setF({ ...f, format, avatar })} />
                  <I2VPicker value={f.i2v_mode} onChange={(v) => setF({ ...f, i2v_mode: v })} />
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
                    <div className={cn(f.kind === "collection" && "pointer-events-none opacity-40")}>
                      <div className="flex justify-between"><span className="label">Sahne sayısı{f.kind === "collection" ? " (ürün sayısı)" : ""}</span><span className="font-display text-2xl font-extrabold grad-text">{f.scenes}</span></div>
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
              <div className="min-w-0 text-sm font-semibold"><div className="truncate">{product?.name ?? "Ürün seçilmedi"}{f.kind === "collection" && f.product_ids.length > 1 ? ` +${f.product_ids.length - 1}` : ""}</div><div className="text-xs font-normal text-muted">{product?.price ? money(product.price, product.currency) : ""}</div></div>
            </div>
            <dl className="space-y-2.5 text-sm">
              {[["Platform", PLATFORMS.find((p) => p.id === f.target_platform)?.label], ["Ton", f.tone], ["Stil", STYLES.find((s) => s.id === f.style_id)?.label],
                ["Hook'lar", f.angles.length ? f.angles.map((a) => ANGLES[a]).join(", ") : "Otomatik"], ["Format", FORMATS.find((x) => x.id === f.format)?.label], ["Hareket", { off: "Ken Burns", hook: "Hook klip", all: "Tüm sahneler klip" }[f.i2v_mode]]].map(([k, v]) => (
                <div key={k} className="flex justify-between gap-4"><dt className="text-muted">{k}</dt><dd className="truncate text-right font-medium">{v}</dd></div>
              ))}
            </dl>
            <div className="my-4 h-px bg-line" />
            <div className="flex flex-wrap gap-1.5">
              <Pill><Clapperboard className="h-3 w-3" />{f.variants} video</Pill>
              <Pill><Video className="h-3 w-3" />{f.variants * nScenes} sahne</Pill>
              <Pill><Music2 className="h-3 w-3" />{f.music === "none" ? "Müziksiz" : "Müzikli"}</Pill>
            </div>
            <p className="mt-3 text-xs text-muted">Tahmini süre: ~{Math.ceil(perVideoMin * f.variants)} dk (RTX 5080)</p>
            <div className="mt-5 flex gap-2">
              {step > 0 && <Button icon={<ArrowLeft className="h-4 w-4" />} onClick={() => setStep(step - 1)}>Geri</Button>}
              {step < STEPS.length - 1
                ? <Button variant="primary" className="flex-1" disabled={!canNext} onClick={() => setStep(step + 1)}>Devam <ArrowRight className="h-4 w-4" /></Button>
                : <Button variant="primary" className="flex-1" size="lg" icon={<Rocket className="h-4 w-4" />} loading={create.isPending} disabled={!ready} onClick={() => create.mutate()}>Üretimi başlat</Button>}
            </div>
          </div>
        </div>
      </div>
      <ProductForm open={newOpen} initial={null} onClose={() => setNewOpen(false)} onSaved={(p) => (f.kind === "collection" ? pickProduct(p.id) : setF((x) => ({ ...x, product_id: p.id })))} />
    </>
  );
}
