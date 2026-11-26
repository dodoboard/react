import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Play, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { VideoCard, VideoModal } from "@/components/VideoCard";
import { Button, PageHeader, Pill, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { money, PLATFORMS } from "@/lib/utils";

export default function CampaignDetail() {
  const id = Number(useParams().id);
  const nav = useNavigate();
  const qc = useQueryClient();
  const { data: c } = useQuery({ queryKey: ["campaign", id], queryFn: () => api.campaign(id) });
  const [open, setOpen] = useState<number | null>(null);
  const render = useMutation({
    mutationFn: () => api.renderCampaign(id),
    onSuccess: (r) => { toast.success(`${r.queued.length} video render kuyruğunda`); qc.invalidateQueries({ queryKey: ["campaign", id] }); },
  });
  const del = useMutation({ mutationFn: () => api.deleteCampaign(id), onSuccess: () => { toast.success("Kampanya silindi"); nav("/campaigns"); }, onError: (e: Error) => toast.error(e.message) });
  const pending = c?.videos?.filter((v) => v.status === "scripted" || v.status === "failed").length ?? 0;

  return (
    <>
      <Link to="/campaigns" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg"><ArrowLeft className="h-4 w-4" /> Kampanyalar</Link>
      <PageHeader eyebrow={c?.product?.name} title={c?.name ?? "…"}
        desc={c ? `${PLATFORMS.find((p) => p.id === c.target_platform)?.label} · ${c.tone} · ${c.scenes} sahne${c.audience ? " · " + c.audience : ""}` : undefined}
        actions={<>
          {pending > 0 && <Button variant="primary" icon={<Play className="h-4 w-4" />} loading={render.isPending} onClick={() => render.mutate()}>{pending} videoyu render et</Button>}
          <Button variant="danger" icon={<Trash2 className="h-4 w-4" />} onClick={() => confirm("Kampanya ve tüm videoları silinsin mi?") && del.mutate()}>Sil</Button>
        </>} />
      {c && (
        <div className="mb-6 flex flex-wrap gap-2">
          <Pill>Toplam {c.total}</Pill><Pill className="text-emerald-500">Hazır {c.counts.done ?? 0}</Pill>
          <Pill className="text-amber-500">İnceleme {c.counts.scripted ?? 0}</Pill><Pill>Gelir {money(c.revenue)}</Pill>
        </div>
      )}
      {(c?.counts.scripted ?? 0) > 0 && (
        <div className="mb-6 rounded-2xl border border-amber-500/30 bg-amber-500/10 p-4 text-sm">
          Senaryolar hazır. Bir karta tıklayıp hook'u ve sahneleri düzenleyebilir, ardından tek tek ya da toplu render edebilirsin.
        </div>
      )}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
        {!c && Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="aspect-[9/16]" />)}
        {c?.videos?.map((v) => <VideoCard key={v.id} v={v} onOpen={() => setOpen(v.id)} />)}
      </div>
      <VideoModal v={c?.videos?.find((v) => v.id === open) ?? null} onClose={() => setOpen(null)} />
    </>
  );
}
