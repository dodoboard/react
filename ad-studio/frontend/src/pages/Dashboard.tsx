import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { ArrowUpRight, Coins, Film, MousePointerClick, Sparkles, TrendingUp, Wallet } from "lucide-react";
import { type ReactNode, useState } from "react";
import { Link } from "react-router-dom";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { VideoCard, VideoModal } from "@/components/VideoCard";
import { Button, PageHeader, Skeleton } from "@/components/ui";
import { useBrand } from "@/lib/brand";
import { api } from "@/lib/api";
import { ANGLES, cn, money, num } from "@/lib/utils";

function Kpi({ icon, label, value, sub, tone, i }: { icon: ReactNode; label: string; value: string; sub?: string; tone: string; i: number }) {
  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }} className="card relative overflow-hidden p-5">
      <div className={cn("absolute -right-6 -top-6 h-24 w-24 rounded-full opacity-20 blur-2xl", tone)} />
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wider text-muted">{label}</span>
        <span className={cn("grid h-9 w-9 place-items-center rounded-xl text-white", tone)}>{icon}</span>
      </div>
      <div className="mt-3 font-display text-[28px] font-extrabold tracking-tight">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-muted">{sub}</div>}
    </motion.div>
  );
}

export default function Dashboard() {
  const { brandId } = useBrand();
  const { data: upcoming } = useQuery({ queryKey: ["upcoming"], queryFn: api.upcoming, refetchInterval: 60_000 });
  const { data: s } = useQuery({ queryKey: ["summary", 30, brandId], queryFn: () => api.summary(30, brandId) });
  const { data: vids } = useQuery({ queryKey: ["videos", "recent", brandId], queryFn: () => api.videos("?limit=6", brandId) });
  const { data: h } = useQuery({ queryKey: ["health"], queryFn: api.health });
  const [open, setOpen] = useState<number | null>(null);
  const cur = s?.currency ?? "TRY";
  const quota = h?.tts.limit ? Math.max(0, h.tts.limit - (h.tts.used ?? 0)) : null;

  return (
    <>
      <PageHeader eyebrow="Kontrol Merkezi" title="Genel Bakış" desc="Üretim hattının, kazancının ve en iyi performans gösteren reklamlarının özeti."
        actions={<Link to="/studio"><Button variant="primary" size="lg" icon={<Sparkles className="h-4 w-4" />}>Yeni Kampanya</Button></Link>} />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {s ? (<>
          <Kpi i={0} icon={<Wallet className="h-4 w-4" />} label="Bu ay gelir" value={money(s.kpi.month_revenue, cur)} sub={`Toplam ${money(s.kpi.total_revenue, cur)}`} tone="bg-emerald-500" />
          <Kpi i={1} icon={<TrendingUp className="h-4 w-4" />} label="ROI" value={s.kpi.roi === null ? "—" : `%${num(s.kpi.roi)}`} sub={`Maliyet ${money(s.kpi.total_cost, cur)}${s.kpi.rpm != null ? ` · RPM ${money(s.kpi.rpm, cur)}` : ""}`} tone="grad-bg" />
          <Kpi i={2} icon={<Film className="h-4 w-4" />} label="Hazır video" value={num(s.kpi.videos_done)} sub={`${s.kpi.published} yayında · ${s.kpi.scheduled} planlı${s.kpi.views ? ` · ${num(s.kpi.views)} izlenme` : ""}`} tone="bg-sky-500" />
          <Kpi i={3} icon={<Coins className="h-4 w-4" />} label={h?.tts.provider === "elevenlabs" ? "ElevenLabs kota" : "Dönüşüm"}
            value={quota !== null ? num(quota) : num(s.kpi.conversions)} sub={quota !== null ? `karakter kaldı · ${h?.tts.tier ?? ""}` : `${num(s.kpi.clicks)} tıklama`} tone="bg-amber-500" />
        </>) : Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-[132px]" />)}
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-3">
        <div className="card p-5 xl:col-span-2">
          <div className="mb-4 flex items-center justify-between">
            <div><h3 className="font-display font-bold">Gelir vs Maliyet</h3><p className="text-xs text-muted">Son 30 gün</p></div>
            <div className="flex gap-4 text-xs text-muted">
              <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-brand" />Gelir</span>
              <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-zinc-500" />Maliyet</span>
            </div>
          </div>
          <div className="h-64">
            <ResponsiveContainer>
              <AreaChart data={s?.series ?? []} margin={{ left: -12, right: 4, top: 4 }}>
                <defs>
                  <linearGradient id="gr" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#8B5CF6" stopOpacity={0.5} /><stop offset="1" stopColor="#EC4899" stopOpacity={0} /></linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 6" stroke="rgb(var(--line))" vertical={false} />
                <XAxis dataKey="day" tickFormatter={(d) => d.slice(8)} tick={{ fontSize: 11, fill: "rgb(var(--muted))" }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11, fill: "rgb(var(--muted))" }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ background: "rgb(var(--panel))", border: "1px solid rgb(var(--line))", borderRadius: 12, fontSize: 12 }}
                  formatter={(v: number, n: string) => [money(v, cur), n === "revenue" ? "Gelir" : "Maliyet"]} labelFormatter={(d) => new Date(d).toLocaleDateString("tr-TR", { day: "numeric", month: "long" })} />
                <Area type="monotone" dataKey="cost" stroke="#71717a" strokeWidth={1.5} fill="transparent" strokeDasharray="4 4" />
                <Area type="monotone" dataKey="revenue" stroke="#8B5CF6" strokeWidth={2.5} fill="url(#gr)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card p-5">
          <h3 className="font-display font-bold">Kazanan yaklaşımlar</h3>
          <p className="mb-4 text-xs text-muted">Video başına ortalama gelir</p>
          {s?.angles.length ? (
            <div className="space-y-3">
              {s.angles.slice(0, 6).map((a) => {
                const max = s.angles[0].avg || 1;
                return (
                  <div key={a.angle}>
                    <div className="mb-1 flex justify-between text-sm"><span>{ANGLES[a.angle] ?? a.angle}</span><span className="font-semibold">{money(a.avg, cur)}</span></div>
                    <div className="h-2 overflow-hidden rounded-full bg-elev"><motion.div initial={{ width: 0 }} animate={{ width: `${(a.avg / max) * 100}%` }} className="h-full rounded-full grad-bg" /></div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="grid h-48 place-items-center text-center text-sm text-muted">
              <div><MousePointerClick className="mx-auto mb-2 h-6 w-6 opacity-50" />Gelir girdikçe hangi hook türünün<br />daha çok kazandırdığını burada göreceksin.</div>
            </div>
          )}
        </div>
      </div>

      {upcoming && upcoming.length > 0 && !brandId && (
        <div className="card mt-6 p-5">
          <div className="mb-4 flex items-end justify-between">
            <div><h3 className="font-display font-bold">Sıradaki YouTube yayınları</h3><p className="text-xs text-muted">Belgesel kanalları · otomatik</p></div>
            <Link to="/channels" className="text-sm font-medium text-brand">Kanallar</Link>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {upcoming.slice(0, 4).map((e) => (
              <Link key={e.id} to={`/channels/${e.channel_id}`} className="group overflow-hidden rounded-xl border border-line bg-elev/30 transition hover:border-brand/40">
                <div className="aspect-video bg-elev">{e.thumb_url && <img src={e.thumb_url} className="h-full w-full object-cover" />}</div>
                <div className="p-2.5">
                  <p className="line-clamp-1 text-sm font-medium">{e.title}</p>
                  <p className="text-[11px] text-muted">{e.channel_name} · {new Date(e.slot_at!).toLocaleString("tr-TR", { weekday: "short", hour: "2-digit", minute: "2-digit" })} · {e.kind === "short" ? "Shorts" : "Belgesel"}</p>
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}

      {s && !brandId && s.by_brand.length > 0 && (
        <div className="card mt-6 p-5">
          <div className="mb-4 flex items-end justify-between">
            <div><h3 className="font-display font-bold">Firmalara göre kâr</h3><p className="text-xs text-muted">Hizmet bedeli + affiliate − üretim maliyeti</p></div>
            <Link to="/brands" className="text-sm font-medium text-brand">Firmalar</Link>
          </div>
          <div className="space-y-3">
            {s.by_brand.slice(0, 6).map((b) => {
              const max = Math.max(...s.by_brand.map((x) => Math.abs(x.profit)), 1);
              return (
                <Link key={b.id} to={`/brands/${b.id}`} className="grid grid-cols-[140px_1fr_auto] items-center gap-3 text-sm sm:grid-cols-[180px_1fr_auto]">
                  <span className="flex items-center gap-2 truncate"><span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: b.color }} />{b.name}</span>
                  <div className="h-2 overflow-hidden rounded-full bg-elev"><div className="h-full rounded-full" style={{ width: `${(Math.abs(b.profit) / max) * 100}%`, background: b.profit >= 0 ? b.color : "#f43f5e" }} /></div>
                  <span className="text-right font-semibold">{money(b.profit, cur)}<span className="ml-2 hidden text-xs font-normal text-muted sm:inline">{b.videos} video</span></span>
                </Link>
              );
            })}
          </div>
        </div>
      )}

      {s && s.hook_retention.length > 0 && (
        <div className="card mt-6 p-5">
          <div className="mb-4 flex items-end justify-between">
            <div><h3 className="font-display font-bold">Hook tutma oranı</h3><p className="text-xs text-muted">YouTube ortalama izlenme yüzdesi · ort. %{s.kpi.avg_retention ?? "—"}</p></div>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            {s.hook_retention.map((h) => (
              <div key={h.id} className="flex items-center gap-3">
                <div className="w-12 shrink-0 text-right font-display text-lg font-extrabold">%{Math.round(h.retention)}</div>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm">{h.hook}</div>
                  <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-elev"><div className="h-full rounded-full grad-bg" style={{ width: `${Math.min(100, h.retention)}%` }} /></div>
                </div>
                {h.score != null && <span className="text-xs text-muted">★{h.score.toFixed(1)}</span>}
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="mt-8 flex items-center justify-between">
        <h3 className="font-display text-lg font-bold">Son videolar</h3>
        <Link to="/library" className="flex items-center gap-1 text-sm font-medium text-brand">Tümü <ArrowUpRight className="h-4 w-4" /></Link>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        {vids ? vids.map((v) => <VideoCard key={v.id} v={v} onOpen={() => setOpen(v.id)} />)
          : Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="aspect-[9/16]" />)}
        {vids?.length === 0 && <p className="col-span-full text-sm text-muted">Henüz video yok — Kampanya Stüdyosu'ndan ilkini üret.</p>}
      </div>
      <VideoModal v={vids?.find((x) => x.id === open) ?? null} onClose={() => setOpen(null)} />
    </>
  );
}
