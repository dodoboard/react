# AdForge Studio — Lokal AI Reklam Video Otomasyonu

Ürün linkini yapıştır → **Ollama** senaryo/hook yazar → **ComfyUI** sahne görselleri (Flux/SDXL) ve isteğe bağlı hareketli klipler (Wan 2.2) üretir → **ElevenLabs** veya **lokal Chatterbox** seslendirir → **FFmpeg** kelime kelime vurgulu altyazılı, müzikli, 1080×1920 dikey reklamı monte eder → takvimle yayınla, affiliate gelirini video bazında takip et.

Hedef donanım: RTX 5080 (16 GB VRAM) · Core Ultra 9 275HX · 32 GB RAM · Windows 11.

```
Ürün ─▶ Ollama (JSON şema) ─▶ [VRAM boşalt] ─▶ ComfyUI (t2i / i2v) ─▶ [VRAM boşalt] ─▶ TTS + kelime zamanları ─▶ FFmpeg (NVENC)
                                                                                                         │
            Gelir CSV (subid) ◀── Affiliate link?sub={subid} ◀── Yayın paketi / YouTube API ◀────────────┘
```

## Özellikler
- **Kampanya Stüdyosu:** 4 adımlı sihirbaz; ürün başına N adet A/B varyant, her biri farklı hook yaklaşımıyla (problem-çözüm, merak, POV, sosyal kanıt, karşılaştırma, liste, kalıp kırıcı, fırsat).
- **İnceleme modu:** senaryoları render öncesi düzenle (hook, sahneler, görsel prompt, CTA, açıklama).
- **Canlı kuyruk:** SSE ile anlık ilerleme; tek GPU worker, aşama bazlı toplu işleme (LLM ve diffusion aynı anda VRAM'e girmez).
- **Montaj:** Ken Burns hareketleri, karaoke tarzı kelime vurgulu ASS altyazı (Türkçe İ/ı doğru), sahne başlıkları, ürün görselli fiyat + CTA kapanış kartı, müzik ducking, −14 LUFS loudness, NVENC.
- **Gelir takibi:** her videoya benzersiz `subid`; affiliate linkine `{subid}` koyarsan otomatik yerleşir. CSV içe aktarımı videoya otomatik eşler → kampanya/hook türü bazında ROI.
- **Yayın:** takvim (sürükle-bırak, en iyi saatlere otomatik dağıtım), yayın paketi (.zip: mp4 + caption + thumbnail), YouTube Shorts API ile direkt/zamanlanmış yükleme.
- **Uyum:** açıklamaya otomatik `#reklam #işbirliği` ve "yapay zekâ ile üretildi" etiketi; YouTube yüklemelerinde `containsSyntheticMedia: true`.

## Kurulum (Windows)

### 1. Ön koşullar
| Araç | Not |
|---|---|
| Python 3.11+ | `winget install Python.Python.3.12` |
| Node.js 20+ | `winget install OpenJS.NodeJS.LTS` |
| FFmpeg (NVENC'li) | `winget install Gyan.FFmpeg` — PATH'te olmalı |
| Ollama | https://ollama.com → `ollama pull qwen3:14b` (alternatif: `gemma3:12b`) |
| ComfyUI | Portable sürüm (RTX 50 serisi için CUDA 12.8+ PyTorch içeren güncel sürüm) |

### 2. ComfyUI modelleri
| Dosya | Klasör | Kullanım |
|---|---|---|
| `flux1-dev-fp8.safetensors` (Comfy-Org all-in-one) | `models/checkpoints` | `flux_t2i` (varsayılan, en kaliteli) |
| Herhangi bir SDXL checkpoint (ör. Juggernaut XL) | `models/checkpoints` | `sdxl_t2i` (daha hızlı) — dosya adını workflow'da güncelle |
| `wan2.2_ti2v_5B_fp16.safetensors` | `models/diffusion_models` | `wan22_i2v` hareketli sahneler |
| `umt5_xxl_fp8_e4m3fn_scaled.safetensors` | `models/text_encoders` | Wan 2.2 |
| `wan2.2_vae.safetensors` | `models/vae` | Wan 2.2 |

Kendi workflow'unu kullanmak için: ComfyUI'da **Workflow → Export (API)**, metin alanlarına `{{prompt}}`, `{{negative}}`, seed'e `{{seed}}`, boyutlara `{{width}}`/`{{height}}`, LoadImage'a `{{image}}`, kayıt node'una `{{filename_prefix}}` yaz ve Ayarlar → *Workflow yükle*.

### 3. Çalıştır
```powershell
cd ad-studio
copy .env.example .env
powershell -ExecutionPolicy Bypass -File scripts\start.ps1
```
Tarayıcıda http://127.0.0.1:8000 açılır. Ayarlar sayfasında ElevenLabs API anahtarını gir ve **Bağlantıları test et**.

Geliştirme (hot reload): `scripts\start.ps1 -Dev` → http://localhost:5173

### Tamamen lokal ses (opsiyonel)
```powershell
backend\.venv\Scripts\pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128
backend\.venv\Scripts\pip install -r backend\requirements-local-tts.txt
```
Ayarlar → Seslendirme → **Lokal (Chatterbox)**. 5-15 sn'lik temiz bir referans kayıt yükleyerek ses klonlayabilirsin (yalnızca hakkına sahip olduğun ses). Altyazı zamanlaması faster-whisper ile çıkarılır.

### YouTube (opsiyonel)
`pip install -r backend/requirements-youtube.txt` → Google Cloud'da YouTube Data API v3 + OAuth *Desktop* istemcisi → JSON'u Ayarlar'dan yükle → Bağlan.

### Demo modu
Donanım/anahtar olmadan arayüzü denemek için `.env` içinde `ADF_DRY_RUN=1` yapıp başlat, sonra:
```powershell
backend\.venv\Scripts\python scripts\demo_seed.py
```

## Performans (RTX 5080, tahmini)
| Aşama | Süre |
|---|---|
| Senaryo (qwen3:14b, varyant başı) | 5-15 sn |
| Flux dev fp8, 768×1344, 20 adım | ~10-15 sn / sahne |
| Wan 2.2 5B i2v, 704×1280, 121 kare | ~1.5-3 dk / sahne |
| ElevenLabs | 2-5 sn |
| FFmpeg NVENC montaj | 5-15 sn |

Ken Burns modunda 4 sahneli bir video ≈ 1-1.5 dk; i2v ile ≈ 8-12 dk. 10 varyantlık bir kampanyayı gece kuyruğa al.

## Gelir stratejisi (pratik notlar)
1. **Niş seç:** komisyonu yüksek, görsel anlatıma uygun ürünler (ev gereçleri, teknoloji aksesuarı, kozmetik aletleri). Trendyol/Hepsiburada/Amazon affiliate programlarına kayıt ol.
2. **Hacim + test:** ürün başına 4-8 varyant üret, farklı hook türlerini aynı gün farklı saatlerde yayınla.
3. **Ölç:** affiliate panelinden günlük CSV indir (subid sütunu ile) → *Gelir & ROI* → içe aktar. Dashboard'daki "Kazanan yaklaşımlar" bir sonraki kampanyada hangi hook'ları seçeceğini söyler.
4. **Ölçekle:** kazanan hook'u "Yeni senaryo" ile çoğalt, kaybedenleri bırak.
5. **Kurallar:** reklam ibaresini kaldırma; ürünün sahip olmadığı özellikleri söyletme (LLM yalnızca girdiğin özellikleri kullanacak şekilde yönlendirilir); platformların AI içerik etiketleme kurallarına uy. ElevenLabs çıktılarını ticari kullanmak için ücretli plan gerekir. Fon müziği olarak yalnızca telifsiz/lisanslı parçalar kullan.

## Proje yapısı
```
backend/app/
  main.py               FastAPI, SPA servis, zamanlayıcı
  config.py             .env + data/config.json
  models.py             Product, Campaign, Video, RevenueEntry (SQLite)
  providers/            ollama.py, comfy.py (WS ilerleme), tts.py (ElevenLabs / Chatterbox / stub)
  pipeline/             script.py, visuals.py, voice→tts, subtitles.py, compose.py, graphics.py, runner.py
  api/                  products, campaigns(+videos), revenue(+analytics), system(+SSE), youtube
backend/workflows/      ComfyUI API-format şablonları
frontend/src/           React + Vite + Tailwind + TanStack Query + Framer Motion + Recharts
data/                   (git'e girmez) veritabanı, medya, müzik, sesler, fontlar
```

## Test
```bash
cd backend && .venv/bin/pip install -r requirements-dev.txt && .venv/bin/python -m pytest
```
Uçtan uca test DRY_RUN'da gerçek FFmpeg ile 1080×1920 video üretir, CSV gelir içe aktarımını ve ROI özetini doğrular.
