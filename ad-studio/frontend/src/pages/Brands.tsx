import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Building2, ImagePlus, Plus, Type } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { BrandMark } from "@/components/BrandSwitcher";
import { Button, Empty, Field, Modal, PageHeader, Pill, Segmented, Skeleton, Toggle } from "@/components/ui";
import { api, type Brand } from "@/lib/api";
import { money } from "@/lib/utils";

const BLANK: Partial<Brand> = { name: "", primary_color: "#8B5CF6", accent_color: "#FFD400", tone: "", audience: "", guidelines: "",
  banned_words: "", must_say: "", cta: "", ad_disclosure: "#reklam #işbirliği", hashtag: "", website: "", contact_name: "",
  contact_email: "", monthly_fee: 0, per_video_fee: 0, currency: "TRY", active: true, voice_id: "", font_file: "" };

/** Mini 9:16 mock: caption highlight + CTA button in brand colours. */
export function BrandPreview({ b, logo }: { b: Partial<Brand>; logo?: string | null }) {
  return (
    <div className="relative mx-auto aspect-[9/16] w-full max-w-[200px] overflow-hidden rounded-2xl border border-line shadow-card"
      style={{ background: `linear-gradient(160deg, ${b.primary_color}, #0b0b12 85%)` }}>
      <div className="absolute inset-x-0 top-0 h-1" style={{ background: b.accent_color }} />
      {logo && <img src={logo} className="absolute left-3 top-3 h-6 max-w-[70px] rounded bg-white/90 object-contain p-0.5" />}
      <div className="absolute inset-x-0 top-[38%] text-center font-display text-[15px] font-black uppercase leading-tight text-white [text-shadow:0_2px_0_#000]">
        BUNU <span style={{ color: b.accent_color }}>GÖRMEDEN</span><br />ALMA
      </div>
      <div className="absolute inset-x-6 bottom-10 rounded-full py-2 text-center text-[11px] font-bold text-white" style={{ background: b.primary_color }}>
        {b.cta || "Link profilde"}
      </div>
      <div className="absolute bottom-[4.6rem] left-1/2 -translate-x-1/2 rounded-full px-3 py-0.5 text-[10px] font-extrabold text-black" style={{ background: b.accent_color }}>1.299 TRY</div>
    </div>
  );
}

export function BrandForm({ initial, open, onClose }: { initial: Partial<Brand> | null; open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const [b, setB] = useState<Partial<Brand>>(BLANK);
  const [tab, setTab] = useState<"kit" | "rules" | "billing">("kit");
  const [logo, setLogo] = useState<File | null>(null);
  const [fontFile, setFontFile] = useState<File | null>(null);
  const logoRef = useRef<HTMLInputElement>(null);
  const fontRef = useRef<HTMLInputElement>(null);
  const { data: voices } = useQuery({ queryKey: ["voices"], queryFn: api.voices, retry: false, enabled: open });
  useEffect(() => { if (open) { setB(initial ?? BLANK); setLogo(null); setFontFile(null); setTab("kit"); } }, [open, initial]);
  const preview = logo ? URL.createObjectURL(logo) : b.logo_url;

  const save = useMutation({
    mutationFn: async () => {
      let r = await api.saveBrand({ ...b, monthly_fee: Number(b.monthly_fee) || 0, per_video_fee: Number(b.per_video_fee) || 0 });
      if (logo) r = await api.brandLogo(r.id, logo);
      if (fontFile) r = await api.brandFont(r.id, fontFile);
      return r;
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["brands"] }); qc.invalidateQueries({ queryKey: ["brand"] }); toast.success("Firma kaydedildi"); onClose(); },
    onError: (e: Error) => toast.error(e.message),
  });
  const set = (k: keyof Brand) => (e: { target: { value: string } }) => setB({ ...b, [k]: e.target.value });

  return (
    <Modal open={open} onClose={onClose} wide title={b.id ? `${b.name} — düzenle` : "Yeni firma"}
      footer={<><Button variant="ghost" onClick={onClose}>Vazgeç</Button><Button variant="primary" disabled={!b.name} loading={save.isPending} onClick={() => save.mutate()}>Kaydet</Button></>}>
      <div className="grid gap-8 md:grid-cols-[1fr_220px]">
        <div className="space-y-5">
          <Field label="Firma adı"><input className="input text-base font-semibold" value={b.name} onChange={set("name")} placeholder="ör. Acme Ev Gereçleri" /></Field>
          <Segmented value={tab} onChange={setTab} options={[{ id: "kit", label: "Marka kiti" }, { id: "rules", label: "Mesaj kuralları" }, { id: "billing", label: "İletişim & ücret" }]} />
          {tab === "kit" && (
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Ana renk"><div className="flex gap-2"><input type="color" className="h-[42px] w-14 cursor-pointer rounded-xl border border-line bg-transparent" value={b.primary_color} onChange={set("primary_color")} /><input className="input font-mono" value={b.primary_color} onChange={set("primary_color")} /></div></Field>
              <Field label="Vurgu rengi (altyazı, fiyat)"><div className="flex gap-2"><input type="color" className="h-[42px] w-14 cursor-pointer rounded-xl border border-line bg-transparent" value={b.accent_color} onChange={set("accent_color")} /><input className="input font-mono" value={b.accent_color} onChange={set("accent_color")} /></div></Field>
              <div>
                <span className="label">Logo</span>
                <Button className="w-full" icon={<ImagePlus className="h-4 w-4" />} onClick={() => logoRef.current?.click()}>{logo ? logo.name : b.logo_url ? "Logoyu değiştir" : "Logo yükle (şeffaf PNG)"}</Button>
                <input ref={logoRef} type="file" accept="image/*" hidden onChange={(e) => setLogo(e.target.files?.[0] ?? null)} />
              </div>
              <div>
                <span className="label">Kurumsal font</span>
                <Button className="w-full" icon={<Type className="h-4 w-4" />} onClick={() => fontRef.current?.click()}>{fontFile ? fontFile.name : b.font_file || "Font yükle (.ttf/.otf)"}</Button>
                <input ref={fontRef} type="file" accept=".ttf,.otf" hidden onChange={(e) => setFontFile(e.target.files?.[0] ?? null)} />
              </div>
              <Field label="Marka sesi">
                <select className="input" value={b.voice_id} onChange={set("voice_id")}><option value="">Varsayılan</option>{voices?.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}</select>
              </Field>
              <Field label="CTA"><input className="input" value={b.cta} onChange={set("cta")} placeholder="ör. Acme'de keşfet" /></Field>
              <Field label="Marka hashtag'i"><input className="input" value={b.hashtag} onChange={set("hashtag")} placeholder="acmeev" /></Field>
              <Field label="Reklam ibaresi"><input className="input" value={b.ad_disclosure} onChange={set("ad_disclosure")} /></Field>
            </div>
          )}
          {tab === "rules" && (
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Ton"><input className="input" value={b.tone} onChange={set("tone")} placeholder="samimi, güven veren" /></Field>
              <Field label="Hedef kitle"><input className="input" value={b.audience} onChange={set("audience")} placeholder="25-45 yaş ev hanımları" /></Field>
              <Field label="Marka kuralları" className="sm:col-span-2" hint="LLM her senaryoda bunlara uyar."><textarea className="input min-h-[90px]" value={b.guidelines} onChange={set("guidelines")} placeholder="Rakip markalardan bahsetme. Fiyatı her zaman söyle. Sen dili kullan." /></Field>
              <Field label="Yasaklı kelimeler (virgülle)" hint="Çıktıda geçerse otomatik yeniden yazılır."><input className="input" value={b.banned_words} onChange={set("banned_words")} placeholder="ucuz, bedava, en iyi" /></Field>
              <Field label="Mutlaka söylenecek"><input className="input" value={b.must_say} onChange={set("must_say")} placeholder="2 yıl garanti, ücretsiz kargo" /></Field>
            </div>
          )}
          {tab === "billing" && (
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Yetkili"><input className="input" value={b.contact_name} onChange={set("contact_name")} /></Field>
              <Field label="E-posta"><input className="input" value={b.contact_email} onChange={set("contact_email")} /></Field>
              <Field label="Web sitesi" className="sm:col-span-2"><input className="input" value={b.website} onChange={set("website")} /></Field>
              <Field label="Aylık sabit ücret"><input type="number" className="input" value={b.monthly_fee} onChange={set("monthly_fee")} /></Field>
              <Field label="Video başı ücret"><input type="number" className="input" value={b.per_video_fee} onChange={set("per_video_fee")} /></Field>
              <Field label="Para birimi"><select className="input" value={b.currency} onChange={set("currency")}>{["TRY", "USD", "EUR"].map((c) => <option key={c}>{c}</option>)}</select></Field>
              <div className="sm:col-span-2"><Toggle checked={b.active ?? true} onChange={(v) => setB({ ...b, active: v })} label="Aktif müşteri" /></div>
            </div>
          )}
        </div>
        <div><span className="label text-center">Önizleme</span><BrandPreview b={b} logo={preview} /></div>
      </div>
    </Modal>
  );
}

export default function Brands() {
  const { data } = useQuery({ queryKey: ["brands"], queryFn: api.brands });
  const [open, setOpen] = useState(false);
  return (
    <>
      <PageHeader eyebrow="Müşteriler" title="Firmalar" desc="Her firmanın marka kiti, ürünleri, kampanyaları, onay süreci ve faturalaması ayrı yönetilir."
        actions={<Button variant="primary" icon={<Plus className="h-4 w-4" />} onClick={() => setOpen(true)}>Yeni firma</Button>} />
      {data?.length === 0 && <Empty icon={<Building2 className="h-6 w-6" />} title="Henüz firma yok" desc="İlk müşterini ekle: logo, renkler, ses ve ücretlendirme." action={<Button variant="primary" onClick={() => setOpen(true)}>Firma ekle</Button>} />}
      <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
        {!data && Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-56" />)}
        {data?.map((b, i) => (
          <motion.div key={b.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}>
            <Link to={`/brands/${b.id}`} className="card group block overflow-hidden transition hover:shadow-glow" style={{ opacity: b.active ? 1 : 0.6 }}>
              <div className="h-20" style={{ background: `linear-gradient(120deg, ${b.primary_color}, ${b.accent_color})` }} />
              <div className="-mt-8 px-5 pb-5">
                <div className="rounded-2xl border-4 border-panel" style={{ width: 64 }}><BrandMark b={{ name: b.name, logo_url: b.logo_url, color: b.primary_color }} size={56} /></div>
                <div className="mt-3 flex items-center gap-2"><h3 className="truncate font-display text-lg font-bold">{b.name}</h3>{!b.active && <Pill>Pasif</Pill>}</div>
                <p className="truncate text-xs text-muted">{b.contact_name || b.website || "—"}</p>
                <div className="mt-4 grid grid-cols-3 gap-2 text-center">
                  {[["Ürün", b.products], ["Video", b.videos], ["Onay", b.pending_approval]].map(([k, v]) => (
                    <div key={k} className="rounded-xl bg-elev/50 py-2"><div className="font-display text-lg font-extrabold">{v}</div><div className="text-[10px] uppercase tracking-wider text-muted">{k}</div></div>
                  ))}
                </div>
                <div className="mt-3 flex justify-between text-xs"><span className="text-muted">Bu ay ücret</span><span className="font-semibold">{money(b.fees_month, b.currency)}</span></div>
                <div className="flex justify-between text-xs"><span className="text-muted">Affiliate toplam</span><span className="font-semibold text-emerald-500">{money(b.affiliate_total, b.currency)}</span></div>
              </div>
            </Link>
          </motion.div>
        ))}
      </div>
      <BrandForm open={open} initial={null} onClose={() => setOpen(false)} />
    </>
  );
}
