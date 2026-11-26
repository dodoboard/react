import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Check, Download, FileText, Package, Pencil, Plus, RotateCcw, Sparkles, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis } from "recharts";
import { toast } from "sonner";
import { BrandMark } from "@/components/BrandSwitcher";
import { VideoCard, VideoModal } from "@/components/VideoCard";
import { Button, Empty, Field, Modal, Pill, Segmented } from "@/components/ui";
import { api, type Approval } from "@/lib/api";
import { cn, money, num } from "@/lib/utils";
import { BrandForm, BrandPreview } from "./Brands";

export const APPROVAL: Record<Approval, { label: string; tone: string }> = {
  draft: { label: "Taslak", tone: "text-muted" },
  sent: { label: "Onayda", tone: "text-sky-500" },
  approved: { label: "Onaylandı", tone: "text-emerald-500" },
  revision: { label: "Revizyon", tone: "text-amber-500" },
};
const thisMonth = () => new Date().toISOString().slice(0, 7);

function Kpi({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return <div className="card p-4"><div className="text-[11px] font-medium uppercase tracking-wider text-muted">{label}</div><div className={cn("mt-1 font-display text-2xl font-extrabold", tone)}>{value}</div></div>;
}

export default function BrandDetail() {
  const id = Number(useParams().id);
  const qc = useQueryClient();
  const [tab, setTab] = useState<"overview" | "videos" | "products" | "billing">("overview");
  const [edit, setEdit] = useState(false);
  const [filter, setFilter] = useState<"all" | Approval>("all");
  const [sel, setSel] = useState<number[]>([]);
  const [open, setOpen] = useState<number | null>(null);
  const [period, setPeriod] = useState(thisMonth());
  const [extra, setExtra] = useState(false);
  const [ex, setEx] = useState({ note: "", amount: "" });

  const { data: b } = useQuery({ queryKey: ["brand", id], queryFn: () => api.brand(id) });
  const { data: s } = useQuery({ queryKey: ["summary", 30, id], queryFn: () => api.summary(30, id) });
  const { data: vids } = useQuery({ queryKey: ["videos", "brand", id], queryFn: () => api.videos("?status=done&limit=500", id) });
  const { data: prods } = useQuery({ queryKey: ["products", id], queryFn: () => api.products(id) });
  const { data: charges } = useQuery({ queryKey: ["charges", id], queryFn: () => api.charges(id) });
  const inv = () => ["brand", "brands", "summary", "charges", "videos"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));

  const approve = useMutation({
    mutationFn: async (a: Approval) => { await Promise.all(sel.map((v) => api.patchVideo(v, { approval: a }))); },
    onSuccess: () => { inv(); setSel([]); toast.success("Onay durumu güncellendi"); },
  });
  const gen = useMutation({ mutationFn: () => api.generateCharges(id, period), onSuccess: () => { inv(); toast.success(`${period} tahakkuku güncellendi`); }, onError: (e: Error) => toast.error(e.message) });
  const paid = useMutation({ mutationFn: ({ cid, v }: { cid: number; v: boolean }) => api.markCharge(cid, v), onSuccess: inv });
  const delC = useMutation({ mutationFn: api.deleteCharge, onSuccess: inv });
  const addX = useMutation({
    mutationFn: () => api.addCharge(id, { period, kind: "extra", quantity: 1, amount: Number(ex.amount), note: ex.note }),
    onSuccess: () => { inv(); setExtra(false); setEx({ note: "", amount: "" }); },
  });

  if (!b) return null;
  const cur = b.currency;
  const list = (vids ?? []).filter((v) => filter === "all" || v.approval === filter);
  const toggle = (vid: number) => setSel((x) => (x.includes(vid) ? x.filter((y) => y !== vid) : [...x, vid]));
  const unpaid = (charges ?? []).filter((c) => !c.paid).reduce((a, c) => a + c.amount, 0);

  return (
    <>
      <Link to="/brands" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg"><ArrowLeft className="h-4 w-4" /> Firmalar</Link>
      <div className="card mb-6 overflow-hidden">
        <div className="h-24" style={{ background: `linear-gradient(120deg, ${b.primary_color}, ${b.accent_color})` }} />
        <div className="flex flex-col gap-4 px-6 pb-5 sm:flex-row sm:items-end sm:justify-between">
          <div className="flex items-end gap-4">
            <div className="-mt-10 shrink-0 rounded-2xl border-4 border-panel bg-panel"><BrandMark b={{ name: b.name, logo_url: b.logo_url, color: b.primary_color }} size={72} /></div>
            <div><h1 className="font-display text-2xl font-extrabold">{b.name}</h1><p className="text-sm text-muted">{[b.contact_name, b.contact_email, b.website].filter(Boolean).join(" · ") || "İletişim bilgisi yok"}</p></div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link to={`/studio?brand=${b.id}`}><Button variant="primary" icon={<Sparkles className="h-4 w-4" />}>Kampanya üret</Button></Link>
            <a href={`/api/brands/${b.id}/report?period=${period}`}><Button icon={<FileText className="h-4 w-4" />}>Aylık rapor</Button></a>
            <Button icon={<Pencil className="h-4 w-4" />} onClick={() => setEdit(true)}>Düzenle</Button>
          </div>
        </div>
      </div>

      <div className="mb-6"><Segmented value={tab} onChange={setTab} options={[{ id: "overview", label: "Genel" }, { id: "videos", label: `Videolar (${vids?.length ?? 0})` }, { id: "products", label: `Ürünler (${prods?.length ?? 0})` }, { id: "billing", label: "Faturalama" }]} /></div>

      {tab === "overview" && s && (
        <div className="grid gap-6 xl:grid-cols-[1fr_240px]">
          <div className="space-y-6">
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
              <Kpi label="Hizmet geliri (ay)" value={money(s.fees.month, cur)} />
              <Kpi label="Affiliate (toplam)" value={money(s.kpi.total_revenue, cur)} tone="text-emerald-500" />
              <Kpi label="Maliyet" value={money(s.kpi.total_cost, cur)} />
              <Kpi label="Kâr" value={money(s.profit, cur)} tone={s.profit >= 0 ? "grad-text" : "text-rose-400"} />
              <Kpi label="Hazır video" value={num(s.kpi.videos_done)} />
              <Kpi label="İzlenme" value={num(s.kpi.views)} />
              <Kpi label="Ort. izlenme oranı" value={s.kpi.avg_retention != null ? `%${s.kpi.avg_retention}` : "—"} />
              <Kpi label="Tahsil edilmemiş" value={money(s.fees.unpaid, cur)} tone={s.fees.unpaid ? "text-amber-500" : undefined} />
            </div>
            <div className="card p-5">
              <h3 className="mb-3 font-display font-bold">Son 30 gün affiliate geliri</h3>
              <div className="h-44">
                <ResponsiveContainer>
                  <AreaChart data={s.series}>
                    <defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={b.primary_color} stopOpacity={0.5} /><stop offset="1" stopColor={b.primary_color} stopOpacity={0} /></linearGradient></defs>
                    <XAxis dataKey="day" tickFormatter={(d) => d.slice(8)} tick={{ fontSize: 11, fill: "rgb(var(--muted))" }} axisLine={false} tickLine={false} />
                    <Tooltip contentStyle={{ background: "rgb(var(--panel))", border: "1px solid rgb(var(--line))", borderRadius: 12, fontSize: 12 }} formatter={(v: number) => money(v, cur)} />
                    <Area type="monotone" dataKey="revenue" stroke={b.primary_color} strokeWidth={2.5} fill="url(#bg)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>
            {(b.guidelines || b.banned_words || b.must_say) && (
              <div className="card space-y-2 p-5 text-sm">
                <h3 className="font-display font-bold">Mesaj kuralları</h3>
                {b.guidelines && <p className="text-muted">{b.guidelines}</p>}
                <div className="flex flex-wrap gap-1.5">
                  {b.must_say && b.must_say.split(",").map((w) => <Pill key={w} className="text-emerald-500">✓ {w.trim()}</Pill>)}
                  {b.banned_words && b.banned_words.split(",").map((w) => <Pill key={w} className="text-rose-400 line-through">{w.trim()}</Pill>)}
                </div>
              </div>
            )}
          </div>
          <div><span className="label text-center">Marka kiti</span><BrandPreview b={b} logo={b.logo_url} /></div>
        </div>
      )}

      {tab === "videos" && (
        <>
          <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <Segmented value={filter} onChange={setFilter} options={[{ id: "all", label: "Tümü" }, ...(["draft", "sent", "approved", "revision"] as Approval[]).map((a) => ({ id: a, label: APPROVAL[a].label }))]} />
            <div className="flex flex-wrap gap-2">
              <Button size="sm" onClick={() => setSel(sel.length === list.length ? [] : list.map((v) => v.id))}>{sel.length === list.length && list.length ? "Seçimi kaldır" : "Tümünü seç"}</Button>
              <a href={sel.length ? `/api/brands/${b.id}/review-package?ids=${sel.join(",")}` : undefined} onClick={() => sel.length && setTimeout(inv, 1500)}>
                <Button size="sm" variant="primary" disabled={!sel.length} icon={<Download className="h-3.5 w-3.5" />}>Onay paketi ({sel.length})</Button>
              </a>
              <Button size="sm" disabled={!sel.length} icon={<Check className="h-3.5 w-3.5" />} onClick={() => approve.mutate("approved")}>Onaylandı</Button>
              <Button size="sm" disabled={!sel.length} icon={<RotateCcw className="h-3.5 w-3.5" />} onClick={() => approve.mutate("revision")}>Revizyon</Button>
            </div>
          </div>
          {list.length === 0 && <Empty icon={<Package className="h-6 w-6" />} title="Video yok" desc="Bu filtrede tamamlanmış video bulunmuyor." />}
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
            {list.map((v) => (
              <div key={v.id} className="relative">
                <VideoCard v={v} onOpen={() => setOpen(v.id)} />
                <button onClick={() => toggle(v.id)} className={cn("absolute bottom-3 right-3 z-10 grid h-7 w-7 place-items-center rounded-lg border-2 transition",
                  sel.includes(v.id) ? "border-brand bg-brand text-white" : "border-line bg-panel/90 text-transparent hover:border-brand")}><Check className="h-4 w-4" /></button>
              </div>
            ))}
          </div>
        </>
      )}

      {tab === "products" && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {prods?.map((p) => (
            <div key={p.id} className="card flex items-center gap-3 p-3">
              <div className="h-16 w-16 shrink-0 overflow-hidden rounded-xl bg-white">{p.image_url && <img src={p.image_url} className="h-full w-full object-contain" />}</div>
              <div className="min-w-0"><div className="truncate text-sm font-semibold">{p.name}</div><div className="text-xs text-muted">{p.price ? money(p.price, p.currency) : "—"}</div>
                {p.cutout_url ? <Pill className="mt-1 text-emerald-500">Kesildi</Pill> : <Pill className="mt-1">Kesim yok</Pill>}</div>
            </div>
          ))}
          <Link to="/products" className="card grid place-items-center p-6 text-sm text-muted hover:text-fg"><span className="flex items-center gap-2"><Plus className="h-4 w-4" />Ürünler sayfasından ekle</span></Link>
        </div>
      )}

      {tab === "billing" && (
        <div className="card overflow-hidden">
          <div className="flex flex-col gap-3 border-b border-line p-5 sm:flex-row sm:items-center sm:justify-between">
            <div><h3 className="font-display font-bold">Tahakkuklar</h3><p className="text-xs text-muted">Aylık {money(b.monthly_fee, cur)} + video başı {money(b.per_video_fee, cur)} · Tahsil edilmemiş: <b className="text-amber-500">{money(unpaid, cur)}</b></p></div>
            <div className="flex flex-wrap items-center gap-2">
              <input type="month" className="input w-40" value={period} onChange={(e) => setPeriod(e.target.value)} />
              <Button variant="primary" size="sm" loading={gen.isPending} onClick={() => gen.mutate()}>Ay tahakkukunu oluştur</Button>
              <Button size="sm" icon={<Plus className="h-3.5 w-3.5" />} onClick={() => setExtra(true)}>Ek kalem</Button>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="bg-elev/30 text-left text-xs uppercase tracking-wider text-muted">{["Dönem", "Kalem", "Adet", "Tutar", "Durum", ""].map((h) => <th key={h} className="px-5 py-2.5 font-medium">{h}</th>)}</tr></thead>
              <tbody>
                {charges?.map((c) => (
                  <tr key={c.id} className="border-t border-line/50">
                    <td className="px-5 py-3 font-mono text-xs">{c.period}</td>
                    <td className="px-5 py-3">{c.note || c.kind}</td><td className="px-5 py-3">{c.quantity}</td>
                    <td className="px-5 py-3 font-semibold">{money(c.amount, cur)}</td>
                    <td className="px-5 py-3"><button onClick={() => paid.mutate({ cid: c.id, v: !c.paid })} className={cn("rounded-full px-2.5 py-0.5 text-xs font-semibold", c.paid ? "bg-emerald-500/15 text-emerald-500" : "bg-amber-500/15 text-amber-500")}>{c.paid ? "Ödendi" : "Bekliyor"}</button></td>
                    <td className="px-5 py-3 text-right"><button onClick={() => delC.mutate(c.id)} className="rounded-lg p-1.5 text-muted hover:text-rose-400"><Trash2 className="h-3.5 w-3.5" /></button></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {charges?.length === 0 && <p className="py-10 text-center text-sm text-muted">Henüz tahakkuk yok — ay sonunda "Ay tahakkukunu oluştur".</p>}
          </div>
        </div>
      )}

      <Modal open={extra} onClose={() => setExtra(false)} title="Ek kalem" footer={<Button variant="primary" disabled={!ex.amount} loading={addX.isPending} onClick={() => addX.mutate()}>Ekle</Button>}>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Açıklama" className="sm:col-span-2"><input className="input" value={ex.note} onChange={(e) => setEx({ ...ex, note: e.target.value })} placeholder="Ek revizyon, acil teslim…" /></Field>
          <Field label={`Tutar (${cur})`}><input type="number" className="input" value={ex.amount} onChange={(e) => setEx({ ...ex, amount: e.target.value })} /></Field>
          <Field label="Dönem"><input type="month" className="input" value={period} onChange={(e) => setPeriod(e.target.value)} /></Field>
        </div>
      </Modal>
      <BrandForm open={edit} initial={b} onClose={() => setEdit(false)} />
      <VideoModal v={vids?.find((x) => x.id === open) ?? null} onClose={() => setOpen(null)} />
    </>
  );
}
