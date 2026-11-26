import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Check, Clapperboard, Lightbulb, Plus, Settings2, ShieldAlert, X, Youtube } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis } from "recharts";
import { toast } from "sonner";
import { EpisodeCard, EpisodeModal } from "@/components/EpisodeCard";
import { Button, Empty, Pill, Segmented } from "@/components/ui";
import { api, type Topic } from "@/lib/api";
import { cn, num } from "@/lib/utils";
import { ChannelForm } from "./Channels";

const TOPIC_TONE: Record<Topic["status"], string> = { idea: "text-muted", approved: "text-emerald-500", rejected: "text-rose-400 line-through", used: "text-sky-500" };
const TOPIC_LABEL: Record<Topic["status"], string> = { idea: "Fikir", approved: "Onaylı", rejected: "Reddedildi", used: "Kullanıldı" };

export default function ChannelDetail() {
  const id = Number(useParams().id);
  const qc = useQueryClient();
  const [tab, setTab] = useState<"episodes" | "topics" | "calendar" | "analytics">("episodes");
  const [open, setOpen] = useState<number | null>(null);
  const [edit, setEdit] = useState(false);
  const [newTopic, setNewTopic] = useState("");
  const { data: c } = useQuery({ queryKey: ["channel", id], queryFn: () => api.channel(id) });
  const { data: eps } = useQuery({ queryKey: ["episodes", id], queryFn: () => api.episodes(id) });
  const { data: topics } = useQuery({ queryKey: ["topics", id], queryFn: () => api.topics(id) });
  const { data: ytInfo } = useQuery({ queryKey: ["channel-yt", id], queryFn: () => api.channelYT(id) });
  const { data: stats } = useQuery({ queryKey: ["channel-stats", id], queryFn: () => api.channelStats(id), enabled: tab === "analytics" });
  const inv = () => ["channel", "channels", "episodes", "topics", "channel-yt"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
  const err = (e: Error) => toast.error(e.message);

  const gen = useMutation({ mutationFn: () => api.generateTopics(id, 10), onSuccess: (r) => { inv(); toast.success(`${r.length} yeni konu`); }, onError: err });
  const add = useMutation({ mutationFn: () => api.addTopic(id, newTopic), onSuccess: () => { inv(); setNewTopic(""); }, onError: err });
  const patch = useMutation({ mutationFn: ({ tid, status }: { tid: number; status: Topic["status"] }) => api.patchTopic(tid, { status }), onSuccess: inv, onError: err });
  const produce = useMutation({ mutationFn: (b: { kind: "long" | "short"; topic_id?: number }) => api.createEpisode(id, b), onSuccess: () => { inv(); toast.success("Üretim başladı"); setTab("episodes"); }, onError: err });
  const connect = useMutation({ mutationFn: () => api.connectChannel(id), onSuccess: (r) => { inv(); toast.success(`Bağlandı: ${r.channel?.title ?? ""}`); }, onError: err });

  if (!c) return null;
  const longs = (eps ?? []).filter((e) => e.kind === "long");
  const shorts = (eps ?? []).filter((e) => e.kind === "short");
  const upcoming = (eps ?? []).filter((e) => e.slot_at).sort((a, b) => a.slot_at!.localeCompare(b.slot_at!));

  return (
    <>
      <Link to="/channels" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg"><ArrowLeft className="h-4 w-4" /> Kanallar</Link>
      <div className="card mb-6 flex flex-col gap-5 p-5 md:flex-row md:items-center">
        <div className="h-24 w-24 shrink-0 overflow-hidden rounded-2xl bg-elev">{c.character?.avatar_url && <img src={c.character.avatar_url} className="h-full w-full object-cover" />}</div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2"><h1 className="font-display text-2xl font-extrabold">{c.name}</h1>
            {c.paused ? <Pill>Durduruldu</Pill> : <Pill className="text-emerald-500">Otomatik</Pill>}</div>
          <p className="text-sm text-muted">{c.niche}</p>
          <p className="mt-1 text-xs text-muted">Sunucu: <b className="text-fg">{c.character?.name ?? "—"}</b> · {c.format === "both" ? "Uzun + Shorts" : c.format} · {c.target_minutes} dk · kalite ≥ {c.min_quality}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {ytInfo?.connected
            ? <Pill className="h-10 px-3 text-sm text-red-500">{ytInfo.channel?.thumbnail && <img src={ytInfo.channel.thumbnail} className="h-6 w-6 rounded-full" />}<Youtube className="h-4 w-4" />{ytInfo.channel?.title ?? "Bağlı"}{ytInfo.channel && ` · ${num(ytInfo.channel.subscribers)} abone`}</Pill>
            : <Button icon={<Youtube className="h-4 w-4 text-red-500" />} loading={connect.isPending} onClick={() => connect.mutate()}>YouTube'u bağla</Button>}
          <Button variant="primary" icon={<Clapperboard className="h-4 w-4" />} loading={produce.isPending} onClick={() => produce.mutate({ kind: c.format === "shorts" ? "short" : "long" })}>Şimdi bölüm üret</Button>
          <Button icon={<Settings2 className="h-4 w-4" />} onClick={() => setEdit(true)}>Ayarlar</Button>
        </div>
      </div>

      <div className="mb-6"><Segmented value={tab} onChange={setTab} options={[{ id: "episodes", label: `Bölümler (${eps?.length ?? 0})` }, { id: "topics", label: `Konu havuzu (${c.backlog})` }, { id: "calendar", label: "Takvim" }, { id: "analytics", label: "Analitik" }]} /></div>

      {tab === "episodes" && (
        <div className="space-y-8">
          {eps?.length === 0 && <Empty icon={<Clapperboard className="h-6 w-6" />} title="Henüz bölüm yok" desc="Otomatik mod slot saatlerinden önce üretmeye başlar; hemen denemek için 'Şimdi bölüm üret'." />}
          {longs.length > 0 && <section><h3 className="mb-3 font-display font-bold">Belgeseller</h3>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">{longs.map((e) => <EpisodeCard key={e.id} e={e} onOpen={() => setOpen(e.id)} />)}</div></section>}
          {shorts.length > 0 && <section><h3 className="mb-3 font-display font-bold">Shorts</h3>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-6">{shorts.map((e) => <EpisodeCard key={e.id} e={e} onOpen={() => setOpen(e.id)} />)}</div></section>}
        </div>
      )}

      {tab === "topics" && (
        <div className="card overflow-hidden">
          <div className="flex flex-col gap-3 border-b border-line p-4 sm:flex-row">
            <input className="input flex-1" value={newTopic} onChange={(e) => setNewTopic(e.target.value)} placeholder="Kendi konunu ekle…" onKeyDown={(e) => e.key === "Enter" && newTopic && add.mutate()} />
            <Button icon={<Plus className="h-4 w-4" />} disabled={!newTopic} onClick={() => add.mutate()}>Ekle</Button>
            <Button variant="primary" icon={<Lightbulb className="h-4 w-4" />} loading={gen.isPending} onClick={() => gen.mutate()}>10 fikir üret</Button>
          </div>
          <div className="divide-y divide-line/60">
            {topics?.map((t) => (
              <div key={t.id} className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center">
                <div className="w-12 shrink-0 font-display text-lg font-extrabold">{t.score.toFixed(1)}</div>
                <div className="min-w-0 flex-1">
                  <div className={cn("font-medium", t.status === "rejected" && "text-muted line-through")}>{t.title}</div>
                  <div className="truncate text-xs text-muted">{t.angle}</div>
                  {t.sensitive && <div className="mt-0.5 flex items-center gap-1 text-xs text-rose-400"><ShieldAlert className="h-3 w-3" />Hassas: {t.sensitive_reason}</div>}
                </div>
                <span className={cn("text-xs font-semibold", TOPIC_TONE[t.status])}>{TOPIC_LABEL[t.status]}</span>
                <div className="flex gap-1">
                  {t.status !== "used" && !t.sensitive && t.status !== "approved" && <Button size="sm" icon={<Check className="h-3.5 w-3.5" />} onClick={() => patch.mutate({ tid: t.id, status: "approved" })}>Onayla</Button>}
                  {t.status === "approved" && <Button size="sm" variant="primary" onClick={() => produce.mutate({ kind: c.format === "shorts" ? "short" : "long", topic_id: t.id })}>Üret</Button>}
                  {t.status !== "rejected" && t.status !== "used" && <Button size="sm" variant="ghost" icon={<X className="h-3.5 w-3.5" />} onClick={() => patch.mutate({ tid: t.id, status: "rejected" })} />}
                </div>
              </div>
            ))}
            {topics?.length === 0 && <p className="p-8 text-center text-sm text-muted">Konu havuzu boş — otomatik mod gerektiğinde kendisi de üretir.</p>}
          </div>
        </div>
      )}

      {tab === "calendar" && (
        <div className="grid gap-6 lg:grid-cols-2">
          <div className="card p-5">
            <h3 className="mb-3 font-display font-bold">Önümüzdeki slotlar</h3>
            <div className="space-y-2">{c.next_slots.map((s) => {
              const ep = upcoming.find((e) => e.slot_at && Math.abs(new Date(e.slot_at).getTime() - new Date(s).getTime()) < 60000);
              return (
                <div key={s} className="flex items-center gap-3 rounded-xl bg-elev/40 px-3 py-2 text-sm">
                  <span className="w-36 shrink-0 font-mono text-xs">{new Date(s).toLocaleString("tr-TR", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</span>
                  {ep ? <button onClick={() => setOpen(ep.id)} className="truncate text-left font-medium hover:text-brand">{ep.title}</button> : <span className="text-muted">Boş — otomatik doldurulacak</span>}
                </div>
              );
            })}</div>
          </div>
          <div className="card p-5">
            <h3 className="mb-3 font-display font-bold">Planlanan / yayınlanan</h3>
            <div className="space-y-2">{upcoming.slice(-12).reverse().map((e) => (
              <button key={e.id} onClick={() => setOpen(e.id)} className="flex w-full items-center gap-3 rounded-xl bg-elev/40 px-3 py-2 text-left text-sm">
                <span className="w-36 shrink-0 font-mono text-xs">{new Date(e.slot_at!).toLocaleString("tr-TR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</span>
                <span className="flex-1 truncate">{e.title}</span><Pill>{e.kind === "short" ? "Shorts" : "Belgesel"}</Pill>
              </button>
            ))}</div>
          </div>
        </div>
      )}

      {tab === "analytics" && (
        <div className="grid gap-6 xl:grid-cols-[1fr_380px]">
          <div className="card p-5">
            <h3 className="mb-3 font-display font-bold">Son 28 gün izlenme</h3>
            <div className="h-56"><ResponsiveContainer>
              <AreaChart data={stats?.series ?? []}>
                <defs><linearGradient id="cv" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#ef4444" stopOpacity={0.45} /><stop offset="1" stopColor="#ef4444" stopOpacity={0} /></linearGradient></defs>
                <XAxis dataKey="day" tickFormatter={(d) => d.slice(8)} tick={{ fontSize: 11, fill: "rgb(var(--muted))" }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ background: "rgb(var(--panel))", border: "1px solid rgb(var(--line))", borderRadius: 12, fontSize: 12 }} />
                <Area type="monotone" dataKey="views" stroke="#ef4444" strokeWidth={2.5} fill="url(#cv)" />
              </AreaChart>
            </ResponsiveContainer></div>
          </div>
          <div className="card p-5">
            <h3 className="mb-3 font-display font-bold">En iyi bölümler</h3>
            {stats?.top.length ? stats.top.map((t) => (
              <button key={t.id} onClick={() => setOpen(t.id)} className="flex w-full items-center gap-3 border-b border-line/50 py-2 text-left text-sm last:border-0">
                <span className="flex-1 truncate">{t.title}</span><span className="font-semibold">{num(t.views)}</span>
                {t.retention != null && <span className="w-12 text-right text-xs text-muted">%{t.retention}</span>}
              </button>
            )) : <p className="text-sm text-muted">YouTube Analytics verisi 6 saatte bir çekilir.</p>}
          </div>
        </div>
      )}

      <EpisodeModal id={open} onClose={() => setOpen(null)} />
      <ChannelForm open={edit} initial={c} onClose={() => { setEdit(false); inv(); }} />
    </>
  );
}
