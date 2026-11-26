import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Sparkles, Trash2, Upload, UserRound } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { api, type Format, type I2V } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button, Segmented } from "./ui";

export const FORMATS: { id: Format; label: string; desc: string }[] = [
  { id: "broll", label: "B-roll", desc: "Ürün + atmosfer sahneleri, dış ses" },
  { id: "avatar_hook", label: "Avatar hook", desc: "İlk sahnede kameraya konuşan kişi, sonra ürün" },
  { id: "avatar_full", label: "Tam UGC", desc: "Tüm video konuşan kişi (en yavaş)" },
];

export function I2VPicker({ value, onChange }: { value: I2V; onChange: (v: I2V) => void }) {
  return (
    <div>
      <span className="label">Hareketli sahne (Wan 2.2)</span>
      <Segmented value={value} onChange={onChange} options={[{ id: "off", label: "Kapalı" }, { id: "hook", label: "Sadece hook" }, { id: "all", label: "Tüm sahneler" }]} />
      <p className="mt-1.5 text-xs text-muted">{value === "off" ? "Ken Burns hareketi — en hızlı." : value === "hook" ? "İlk sahne AI video klip: ilk saniyeyi güçlendirir, video başı ~2 dk ek." : "Her sahne klip: en etkileyici, sahne başı ~1.5-3 dk."}</p>
    </div>
  );
}

export function FormatPicker({ format, avatar, onChange }: { format: Format; avatar: string; onChange: (f: Format, avatar: string) => void }) {
  const qc = useQueryClient();
  const { data: avatars } = useQuery({ queryKey: ["avatars"], queryFn: api.avatars });
  const [desc, setDesc] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const gen = useMutation({
    mutationFn: () => api.generateAvatar(desc),
    onSuccess: (a) => { qc.invalidateQueries({ queryKey: ["avatars"] }); onChange(format, a.name); toast.success("Persona üretildi"); },
    onError: (e: Error) => toast.error(e.message),
  });
  const up = useMutation({
    mutationFn: api.uploadAvatar,
    onSuccess: (a) => { qc.invalidateQueries({ queryKey: ["avatars"] }); onChange(format, a.name); },
    onError: (e: Error) => toast.error(e.message),
  });
  const del = useMutation({ mutationFn: api.deleteAvatar, onSuccess: () => qc.invalidateQueries({ queryKey: ["avatars"] }) });

  return (
    <div className="space-y-4">
      <div>
        <span className="label">Video formatı</span>
        <div className="grid gap-2 sm:grid-cols-3">
          {FORMATS.map((f) => (
            <button key={f.id} type="button" onClick={() => onChange(f.id, avatar)}
              className={cn("rounded-2xl border p-3.5 text-left transition", format === f.id ? "border-brand bg-brand/10 shadow-glow" : "border-line bg-elev/30 hover:border-brand/40")}>
              <div className="text-sm font-semibold">{f.label}</div><div className="mt-1 text-[11px] text-muted">{f.desc}</div>
            </button>
          ))}
        </div>
      </div>
      {format !== "broll" && (
        <div className="rounded-2xl border border-line bg-elev/30 p-4">
          <div className="mb-3 flex items-center justify-between"><span className="label mb-0">Persona</span>
            <Button size="sm" variant="ghost" icon={<Upload className="h-3.5 w-3.5" />} onClick={() => fileRef.current?.click()}>Kendi fotoğrafın</Button>
            <input ref={fileRef} type="file" accept="image/*" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) up.mutate(f); e.target.value = ""; }} />
          </div>
          <div className="flex gap-3 overflow-x-auto pb-1">
            {avatars?.map((a) => (
              <div key={a.name} className="group relative shrink-0">
                <button type="button" onClick={() => onChange(format, a.name)}
                  className={cn("h-28 w-16 overflow-hidden rounded-xl border-2 transition", avatar === a.name ? "border-brand shadow-glow" : "border-transparent opacity-80 hover:opacity-100")}>
                  <img src={a.url} className="h-full w-full object-cover" />
                </button>
                <button type="button" onClick={() => del.mutate(a.name)} className="absolute -right-1.5 -top-1.5 hidden rounded-full bg-panel p-1 text-muted shadow group-hover:block hover:text-rose-400"><Trash2 className="h-3 w-3" /></button>
              </div>
            ))}
            {!avatars?.length && <div className="flex h-28 items-center gap-2 text-xs text-muted"><UserRound className="h-4 w-4" />Henüz persona yok</div>}
          </div>
          <div className="mt-3 flex gap-2">
            <input className="input" value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="ör. 25 yaşında enerjik kadın, spor kıyafet, mutfakta" />
            <Button variant="primary" icon={<Sparkles className="h-4 w-4" />} loading={gen.isPending} onClick={() => gen.mutate()}>Üret</Button>
          </div>
          <p className="mt-2 text-[11px] text-muted">Yalnızca kendi yüzünü veya AI ile üretilmiş kurgusal kişileri kullan; gerçek kişileri taklit etme. Wan 2.2 S2V 14B ile dudak senkronu — 16 GB VRAM'de yavaş.</p>
        </div>
      )}
    </div>
  );
}
