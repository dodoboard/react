import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileUp, Plus, Trash2, Wallet } from "lucide-react";
import { useRef, useState } from "react";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { toast } from "sonner";
import { Button, Field, Modal, PageHeader, Pill } from "@/components/ui";
import { api } from "@/lib/api";
import { cn, money, num } from "@/lib/utils";

export default function RevenuePage() {
  const qc = useQueryClient();
  const { data: rows } = useQuery({ queryKey: ["revenue"], queryFn: api.revenue });
  const { data: s } = useQuery({ queryKey: ["summary"], queryFn: () => api.summary(30) });
  const { data: vids } = useQuery({ queryKey: ["videos", "library"], queryFn: () => api.videos("?status=done&limit=500") });
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ day: new Date().toISOString().slice(0, 10), video_id: "", platform: "", amount: "", clicks: "", conversions: "", views: "", note: "" });
  const fileRef = useRef<HTMLInputElement>(null);
  const cur = s?.currency ?? "TRY";
  const inv = () => { qc.invalidateQueries({ queryKey: ["revenue"] }); qc.invalidateQueries({ queryKey: ["summary"] }); qc.invalidateQueries({ queryKey: ["campaigns"] }); };

  const add = useMutation({
    mutationFn: () => api.addRevenue({ ...f, video_id: f.video_id ? +f.video_id : null, amount: +f.amount || 0, clicks: +f.clicks || 0, conversions: +f.conversions || 0, views: +f.views || 0 }),
    onSuccess: () => { inv(); setOpen(false); toast.success("Gelir eklendi"); },
    onError: (e: Error) => toast.error(e.message),
  });
  const del = useMutation({ mutationFn: api.deleteRevenue, onSuccess: inv });
  const imp = useMutation({
    mutationFn: api.importRevenue,
    onSuccess: (r) => { inv(); toast.success(`${r.added} satır içe aktarıldı`, { description: `${r.matched} tanesi videoya eşleşti (subid)` }); },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <>
      <PageHeader eyebrow="Kazanç" title="Gelir & ROI" desc="Affiliate panelinden komisyonları gir veya CSV yükle. subid sütunu sayesinde her kazanç doğru videoya bağlanır."
        actions={<>
          <Button icon={<FileUp className="h-4 w-4" />} loading={imp.isPending} onClick={() => fileRef.current?.click()}>CSV içe aktar</Button>
          <input ref={fileRef} type="file" accept=".csv,text/csv" hidden onChange={(e) => { const x = e.target.files?.[0]; if (x) imp.mutate(x); e.target.value = ""; }} />
          <Button variant="primary" icon={<Plus className="h-4 w-4" />} onClick={() => setOpen(true)}>Gelir ekle</Button>
        </>} />

      <div className="grid gap-6 xl:grid-cols-3">
        <div className="card p-5 xl:col-span-2">
          <h3 className="mb-4 font-display font-bold">Kampanya bazlı ROI</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="border-b border-line text-left text-xs uppercase tracking-wider text-muted">
                <th className="pb-2 font-medium">Kampanya</th><th className="pb-2 text-right font-medium">Video</th><th className="pb-2 text-right font-medium">Gelir</th><th className="pb-2 text-right font-medium">Maliyet</th><th className="pb-2 text-right font-medium">ROI</th></tr></thead>
              <tbody>
                {s?.campaigns.map((c) => (
                  <tr key={c.id} className="border-b border-line/50 last:border-0">
                    <td className="py-3"><div className="font-medium">{c.name}</div><div className="text-xs text-muted">{c.product}</div></td>
                    <td className="py-3 text-right">{c.videos}</td>
                    <td className="py-3 text-right font-semibold">{money(c.revenue, cur)}</td>
                    <td className="py-3 text-right text-muted">{money(c.cost, cur)}</td>
                    <td className="py-3 text-right">{c.roi === null ? "—" : <span className={cn("rounded-md px-2 py-0.5 text-xs font-bold", c.roi >= 0 ? "bg-emerald-500/15 text-emerald-500" : "bg-rose-500/15 text-rose-400")}>%{num(c.roi)}</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {s?.campaigns.length === 0 && <p className="py-8 text-center text-sm text-muted">Henüz kampanya yok.</p>}
          </div>
        </div>
        <div className="card p-5">
          <h3 className="mb-4 font-display font-bold">Platforma göre</h3>
          <div className="h-56">
            <ResponsiveContainer>
              <BarChart data={s?.platforms ?? []} layout="vertical" margin={{ left: 10 }}>
                <XAxis type="number" hide /><YAxis type="category" dataKey="platform" tick={{ fontSize: 12, fill: "rgb(var(--muted))" }} axisLine={false} tickLine={false} width={80} />
                <Tooltip cursor={{ fill: "rgb(var(--elev))" }} contentStyle={{ background: "rgb(var(--panel))", border: "1px solid rgb(var(--line))", borderRadius: 12, fontSize: 12 }} formatter={(v: number) => money(v, cur)} />
                <Bar dataKey="revenue" fill="#8B5CF6" radius={[0, 8, 8, 0]} barSize={18} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-2 rounded-xl bg-elev/40 p-3 text-xs text-muted">
            <b className="text-fg">CSV formatı:</b> date, subid, amount, clicks, conversions, views, platform — Türkçe başlıklar (tarih, komisyon, tıklama, sipariş) da tanınır.
          </div>
        </div>
      </div>

      <div className="card mt-6 overflow-hidden">
        <div className="flex items-center justify-between border-b border-line px-5 py-4"><h3 className="font-display font-bold">Kayıtlar</h3><Pill>{rows?.length ?? 0}</Pill></div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="bg-elev/30 text-left text-xs uppercase tracking-wider text-muted">
              {["Tarih", "Video", "Kampanya", "Platform", "Tıklama", "Satış", "Tutar", ""].map((h) => <th key={h} className="px-5 py-2.5 font-medium">{h}</th>)}</tr></thead>
            <tbody>
              {rows?.map((r) => (
                <tr key={r.id} className="border-t border-line/50">
                  <td className="px-5 py-3 font-mono text-xs">{r.day}</td><td className="px-5 py-3">{r.video_label ?? "—"}</td>
                  <td className="max-w-[200px] truncate px-5 py-3 text-muted">{r.campaign_name ?? "—"}</td><td className="px-5 py-3">{r.platform || "—"}</td>
                  <td className="px-5 py-3">{num(r.clicks)}</td><td className="px-5 py-3">{num(r.conversions)}</td>
                  <td className="px-5 py-3 font-semibold text-emerald-500">{money(r.amount, cur)}</td>
                  <td className="px-5 py-3 text-right"><button onClick={() => del.mutate(r.id)} className="rounded-lg p-1.5 text-muted hover:text-rose-400"><Trash2 className="h-3.5 w-3.5" /></button></td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows?.length === 0 && <div className="flex flex-col items-center py-12 text-sm text-muted"><Wallet className="mb-2 h-6 w-6 opacity-50" />Henüz gelir kaydı yok</div>}
        </div>
      </div>

      <Modal open={open} onClose={() => setOpen(false)} title="Gelir ekle"
        footer={<><Button variant="ghost" onClick={() => setOpen(false)}>Vazgeç</Button><Button variant="primary" loading={add.isPending} onClick={() => add.mutate()}>Ekle</Button></>}>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Tarih"><input type="date" className="input" value={f.day} onChange={(e) => setF({ ...f, day: e.target.value })} /></Field>
          <Field label={`Tutar (${cur})`}><input type="number" step="0.01" className="input" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></Field>
          <Field label="Video" className="sm:col-span-2">
            <select className="input" value={f.video_id} onChange={(e) => setF({ ...f, video_id: e.target.value })}>
              <option value="">— Videoya bağlama —</option>
              {vids?.map((v) => <option key={v.id} value={v.id}>#{v.id} {v.ab_label} · {v.hook.slice(0, 60)}</option>)}
            </select>
          </Field>
          <Field label="Platform"><input className="input" value={f.platform} onChange={(e) => setF({ ...f, platform: e.target.value })} placeholder="tiktok, trendyol…" /></Field>
          <Field label="İzlenme"><input type="number" className="input" value={f.views} onChange={(e) => setF({ ...f, views: e.target.value })} /></Field>
          <Field label="Tıklama"><input type="number" className="input" value={f.clicks} onChange={(e) => setF({ ...f, clicks: e.target.value })} /></Field>
          <Field label="Satış"><input type="number" className="input" value={f.conversions} onChange={(e) => setF({ ...f, conversions: e.target.value })} /></Field>
        </div>
      </Modal>
    </>
  );
}
