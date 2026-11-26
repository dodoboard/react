import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BrainCircuit, CheckCircle2, Coins, Image, KeyRound, Mic, Music2, Palette, RefreshCw, Sparkles, Trash2, Upload, XCircle, Youtube } from "lucide-react";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Button, Field, PageHeader, Segmented, Toggle } from "@/components/ui";
import { api, type Config } from "@/lib/api";
import { gb } from "@/lib/utils";

function Section({ icon, title, desc, children, status }: { icon: ReactNode; title: string; desc: string; children: ReactNode; status?: ReactNode }) {
  return (
    <section className="card p-6">
      <div className="mb-5 flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl grad-bg text-white">{icon}</div>
          <div><h3 className="font-display text-lg font-bold">{title}</h3><p className="text-sm text-muted">{desc}</p></div>
        </div>
        {status}
      </div>
      {children}
    </section>
  );
}

function Status({ ok, text }: { ok?: boolean; text: string }) {
  return ok ? <span className="flex shrink-0 items-center gap-1.5 rounded-lg bg-emerald-500/10 px-2.5 py-1 text-xs font-medium text-emerald-500"><CheckCircle2 className="h-3.5 w-3.5" />{text}</span>
    : <span className="flex max-w-[260px] shrink-0 items-center gap-1.5 truncate rounded-lg bg-rose-500/10 px-2.5 py-1 text-xs font-medium text-rose-400"><XCircle className="h-3.5 w-3.5 shrink-0" /><span className="truncate">{text}</span></span>;
}

function Upload1({ accept, label, onFile }: { accept: string; label: string; onFile: (f: File) => void }) {
  const r = useRef<HTMLInputElement>(null);
  return (<><Button size="sm" icon={<Upload className="h-3.5 w-3.5" />} onClick={() => r.current?.click()}>{label}</Button>
    <input ref={r} type="file" accept={accept} hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); e.target.value = ""; }} /></>);
}

export default function SettingsPage() {
  const qc = useQueryClient();
  const { data: cfg } = useQuery({ queryKey: ["config"], queryFn: api.config });
  const { data: h, refetch: recheck, isFetching } = useQuery({ queryKey: ["health"], queryFn: api.health });
  const { data: models } = useQuery({ queryKey: ["ollama-models"], queryFn: api.ollamaModels, retry: false });
  const { data: wfs } = useQuery({ queryKey: ["workflows"], queryFn: api.workflows });
  const { data: music } = useQuery({ queryKey: ["music"], queryFn: api.music });
  const { data: voices } = useQuery({ queryKey: ["voices"], queryFn: api.voices, retry: false });
  const { data: yt } = useQuery({ queryKey: ["yt"], queryFn: api.ytStatus });
  const [c, setC] = useState<Config | null>(null);
  useEffect(() => { if (cfg) setC(cfg); }, [cfg]);

  const save = useMutation({
    mutationFn: () => api.saveConfig(c!),
    onSuccess: (r) => { qc.setQueryData(["config"], r); toast.success("Ayarlar kaydedildi"); qc.invalidateQueries({ queryKey: ["health"] }); qc.invalidateQueries({ queryKey: ["voices"] }); qc.invalidateQueries({ queryKey: ["ollama-models"] }); },
    onError: (e: Error) => toast.error(e.message),
  });
  const up = (fn: (f: File) => Promise<unknown>, keys: string[]) => (f: File) =>
    fn(f).then(() => { toast.success(`${f.name} yüklendi`); keys.forEach((k) => qc.invalidateQueries({ queryKey: [k] })); }).catch((e: Error) => toast.error(e.message));
  const ytSync = useMutation({ mutationFn: api.ytSync, onSuccess: (r) => { toast.success(`${r.rows} gün/video satırı güncellendi`); qc.invalidateQueries({ queryKey: ["summary"] }); }, onError: (e: Error) => toast.error(e.message) });
  const ytConnect = useMutation({ mutationFn: api.ytConnect, onSuccess: () => { toast.success("YouTube bağlandı"); qc.invalidateQueries({ queryKey: ["yt"] }); }, onError: (e: Error) => toast.error(e.message) });

  if (!c) return null;
  const set = <K extends keyof Config>(k: K) => (e: { target: { value: string } }) =>
    setC({ ...c, [k]: typeof c[k] === "number" ? Number(e.target.value) : e.target.value });

  return (
    <>
      <PageHeader eyebrow="Sistem" title="Ayarlar & Bağlantılar" desc="Tüm servisler lokalde çalışır. Ayarlar data/config.json dosyasında saklanır."
        actions={<>
          <Button icon={<RefreshCw className={isFetching ? "h-4 w-4 animate-spin" : "h-4 w-4"} />} onClick={() => recheck()}>Bağlantıları test et</Button>
          <Button variant="primary" loading={save.isPending} onClick={() => save.mutate()}>Kaydet</Button>
        </>} />
      {c.dry_run && <div className="mb-6 rounded-2xl border border-amber-500/30 bg-amber-500/10 p-4 text-sm">DEMO modu açık (<code>ADF_DRY_RUN=1</code>). Gerçek üretim için .env içinde kapatıp sunucuyu yeniden başlat.</div>}

      <div className="grid gap-6 xl:grid-cols-2">
        <Section icon={<BrainCircuit className="h-5 w-5" />} title="Ollama — Metin yazarı" desc="Senaryo, hook ve açıklamaları yazan lokal LLM."
          status={h && <Status ok={h.ollama.ok} text={h.ollama.ok ? `${h.ollama.models ?? 0} model${h.ollama.model_ready === false ? " · seçili model yok!" : ""}` : h.ollama.error ?? "Bağlanamadı"} />}>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Sunucu"><input className="input font-mono text-xs" value={c.ollama_url} onChange={set("ollama_url")} /></Field>
            <Field label="Model" hint="Önerilen: qwen3:14b veya gemma3:12b (16 GB VRAM)">
              {models?.length ? <select className="input" value={c.ollama_model} onChange={set("ollama_model")}>
                {!models.some((m) => m.name === c.ollama_model) && <option>{c.ollama_model}</option>}
                {models.map((m) => <option key={m.name} value={m.name}>{m.name} · {gb(m.size)} GB</option>)}</select>
                : <input className="input" value={c.ollama_model} onChange={set("ollama_model")} />}
            </Field>
            <Field label={`Yaratıcılık (temperature): ${c.ollama_temperature}`} className="sm:col-span-2">
              <input type="range" min={0.2} max={1.3} step={0.05} value={c.ollama_temperature} onChange={set("ollama_temperature")} className="w-full accent-violet-500" />
            </Field>
          </div>
        </Section>

        <Section icon={<Image className="h-5 w-5" />} title="ComfyUI — Görsel & Video" desc="Sahne görselleri (Flux/SDXL) ve hareketli klipler (Wan 2.2)."
          status={h && <Status ok={h.comfy.ok} text={h.comfy.ok ? `${h.comfy.gpu ?? ""} ${h.comfy.vram_total ? gb(h.comfy.vram_total) + " GB" : ""}` : h.comfy.error ?? "Bağlanamadı"} />}>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Sunucu"><input className="input font-mono text-xs" value={c.comfy_url} onChange={set("comfy_url")} /></Field>
            <Field label="Adım sayısı"><input type="number" className="input" value={c.image_steps} onChange={set("image_steps")} /></Field>
            <Field label="Görsel workflow"><select className="input" value={c.image_workflow} onChange={set("image_workflow")}>{wfs?.map((w) => <option key={w}>{w}</option>)}</select></Field>
            <Field label="Video workflow"><select className="input" value={c.video_workflow} onChange={set("video_workflow")}>{wfs?.map((w) => <option key={w}>{w}</option>)}</select></Field>
            <Field label="Stil eki (her prompt'a)" className="sm:col-span-2"><textarea className="input text-xs" value={c.style_suffix} onChange={set("style_suffix")} /></Field>
            <Field label="Negatif prompt" className="sm:col-span-2"><textarea className="input text-xs" value={c.negative_prompt} onChange={set("negative_prompt")} /></Field>
            <div className="sm:col-span-2"><Toggle checked={c.use_i2v} onChange={(v) => setC({ ...c, use_i2v: v })} label="Tüm kampanyalarda image-to-video" desc="Kampanya bazında da açılabilir." /></div>
            <div className="flex items-center gap-2 sm:col-span-2"><Upload1 accept=".json" label="Workflow yükle (API format)" onFile={up(api.uploadWorkflow, ["workflows"])} />
              <span className="text-xs text-muted">Yer tutucular: {"{{prompt}} {{negative}} {{seed}} {{width}} {{height}} {{image}}"}</span></div>
          </div>
        </Section>

        <Section icon={<Mic className="h-5 w-5" />} title="Seslendirme" desc="ElevenLabs (bulut, en kaliteli) veya Chatterbox (tamamen lokal, MIT lisanslı)."
          status={h && <Status ok={h.tts.ok} text={h.tts.ok ? (h.tts.limit ? `${(h.tts.limit - (h.tts.used ?? 0)).toLocaleString("tr-TR")} karakter kaldı` : h.tts.provider ?? "Hazır") : h.tts.error ?? "Hata"} />}>
          <div className="mb-4"><Segmented value={c.tts_provider} onChange={(v) => setC({ ...c, tts_provider: v })} options={[{ id: "elevenlabs", label: "ElevenLabs" }, { id: "chatterbox", label: "Lokal (Chatterbox)" }]} /></div>
          {c.tts_provider === "elevenlabs" ? (
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="API anahtarı" className="sm:col-span-2"><div className="relative"><KeyRound className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
                <input type="password" className="input pl-9 font-mono text-xs" value={c.elevenlabs_api_key} onChange={set("elevenlabs_api_key")} placeholder="sk_..." /></div></Field>
              <Field label="Varsayılan ses">{voices?.length ? <select className="input" value={c.elevenlabs_voice_id} onChange={set("elevenlabs_voice_id")}>{voices.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}</select>
                : <input className="input font-mono text-xs" value={c.elevenlabs_voice_id} onChange={set("elevenlabs_voice_id")} />}</Field>
              <Field label="Model"><select className="input" value={c.elevenlabs_model} onChange={set("elevenlabs_model")}>
                {["eleven_multilingual_v2", "eleven_v3", "eleven_flash_v2_5", "eleven_turbo_v2_5"].map((m) => <option key={m}>{m}</option>)}</select></Field>
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Referans ses (klonlama)" hint="5-15 sn temiz kayıt yükle. Boşsa varsayılan ses.">
                <select className="input" value={c.chatterbox_voice} onChange={set("chatterbox_voice")}><option value="">Varsayılan</option>{voices?.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}</select></Field>
              <Field label="Whisper modeli (altyazı senkronu)"><select className="input" value={c.whisper_model} onChange={set("whisper_model")}>{["small", "medium", "large-v3", "turbo"].map((m) => <option key={m}>{m}</option>)}</select></Field>
              <div className="sm:col-span-2"><Upload1 accept="audio/*" label="Referans ses yükle" onFile={up(api.uploadVoice, ["voices"])} /></div>
            </div>
          )}
        </Section>

        <Section icon={<Palette className="h-5 w-5" />} title="Marka & Montaj" desc="Altyazı stili, kapanış kartı, uyum etiketleri.">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Marka / hesap adı"><input className="input" value={c.brand_name} onChange={set("brand_name")} placeholder="@hesabin" /></Field>
            <Field label="Varsayılan CTA"><input className="input" value={c.cta_default} onChange={set("cta_default")} /></Field>
            <Field label="Altyazı fontu" hint="data/fonts klasörüne .ttf ekleyebilirsin"><input className="input" value={c.subtitle_font} onChange={set("subtitle_font")} /></Field>
            <Field label="Vurgu rengi"><div className="flex gap-2"><input type="color" className="h-[42px] w-14 cursor-pointer rounded-xl border border-line bg-transparent" value={c.subtitle_highlight} onChange={set("subtitle_highlight")} /><input className="input font-mono" value={c.subtitle_highlight} onChange={set("subtitle_highlight")} /></div></Field>
            <Field label={`Müzik seviyesi: ${Math.round(c.music_volume * 100)}%`}><input type="range" min={0} max={0.6} step={0.01} value={c.music_volume} onChange={set("music_volume")} className="w-full accent-violet-500" /></Field>
            <Field label="Encoder"><select className="input" value={c.video_encoder} onChange={set("video_encoder")}><option value="auto">Otomatik ({h?.encoder})</option><option value="h264_nvenc">NVENC (GPU)</option><option value="libx264">libx264 (CPU)</option></select></Field>
            <Field label="Reklam ibaresi" className="sm:col-span-2" hint="Türkiye'de influencer reklamlarında #reklam / #işbirliği ibaresi zorunludur."><input className="input" value={c.ad_disclosure} onChange={set("ad_disclosure")} /></Field>
            <div className="sm:col-span-2"><Toggle checked={c.ai_label} onChange={(v) => setC({ ...c, ai_label: v })} label="'Yapay zekâ ile üretildi' etiketi" desc="TikTok/YouTube AI içerik politikalarıyla uyum için önerilir." /></div>
          </div>
        </Section>

        <Section icon={<Sparkles className="h-5 w-5" />} title="Kalite & Öğrenme" desc="Ürün sadakati, viral montaj efektleri ve hook turnuvası."
          status={h && <Status ok={h.dry_run || !!h.rembg} text={h.rembg ? "BiRefNet hazır" : "rembg yok — basit kesim"} />}>
          <div className="space-y-4">
            <div>
              <span className="label">Ürün sahneleri</span>
              <Segmented value={c.product_mode} onChange={(v) => setC({ ...c, product_mode: v })} options={[{ id: "composite", label: "Birebir kompozit" }, { id: "kontext", label: "Flux Kontext" }, { id: "off", label: "Kapalı" }]} />
              <p className="mt-1.5 text-xs text-muted">{c.product_mode === "composite" ? "AI arka plan + gerçek ürün fotoğrafı, gölge ve yansıma ile. Ürün piksel-birebir korunur." : c.product_mode === "kontext" ? "Flux Kontext ürünü sahneye yerleştirir — daha doğal ışık, küçük detaylar değişebilir." : "Ürün yalnızca kapanış kartında."}</p>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Altyazı stili"><select className="input" value={c.caption_style} onChange={set("caption_style")}>
                <option value="bold_yellow">Kalın + sarı vurgu</option><option value="white_box">Beyaz kutu</option><option value="gradient_pop">Mor kontur</option></select></Field>
              <Field label={`Geçiş sesi (whoosh): ${Math.round(c.sfx_volume * 100)}%`}><input type="range" min={0} max={1} step={0.05} value={c.sfx_volume} onChange={set("sfx_volume")} className="w-full accent-violet-500" /></Field>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              <Toggle checked={c.hook_punch} onChange={(v) => setC({ ...c, hook_punch: v })} label="Hook punch-in + flaş" />
              <Toggle checked={c.progress_bar} onChange={(v) => setC({ ...c, progress_bar: v })} label="İlerleme çubuğu" />
              <Toggle checked={c.price_badge} onChange={(v) => setC({ ...c, price_badge: v })} label="Fiyat rozeti" />
              <Toggle checked={c.hook_tournament} onChange={(v) => setC({ ...c, hook_tournament: v })} label="Hook turnuvası" desc={`Slot başı ${c.hooks_per_slot} aday, LLM jürisi seçer`} />
            </div>
            <div className="rounded-2xl border border-line bg-elev/30 p-4">
              <div className="mb-3 text-sm font-semibold">Gerçekçilik</div>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="sm:col-span-2"><Toggle checked={c.realism} onChange={(v) => setC({ ...c, realism: v })} label="Sinematografi reçeteleri" desc="Kamera/lens/ışık/film dokusu dili + 'AI görünümü' negatifleri" /></div>
                <div className="sm:col-span-2"><Toggle checked={c.identity_lock} onChange={(v) => setC({ ...c, identity_lock: v })} label="Karakter kimlik kilidi (Flux Kontext)" desc="Sunucu her bölümde aynı yüzle, mekâna uygun orta/yakın planlarla (A/B kamera)" /></div>
                <Field label="Realism LoRA (models/loras)" hint="Boşsa LoRA'sız; doluysa flux_realism_lora kullanılır"><input className="input font-mono text-xs" value={c.realism_lora} onChange={set("realism_lora")} placeholder="flux_realism_lora.safetensors" /></Field>
                <Field label={`LoRA gücü: ${c.realism_lora_strength}`}><input type="range" min={0} max={1.2} step={0.05} value={c.realism_lora_strength} onChange={set("realism_lora_strength")} className="w-full accent-violet-500" /></Field>
                <Field label="Upscale modeli"><input className="input font-mono text-xs" value={c.upscale_model} onChange={set("upscale_model")} /></Field>
                <Field label="Hızlı i2v LoRA (Lightning)" hint="Doluysa 6 adımlık hızlı workflow"><input className="input font-mono text-xs" value={c.i2v_fast_lora} onChange={set("i2v_fast_lora")} /></Field>
                <Field label={`Belgesel hareketli çekim oranı: %${Math.round(c.doc_i2v_ratio * 100)}`} hint="Bölüm açılışları önce, sonra en uzun çekimler"><input type="range" min={0} max={1} step={0.05} value={c.doc_i2v_ratio} onChange={set("doc_i2v_ratio")} className="w-full accent-violet-500" /></Field>
                <Field label={`Sunucu klip parçası: ${c.presenter_chunk} sn`} hint="16 GB VRAM'de 6-10 sn"><input type="range" min={4} max={20} step={1} value={c.presenter_chunk} onChange={set("presenter_chunk")} className="w-full accent-violet-500" /></Field>
                <Field label="Konuşan sunucu motoru"><select className="input" value={c.avatar_workflow} onChange={set("avatar_workflow")}>{wfs?.filter((w) => /talk|s2v/.test(w)).map((w) => <option key={w}>{w}</option>)}</select></Field>
                <Field label="Renk (reklam / belgesel)"><div className="flex gap-2">
                  {(["lut_ads", "lut_doc"] as const).map((k) => <select key={k} className="input" value={c[k]} onChange={set(k)}>{["none", "neutral", "warm_film", "cool_doc", "teal_orange"].map((x) => <option key={x}>{x}</option>)}</select>)}
                </div></Field>
              </div>
            </div>
            <Field label="Varsayılan i2v modu"><select className="input" value={c.i2v_mode} onChange={set("i2v_mode")}><option value="off">Kapalı</option><option value="hook">Sadece hook sahnesi</option><option value="all">Tüm sahneler</option></select></Field>
          </div>
        </Section>

        <Section icon={<Music2 className="h-5 w-5" />} title="Müzik kütüphanesi" desc="Telifsiz fon müzikleri — konuşma sırasında otomatik kısılır (ducking).">
          <div className="space-y-2">
            {music?.map((m) => (
              <div key={m.name} className="flex items-center justify-between rounded-xl border border-line bg-elev/30 px-3 py-2 text-sm">
                <span className="truncate">{m.name}</span>
                <button onClick={() => api.deleteMusic(m.name).then(() => qc.invalidateQueries({ queryKey: ["music"] }))} className="rounded-lg p-1.5 text-muted hover:text-rose-400"><Trash2 className="h-3.5 w-3.5" /></button>
              </div>
            ))}
            {music?.length === 0 && <p className="text-sm text-muted">Müzik yok — videolar müziksiz render edilir.</p>}
            <Upload1 accept="audio/*" label="Müzik yükle" onFile={up(api.uploadMusic, ["music"])} />
          </div>
        </Section>

        <Section icon={<Coins className="h-5 w-5" />} title="Maliyet modeli" desc="ROI hesaplaması için. Elektrik + ses maliyeti video başına hesaplanır.">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Para birimi"><select className="input" value={c.currency} onChange={set("currency")}>{["TRY", "USD", "EUR"].map((x) => <option key={x}>{x}</option>)}</select></Field>
            <Field label="TTS maliyeti / 1000 karakter"><input type="number" step="0.1" className="input" value={c.tts_cost_per_1k_chars} onChange={set("tts_cost_per_1k_chars")} /></Field>
            <Field label="GPU güç tüketimi (W)"><input type="number" className="input" value={c.gpu_watts} onChange={set("gpu_watts")} /></Field>
            <Field label="Elektrik (kWh fiyatı)"><input type="number" step="0.01" className="input" value={c.kwh_price} onChange={set("kwh_price")} /></Field>
          </div>
        </Section>

        <Section icon={<Youtube className="h-5 w-5" />} title="YouTube Shorts (opsiyonel)" desc="Resmi Data API ile direkt yükleme ve takvimden otomatik yayın."
          status={yt && <Status ok={yt.connected} text={yt.connected ? "Bağlı" : !yt.installed ? "Paket kurulu değil" : !yt.has_secret ? "Client secret yok" : "Bağlı değil"} />}>
          <div className="space-y-4">
            <ol className="list-decimal space-y-1 pl-5 text-sm text-muted">
              <li>Google Cloud Console → YouTube Data API v3'ü etkinleştir</li>
              <li>OAuth istemcisi (Desktop app) oluştur, JSON'u indir ve aşağıdan yükle</li>
              <li>"Bağlan" ile tarayıcıda hesabını yetkilendir</li>
            </ol>
            <div className="flex flex-wrap gap-2">
              <Upload1 accept=".json" label="client_secret.json" onFile={up(api.ytSecret, ["yt"])} />
              <Button size="sm" variant="primary" disabled={!yt?.has_secret} loading={ytConnect.isPending} onClick={() => ytConnect.mutate()}>{yt?.connected && !yt.analytics ? "Analitik için yeniden bağlan" : "Bağlan"}</Button>
              <Button size="sm" disabled={!yt?.analytics} loading={ytSync.isPending} icon={<RefreshCw className="h-3.5 w-3.5" />} onClick={() => ytSync.mutate()}>İstatistikleri çek</Button>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Gizlilik"><select className="input" value={c.youtube_privacy} onChange={set("youtube_privacy")}><option value="private">Özel</option><option value="unlisted">Liste dışı</option><option value="public">Herkese açık</option></select></Field>
            </div>
            <Toggle checked={c.youtube_auto_upload} onChange={(v) => setC({ ...c, youtube_auto_upload: v })} label="Planlanan YouTube videolarını otomatik yükle" desc="Takvimdeki zaman geldiğinde yükler (uygulama açık olmalı)." />
          </div>
        </Section>
      </div>
    </>
  );
}
