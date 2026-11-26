import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Clapperboard, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import { Button, Empty, PageHeader, Pill, Progress, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { ago, money, PLATFORMS } from "@/lib/utils";

export default function Campaigns() {
  const { data } = useQuery({ queryKey: ["campaigns"], queryFn: api.campaigns });
  return (
    <>
      <PageHeader eyebrow="Kampanyalar" title="Tüm kampanyalar" desc="Her kampanya bir ürün için birden çok A/B varyantı içerir."
        actions={<Link to="/studio"><Button variant="primary" icon={<Sparkles className="h-4 w-4" />}>Yeni kampanya</Button></Link>} />
      {data?.length === 0 && <Empty icon={<Clapperboard className="h-6 w-6" />} title="Kampanya yok" desc="Stüdyodan ilk kampanyanı oluştur." action={<Link to="/studio"><Button variant="primary">Stüdyoya git</Button></Link>} />}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {!data && Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-44" />)}
        {data?.map((c, i) => {
          const done = c.counts.done ?? 0;
          const failed = c.counts.failed ?? 0;
          const review = c.counts.scripted ?? 0;
          return (
            <motion.div key={c.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }}>
              <Link to={`/campaigns/${c.id}`} className="card group flex gap-4 p-4 transition hover:border-brand/40 hover:shadow-glow">
                <div className="h-36 w-24 shrink-0 overflow-hidden rounded-xl bg-elev">
                  {c.thumb_url ? <img src={c.thumb_url} className="h-full w-full object-cover transition duration-500 group-hover:scale-105" />
                    : c.product?.image_url ? <img src={c.product.image_url} className="h-full w-full bg-white object-contain p-2" /> : null}
                </div>
                <div className="flex min-w-0 flex-1 flex-col">
                  <h3 className="truncate font-semibold">{c.name}</h3>
                  <p className="text-xs text-muted">{ago(c.created_at)} · {PLATFORMS.find((p) => p.id === c.target_platform)?.label}</p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    <Pill>{c.total} varyant</Pill><Pill>{c.tone}</Pill>
                    {review > 0 && <Pill className="border-amber-500/30 text-amber-500">{review} inceleme bekliyor</Pill>}
                    {failed > 0 && <Pill className="border-rose-500/30 text-rose-400">{failed} hata</Pill>}
                  </div>
                  <div className="mt-auto space-y-1.5">
                    <div className="flex justify-between text-xs"><span className="text-muted">{done}/{c.total} hazır</span><span className="font-semibold text-emerald-500">{money(c.revenue)}</span></div>
                    <Progress value={c.total ? (done / c.total) * 100 : 0} />
                  </div>
                </div>
              </Link>
            </motion.div>
          );
        })}
      </div>
    </>
  );
}
