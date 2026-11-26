import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Pause, Play, Plus, Sparkles, Trash2, UserRound, Wand2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Button, Empty, Field, Modal, PageHeader, Pill } from "@/components/ui";
import { api, type Character } from "@/lib/api";
import { cn } from "@/lib/utils";

const BLANK: Partial<Character> = { name: "", persona: "", speaking_style: "", catchphrases: "", opening_line: "", closing_line: "",
  look_prompt: "", avatar: "", voice_id: "", language: "tr" };

export function useVoicePreview() {
  const audio = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState<number | null>(null);
  const m = useMutation({
    mutationFn: (id: number) => api.previewVoice(id),
    onSuccess: (r, id) => {
      audio.current?.pause();
      audio.current = new Audio(r.url);
      audio.current.onended = () => setPlaying(null);
      audio.current.play();
      setPlaying(id);
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const toggle = (id: number) => { if (playing === id) { audio.current?.pause(); setPlaying(null); } else m.mutate(id); };
  return { toggle, playing, loading: m.isPending ? m.variables : null };
}

const VS_DEFAULT = { stability: 0.4, similarity_boost: 0.8, style: 0.35, speed: 0.97, exaggeration: 0.6, cfg_weight: 0.4 };

function VoiceSettings({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  let v = VS_DEFAULT;
  try { v = { ...VS_DEFAULT, ...(value ? JSON.parse(value) : {}) }; } catch { /* keep defaults */ }
  const set = (k: keyof typeof VS_DEFAULT, x: number) => onChange(JSON.stringify({ ...v, [k]: x }));
  const rows: [keyof typeof VS_DEFAULT, string, number, number, string][] = [
    ["stability", "Stabilite", 0, 1, "Düşük = daha duygulu, değişken"], ["style", "Stil vurgusu", 0, 1, "Anlatıcı karakteri belirginleşir"],
    ["speed", "Hız", 0.7, 1.2, "Belgesel için 0.92-1.0"], ["exaggeration", "Duygu (lokal ses)", 0.2, 1.2, "Chatterbox"],
  ];
  return (
    <div className="rounded-xl border border-line bg-elev/30 p-3 sm:col-span-2">
      <span className="label">Ses karakteri</span>
      <div className="grid gap-x-4 gap-y-2 sm:grid-cols-2">
        {rows.map(([k, label, min, max, hint]) => (
          <label key={k} className="text-xs"><div className="flex justify-between"><span>{label}</span><span className="font-mono text-muted">{v[k].toFixed(2)}</span></div>
            <input type="range" min={min} max={max} step={0.01} value={v[k]} onChange={(e) => set(k, +e.target.value)} className="w-full accent-violet-500" title={hint} /></label>
        ))}
      </div>
    </div>
  );
}

function CharacterForm({ initial, open, onClose }: { initial: Partial<Character> | null; open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const [c, setC] = useState<Partial<Character>>(BLANK);
  const [niche, setNiche] = useState("");
  const [vibe, setVibe] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const { data: avatars } = useQuery({ queryKey: ["avatars"], queryFn: api.avatars, enabled: open });
  const { data: voices } = useQuery({ queryKey: ["voices"], queryFn: api.voices, enabled: open, retry: false });
  useEffect(() => { if (open) setC(initial ?? BLANK); }, [open, initial]);
  const set = (k: keyof Character) => (e: { target: { value: string } }) => setC({ ...c, [k]: e.target.value });

  const persona = useMutation({
    mutationFn: () => api.generatePersona({ niche, name: c.name, vibe, language: c.language }),
    onSuccess: (p) => { setC((x) => ({ ...x, ...p, name: x.name || p.name })); toast.success("Kişilik oluşturuldu"); },
    onError: (e: Error) => toast.error(e.message),
  });
  const face = useMutation({
    mutationFn: () => api.generateAvatar(c.look_prompt || `${c.name}, documentary presenter`),
    onSuccess: (a) => { qc.invalidateQueries({ queryKey: ["avatars"] }); setC((x) => ({ ...x, avatar: a.name })); },
    onError: (e: Error) => toast.error(e.message),
  });
  const upload = useMutation({
    mutationFn: api.uploadAvatar,
    onSuccess: (a) => { qc.invalidateQueries({ queryKey: ["avatars"] }); setC((x) => ({ ...x, avatar: a.name })); },
  });
  const save = useMutation({
    mutationFn: () => api.saveCharacter(c),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["characters"] }); toast.success("Karakter kaydedildi"); onClose(); },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <Modal open={open} onClose={onClose} wide title={c.id ? `${c.name} — düzenle` : "Yeni karakter"}
      footer={<><Button variant="ghost" onClick={onClose}>Vazgeç</Button><Button variant="primary" disabled={!c.name} loading={save.isPending} onClick={() => save.mutate()}>Kaydet</Button></>}>
      <div className="grid gap-6 lg:grid-cols-[1fr_260px]">
        <div className="space-y-4">
          <div className="rounded-2xl border border-brand/30 bg-gradient-to-r from-brand/10 to-brand-2/5 p-4">
            <div className="mb-2 flex items-center gap-2 text-sm font-semibold"><Wand2 className="h-4 w-4 text-brand" /> Kişiliği LLM ile oluştur</div>
            <div className="grid gap-2 sm:grid-cols-[1fr_1fr_auto]">
              <input className="input" value={niche} onChange={(e) => setNiche(e.target.value)} placeholder="Niş: tarih gizemleri, okyanuslar…" />
              <input className="input" value={vibe} onChange={(e) => setVibe(e.target.value)} placeholder="Hava: bilge, esprili, gizemli…" />
              <Button variant="primary" disabled={!niche} loading={persona.isPending} onClick={() => persona.mutate()}>Oluştur</Button>
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="İsim"><input className="input" value={c.name} onChange={set("name")} /></Field>
            <Field label="Dil"><select className="input" value={c.language} onChange={set("language")}>{[["tr", "Türkçe"], ["en", "English"], ["de", "Deutsch"], ["es", "Español"]].map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
            <Field label="Kişilik / biyografi" className="sm:col-span-2"><textarea className="input min-h-[80px]" value={c.persona} onChange={set("persona")} /></Field>
            <Field label="Konuşma tarzı" className="sm:col-span-2"><input className="input" value={c.speaking_style} onChange={set("speaking_style")} /></Field>
            <Field label="İmza açılış"><input className="input" value={c.opening_line} onChange={set("opening_line")} /></Field>
            <Field label="İmza kapanış"><input className="input" value={c.closing_line} onChange={set("closing_line")} /></Field>
            <Field label="İmza ifadeler"><input className="input" value={c.catchphrases} onChange={set("catchphrases")} /></Field>
            <Field label="Ses"><select className="input" value={c.voice_id} onChange={set("voice_id")}><option value="">Varsayılan</option>{voices?.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}</select></Field>
            <VoiceSettings value={c.voice_settings ?? ""} onChange={(v) => setC({ ...c, voice_settings: v })} />
            <Field label="Görünüm (EN, tutarlılık için)" className="sm:col-span-2" hint="Persona görseli ve S2V/kapak üretiminde kullanılır."><textarea className="input text-xs" value={c.look_prompt} onChange={set("look_prompt")} /></Field>
          </div>
        </div>
        <div>
          <span className="label">Görünüm</span>
          <div className="aspect-[3/4] overflow-hidden rounded-2xl border border-line bg-elev">
            {c.avatar ? <img src={avatars?.find((a) => a.name === c.avatar)?.url} className="h-full w-full object-cover" /> : <div className="grid h-full place-items-center text-muted"><UserRound className="h-10 w-10" /></div>}
          </div>
          <div className="mt-2 grid grid-cols-2 gap-2">
            <Button size="sm" variant="primary" icon={<Sparkles className="h-3.5 w-3.5" />} loading={face.isPending} onClick={() => face.mutate()}>Üret</Button>
            <Button size="sm" onClick={() => fileRef.current?.click()}>Yükle</Button>
            <input ref={fileRef} type="file" accept="image/*" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) upload.mutate(f); e.target.value = ""; }} />
          </div>
          <div className="mt-3 flex gap-2 overflow-x-auto pb-1">
            {avatars?.map((a) => (
              <button key={a.name} onClick={() => setC({ ...c, avatar: a.name })} className={cn("h-16 w-12 shrink-0 overflow-hidden rounded-lg border-2", c.avatar === a.name ? "border-brand" : "border-transparent opacity-70")}>
                <img src={a.url} className="h-full w-full object-cover" /></button>
            ))}
          </div>
          <p className="mt-2 text-[11px] text-muted">Kurgusal kişi veya kendi yüzünüz. Gerçek ünlüleri taklit etmeyin. Nötr arka planlı, omuz üstü kadraj en iyi sonucu verir.</p>
        </div>
      </div>
    </Modal>
  );
}

export default function Characters() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["characters"], queryFn: api.characters });
  const [edit, setEdit] = useState<Partial<Character> | null>(null);
  const [open, setOpen] = useState(false);
  const voice = useVoicePreview();
  const del = useMutation({ mutationFn: api.deleteCharacter, onSuccess: () => qc.invalidateQueries({ queryKey: ["characters"] }), onError: (e: Error) => toast.error(e.message) });
  return (
    <>
      <PageHeader eyebrow="Belgesel" title="Karakterler" desc="Kanallarını sunan kalıcı karakterler: görünüş, kişilik, imza cümleler ve ses — her bölümde aynı kimlik."
        actions={<Button variant="primary" icon={<Plus className="h-4 w-4" />} onClick={() => { setEdit(null); setOpen(true); }}>Yeni karakter</Button>} />
      {data?.length === 0 && <Empty icon={<UserRound className="h-6 w-6" />} title="Henüz karakter yok" desc="Nişini yaz, LLM kişiliği oluştursun; Flux ile yüzünü üret, sesini seç." action={<Button variant="primary" onClick={() => setOpen(true)}>Karakter oluştur</Button>} />}
      <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
        {data?.map((c, i) => (
          <motion.div key={c.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }} className="card flex overflow-hidden">
            <div className="w-32 shrink-0 bg-elev">{c.avatar_url ? <img src={c.avatar_url} className="h-full w-full object-cover" /> : <div className="grid h-full place-items-center text-muted"><UserRound className="h-8 w-8" /></div>}</div>
            <div className="flex min-w-0 flex-1 flex-col p-4">
              <h3 className="font-display text-lg font-bold">{c.name}</h3>
              <p className="line-clamp-3 text-xs text-muted">{c.persona || "—"}</p>
              {c.opening_line && <p className="mt-2 line-clamp-2 text-xs italic">“{c.opening_line}”</p>}
              <div className="mt-auto flex items-center gap-2 pt-3">
                <Pill>{c.channels} kanal</Pill>
                <button onClick={() => voice.toggle(c.id)} className="ml-auto grid h-8 w-8 place-items-center rounded-full grad-bg text-white" title="Sesi dinle">
                  {voice.playing === c.id ? <Pause className="h-3.5 w-3.5" /> : <Play className={cn("ml-0.5 h-3.5 w-3.5", voice.loading === c.id && "animate-pulse")} />}</button>
                <Button size="sm" onClick={() => { setEdit(c); setOpen(true); }}>Düzenle</Button>
                <button onClick={() => confirm("Karakter silinsin mi?") && del.mutate(c.id)} className="rounded-lg p-1.5 text-muted hover:text-rose-400"><Trash2 className="h-4 w-4" /></button>
              </div>
            </div>
          </motion.div>
        ))}
      </div>
      <CharacterForm open={open} initial={edit} onClose={() => setOpen(false)} />
    </>
  );
}
