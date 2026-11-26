import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { Building2, Check, ChevronDown } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, type BrandRef } from "@/lib/api";
import { useBrand } from "@/lib/brand";
import { cn } from "@/lib/utils";

export function BrandMark({ b, size = 24 }: { b: Pick<BrandRef, "name" | "logo_url" | "color"> | null | undefined; size?: number }) {
  if (!b) return <span className="grid shrink-0 place-items-center rounded-md bg-elev text-muted" style={{ width: size, height: size }}><Building2 className="h-3.5 w-3.5" /></span>;
  return b.logo_url
    ? <img src={b.logo_url} className="shrink-0 rounded-md bg-white object-contain p-0.5" style={{ width: size, height: size }} />
    : <span className="grid shrink-0 place-items-center rounded-md text-[11px] font-bold text-white" style={{ width: size, height: size, background: b.color }}>{b.name.slice(0, 1).toUpperCase()}</span>;
}

export default function BrandSwitcher() {
  const { brandId, setBrandId } = useBrand();
  const { data } = useQuery({ queryKey: ["brands"], queryFn: api.brands });
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const cur = data?.find((b) => b.id === brandId);
  useEffect(() => {
    if (brandId && data && !cur) setBrandId(null);  // brand deleted
  }, [brandId, data, cur, setBrandId]);
  useEffect(() => {
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    window.addEventListener("mousedown", h);
    return () => window.removeEventListener("mousedown", h);
  }, []);
  const pick = (id: number | null) => { setBrandId(id); setOpen(false); };

  return (
    <div ref={ref} className="relative">
      <button onClick={() => setOpen(!open)}
        className={cn("flex h-10 max-w-[220px] items-center gap-2 rounded-xl border px-2.5 text-sm font-medium transition",
          cur ? "border-brand/40 bg-brand/10" : "border-line bg-elev/50 text-muted hover:text-fg")}>
        <BrandMark b={cur ? { name: cur.name, logo_url: cur.logo_url, color: cur.primary_color } : null} size={22} />
        <span className="hidden truncate sm:block">{cur?.name ?? "Tüm firmalar"}</span>
        <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-60" />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }}
            className="card absolute right-0 top-12 z-50 w-64 overflow-hidden bg-panel p-1.5 sm:left-0 sm:right-auto">
            <button onClick={() => pick(null)} className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm hover:bg-elev">
              <BrandMark b={null} size={22} /><span className="flex-1">Tüm firmalar</span>{!brandId && <Check className="h-4 w-4 text-brand" />}
            </button>
            <div className="my-1 h-px bg-line" />
            <div className="max-h-72 overflow-y-auto">
              {data?.map((b) => (
                <button key={b.id} onClick={() => pick(b.id)} className={cn("flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm hover:bg-elev", !b.active && "opacity-50")}>
                  <BrandMark b={{ name: b.name, logo_url: b.logo_url, color: b.primary_color }} size={22} />
                  <span className="flex-1 truncate">{b.name}</span>{brandId === b.id && <Check className="h-4 w-4 text-brand" />}
                </button>
              ))}
              {data?.length === 0 && <p className="px-2.5 py-2 text-xs text-muted">Henüz firma yok</p>}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
