import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { ImagePlus, Link2, Package, Pencil, Plus, Sparkles, Trash2, Wand2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Button, Empty, Field, Modal, PageHeader, Pill, Skeleton } from "@/components/ui";
import { api, type Product } from "@/lib/api";
import { cn, money } from "@/lib/utils";

const BLANK: Partial<Product> = { name: "", description: "", features: "", price: null, currency: "TRY", affiliate_url: "", platform: "", commission_rate: null };

export function ProductForm({ initial, open, onClose, onSaved }: { initial: Partial<Product> | null; open: boolean; onClose: () => void; onSaved?: (p: Product) => void }) {
  const qc = useQueryClient();
  const [p, setP] = useState<Partial<Product>>(BLANK);
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [drag, setDrag] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => { if (open) { setP(initial ?? BLANK); setFile(null); setPreview(initial?.image_url ?? null); setUrl(""); } }, [open, initial]);

  const auto = useMutation({
    mutationFn: () => api.autofill(url),
    onSuccess: (r) => { setP((x) => ({ ...x, ...r })); if (r.image_url) setPreview(r.image_url); toast.success("Ürün bilgileri dolduruldu"); },
    onError: (e: Error) => toast.error(e.message),
  });
  const save = useMutation({
    mutationFn: async () => {
      const body = { ...p, price: p.price ? Number(p.price) : null, commission_rate: p.commission_rate ? Number(p.commission_rate) : null };
      let saved = p.id ? await api.updateProduct(p.id, body) : await api.createProduct(body);
      if (file) saved = await api.productImage(saved.id, file);
      return saved;
    },
    onSuccess: (r) => { qc.invalidateQueries({ queryKey: ["products"] }); toast.success("Ürün kaydedildi"); onSaved?.(r); onClose(); },
    onError: (e: Error) => toast.error(e.message),
  });
  const pick = (f?: File) => { if (f) { setFile(f); setPreview(URL.createObjectURL(f)); } };
  const set = (k: keyof Product) => (e: { target: { value: string } }) => setP({ ...p, [k]: e.target.value });

  return (
    <Modal open={open} onClose={onClose} wide title={p.id ? "Ürünü düzenle" : "Yeni ürün"}
      footer={<><Button variant="ghost" onClick={onClose}>Vazgeç</Button><Button variant="primary" loading={save.isPending} disabled={!p.name} onClick={() => save.mutate()}>Kaydet</Button></>}>
      <div className="mb-6 rounded-2xl border border-brand/30 bg-gradient-to-r from-brand/10 to-brand-2/5 p-4">
        <div className="mb-2 flex items-center gap-2 text-sm font-semibold"><Wand2 className="h-4 w-4 text-brand" /> Linkten otomatik doldur</div>
        <div className="flex gap-2">
          <div className="relative flex-1"><Link2 className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
            <input className="input pl-9" placeholder="https://www.trendyol.com/... veya amazon.com.tr/..." value={url} onChange={(e) => setUrl(e.target.value)} />
          </div>
          <Button variant="primary" loading={auto.isPending} disabled={!url} onClick={() => auto.mutate()}>Getir</Button>
        </div>
        <p className="mt-2 text-xs text-muted">Başlık, fiyat, görsel ve özellikler sayfadan çekilir; Ollama özellikleri özetler.</p>
      </div>
      <div className="grid gap-6 md:grid-cols-[220px_1fr]">
        <div>
          <span className="label">Ürün görseli</span>
          <button type="button" onClick={() => inputRef.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); pick(e.dataTransfer.files[0]); }}
            className={cn("relative grid aspect-square w-full place-items-center overflow-hidden rounded-2xl border-2 border-dashed transition",
              drag ? "border-brand bg-brand/10" : "border-line bg-elev/40 hover:border-brand/50")}>
            {preview ? <img src={preview} className="h-full w-full object-contain p-2" /> :
              <div className="text-center text-xs text-muted"><ImagePlus className="mx-auto mb-2 h-7 w-7 opacity-60" />Sürükle bırak<br />veya tıkla</div>}
          </button>
          <input ref={inputRef} type="file" accept="image/*" hidden onChange={(e) => pick(e.target.files?.[0])} />
          <p className="mt-2 text-xs text-muted">Kapanış kartında gösterilir — ürün sadakati için şeffaf/beyaz arka planlı görsel ideal.</p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Ürün adı" className="sm:col-span-2"><input className="input" value={p.name ?? ""} onChange={set("name")} /></Field>
          <Field label="Açıklama" className="sm:col-span-2"><textarea className="input min-h-[80px]" value={p.description ?? ""} onChange={set("description")} /></Field>
          <Field label="Özellikler (her satır bir özellik)" className="sm:col-span-2" hint="LLM yalnızca bu özellikleri kullanır — uydurma iddia üretmez.">
            <textarea className="input min-h-[110px]" value={p.features ?? ""} onChange={set("features")} placeholder={"40 saat pil ömrü\nAktif gürültü engelleme\nHızlı şarj"} />
          </Field>
          <Field label="Fiyat"><div className="flex gap-2"><input className="input" type="number" step="0.01" value={p.price ?? ""} onChange={set("price")} />
            <select className="input w-24" value={p.currency} onChange={set("currency")}>{["TRY", "USD", "EUR"].map((c) => <option key={c}>{c}</option>)}</select></div></Field>
          <Field label="Satış yeri"><input className="input" value={p.platform ?? ""} onChange={set("platform")} placeholder="Trendyol, Amazon, Hepsiburada…" /></Field>
          <Field label="Affiliate link" className="sm:col-span-2" hint={<>Link <code className="rounded bg-elev px-1">{"{subid}"}</code> içerirse her videoya özel takip kodu yerleştirilir; yoksa <code className="rounded bg-elev px-1">utm_content</code> eklenir.</>}>
            <input className="input font-mono text-xs" value={p.affiliate_url ?? ""} onChange={set("affiliate_url")} />
          </Field>
          <Field label="Komisyon oranı (%)"><input className="input" type="number" step="0.1" value={p.commission_rate ?? ""} onChange={set("commission_rate")} /></Field>
        </div>
      </div>
    </Modal>
  );
}

export default function Products() {
  const qc = useQueryClient();
  const nav = useNavigate();
  const { data } = useQuery({ queryKey: ["products"], queryFn: api.products });
  const [edit, setEdit] = useState<Partial<Product> | null>(null);
  const [open, setOpen] = useState(false);
  const del = useMutation({ mutationFn: api.deleteProduct, onSuccess: () => qc.invalidateQueries({ queryKey: ["products"] }), onError: (e: Error) => toast.error(e.message) });

  return (
    <>
      <PageHeader eyebrow="Katalog" title="Ürünler" desc="Tanıtacağın affiliate ürünleri. Linki yapıştır, gerisini sistem doldursun."
        actions={<Button variant="primary" icon={<Plus className="h-4 w-4" />} onClick={() => { setEdit(null); setOpen(true); }}>Ürün ekle</Button>} />
      {data?.length === 0 && <Empty icon={<Package className="h-6 w-6" />} title="Henüz ürün yok" desc="Bir ürün linki yapıştır; başlık, fiyat, görsel ve özellikler otomatik gelsin." action={<Button variant="primary" onClick={() => setOpen(true)}>İlk ürünü ekle</Button>} />}
      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {!data && Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-80" />)}
        {data?.map((p, i) => (
          <motion.div key={p.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }} className="card group flex flex-col overflow-hidden">
            <div className="relative aspect-[4/3] bg-gradient-to-br from-elev to-panel">
              {p.image_url ? <img src={p.image_url} className="h-full w-full object-contain p-6 transition duration-500 group-hover:scale-105" /> : <Package className="absolute inset-0 m-auto h-10 w-10 text-muted/40" />}
              {p.platform && <Pill className="absolute left-3 top-3 bg-panel/90">{p.platform}</Pill>}
              <div className="absolute right-3 top-3 flex gap-1 opacity-0 transition group-hover:opacity-100">
                <button onClick={() => { setEdit(p); setOpen(true); }} className="rounded-lg bg-panel/90 p-2 text-muted hover:text-fg"><Pencil className="h-3.5 w-3.5" /></button>
                <button onClick={() => confirm("Ürün silinsin mi?") && del.mutate(p.id)} className="rounded-lg bg-panel/90 p-2 text-muted hover:text-rose-400"><Trash2 className="h-3.5 w-3.5" /></button>
              </div>
            </div>
            <div className="flex flex-1 flex-col p-4">
              <h3 className="line-clamp-2 font-semibold leading-snug">{p.name}</h3>
              <p className="mt-1 line-clamp-2 text-xs text-muted">{p.description}</p>
              <div className="mt-auto flex items-end justify-between pt-4">
                <div>
                  <div className="font-display text-lg font-extrabold">{p.price ? money(p.price, p.currency) : "—"}</div>
                  {p.commission_rate ? <div className="text-[11px] text-emerald-500">%{p.commission_rate} komisyon</div> : null}
                </div>
                <Button size="sm" variant="primary" icon={<Sparkles className="h-3.5 w-3.5" />} onClick={() => nav(`/studio?product=${p.id}`)}>Reklam üret</Button>
              </div>
            </div>
          </motion.div>
        ))}
      </div>
      <ProductForm open={open} initial={edit} onClose={() => setOpen(false)} />
    </>
  );
}
