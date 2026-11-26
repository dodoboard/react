import { useQuery } from "@tanstack/react-query";
import { Film, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { VideoCard, VideoModal } from "@/components/VideoCard";
import { Empty, PageHeader, Segmented, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";

export default function Library() {
  const { data } = useQuery({ queryKey: ["videos", "library"], queryFn: () => api.videos("?status=done&limit=500") });
  const [q, setQ] = useState("");
  const [f, setF] = useState<"all" | "fav" | "unpub" | "pub">("all");
  const [open, setOpen] = useState<number | null>(null);
  const list = useMemo(() => (data ?? []).filter((v) =>
    (f === "all" || (f === "fav" && v.favorite) || (f === "unpub" && !v.published_at) || (f === "pub" && v.published_at)) &&
    (!q || `${v.hook} ${v.product_name} ${v.campaign_name}`.toLowerCase().includes(q.toLowerCase()))), [data, q, f]);

  return (
    <>
      <PageHeader eyebrow="Kütüphane" title="Hazır videolar" desc="Önizle, paylaşım metnini kopyala, yayın paketini indir veya planla." />
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative max-w-sm flex-1"><Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
          <input className="input pl-9" placeholder="Hook, ürün veya kampanya ara…" value={q} onChange={(e) => setQ(e.target.value)} /></div>
        <Segmented value={f} onChange={setF} options={[{ id: "all", label: "Tümü" }, { id: "unpub", label: "Yayınlanmadı" }, { id: "pub", label: "Yayında" }, { id: "fav", label: "Favoriler" }]} />
      </div>
      {data && list.length === 0 && <Empty icon={<Film className="h-6 w-6" />} title="Video bulunamadı" desc="Filtreleri değiştir veya yeni kampanya başlat." />}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
        {!data && Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="aspect-[9/16]" />)}
        {list.map((v) => <VideoCard key={v.id} v={v} onOpen={() => setOpen(v.id)} />)}
      </div>
      <VideoModal v={data?.find((x) => x.id === open) ?? null} onClose={() => setOpen(null)} />
    </>
  );
}
