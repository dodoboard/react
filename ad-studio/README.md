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

## v4 — Belgesel Kanalı (tam otomatik YouTube)
Kendi YouTube kanal(lar)ında, sabit bir **sunucu karakterin** anlattığı belgesel bölümleri ve Shorts — konu seçiminden yayına kadar otomatik.

```
Niş ─▶ Konu havuzu (LLM + hassas konu filtresi) ─▶ Taslak ─▶ Bölüm bölüm senaryo (karakterin üslubu)
     ─▶ Kalite jürisi (eşik altı → yeniden yaz → yine düşükse YAYINLANMAZ, incelemeye düşer)
     ─▶ Ses (karakter sesi) ─▶ Görseller: sunucu (Wan 2.2 S2V) + belgesel b-roll (Flux 16:9, bölüm açılışlarında i2v)
     ─▶ 16:9 montaj (çapraz geçiş, film dokusu, lower-third, müzik) + SRT + bölümler + kapak
     ─▶ Shorts kesiti (en çarpıcı 35-58 sn, 9:16) ─▶ YouTube: publishAt ile zamanlanmış yükleme, kapak, altyazı, oynatma listesi
```

| Özellik | Ayrıntı |
|---|---|
| **Karakter** | Kişilik/biyografi, konuşma tarzı, imza açılış-kapanış, tutarlı görünüm prompt'u, avatar (Flux ile üret veya yükle), ses + "dinle" önizlemesi. LLM ile tek tıkla kişilik üretimi. |
| **Kanal** | Niş, dil, format (uzun / Shorts / ikisi), süre, haftalık yayın slotları, kaç gün önceden üretileceği, günlük üretim limiti, gece üretim saati, gizlilik, oynatma listesi, kalite eşiği, durdurma anahtarı. Her kanalın kendi YouTube OAuth bağlantısı. |
| **Güvenlik kapıları** | Hassas konu engeli (siyaset, sağlık, finans, güncel trajediler, yaşayan kişiler — "AI persona + hassas konu" para kazanamaz), tekrar konu engeli, kalite jürisi (hook / akış / özgünlük / doğruluk riski), günlük limit, API kota takibi. |
| **YouTube** | `containsSyntheticMedia: true`, `publishAt` ile YouTube'un kendi zamanlaması, kapak (`thumbnails.set`), SRT altyazı (`captions.insert`), açıklamada otomatik bölümler (00:00…), Shorts açıklamasında tam bölüm linki; Shorts her zaman uzun bölümden **sonra** yayınlanır. |
| **Analitik** | Bölüm başına günlük izlenme / izlenme oranı (YouTube Analytics) → en çok izlenen başlıklar yeni konu üretimine örnek olarak verilir. |
| **GPU paylaşımı** | Reklam ve belgesel hatları tek GPU kilidiyle sırayla çalışır (VRAM çakışması yok). |

**Kurulum ekleri**
- ComfyUI: Wan 2.2 S2V modelleri (v2 tablosu) — sunucu sahneleri için. Yoksa sunucu sahneleri avatar üzerinde yavaş zoom ile üretilir.
- `pip install -r backend/requirements-youtube.txt`, Google Cloud'da **YouTube Data API v3** + **YouTube Analytics API**, OAuth *Desktop* istemcisi → Ayarlar'dan yükle → Kanal detay → "YouTube'u bağla" (her kanal ayrı Google/marka hesabı olabilir).
- Varsayılan API kotası günde 10.000 birim; bir bölüm yüklemesi ≈ 2.100 birim (≈4 bölüm/gün). Gerekirse Google'dan kota artışı isteyin ve Ayarlar → `youtube_daily_quota` değerini güncelleyin.
- Uzun üretim süresi: 10 dk'lık bölüm ≈ 80-100 görsel + birkaç S2V klip → RTX 5080'de yaklaşık 30-60 dk. Gece üretim saatini buna göre seçin.

> **YouTube para kazanma notu:** YouTube, şablon gibi görünen tekrarlı içerikleri ve hassas konulardaki AI personaları para kazanmaya kapatabiliyor. Sistem bunlara karşı filtreler uygular ama niş seçimi, karakterin özgünlüğü ve ilk bölümleri izleyip ayarları iyileştirmek size kalır.

## v3 — Firmalar (çok markalı ajans modu)
| Özellik | Ne yapar | Nerede |
|---|---|---|
| **Firma kartı** | Her firma için logo, ana/vurgu rengi, kurumsal font, marka sesi, CTA, hashtag, reklam ibaresi; videolarda otomatik uygulanır (altyazı vurgusu, ilerleme çubuğu, fiyat rozeti, logo filigranı, kapanış kartı). | Firmalar → Yeni firma |
| **Mesaj kuralları** | Ton, hedef kitle, marka kuralları, *mutlaka söylenecekler* ve **yasaklı kelimeler** prompt'a girer; çıktıda yasaklı kelime varsa otomatik yeniden yazılır, kalırsa uyarı verilir. | Firma → Mesaj kuralları |
| **Tek videoda çok ürün** | 2-6 ürün: Top liste, Kombin, Karşılaştırma, İndirim vitrini, Hediye rehberi. Her ürün kendi sahnesinde gerçek görseliyle, kendi fiyat rozetiyle; kapanışta numaralı ürün ızgarası. | Stüdyo → Çok ürün |
| **Ürün bazlı takip** | Çok ürünlü videoda her ürün linki `{subid}p{ürünID}` alır → CSV içe aktarımı geliri doğru ürüne ve firmaya bağlar. | Gelir & ROI |
| **Firma seçici** | Üst bardaki seçici tüm sayfaları (dashboard, ürünler, kampanyalar, kütüphane, takvim, gelir) o firmaya filtreler. | Üst bar |
| **Onay akışı** | Taslak → Onayda → Onaylandı / Revizyon. Seçili videolar için **onay paketi** (.zip: mp4 + açıklamalar) indirilir, durum otomatik "Onayda" olur. | Firma → Videolar |
| **Faturalama** | Aylık sabit + video başı ücret; "Ay tahakkukunu oluştur" (tekrar çalıştırmak güvenli, ödenmiş kalemlere dokunmaz), ek kalem, ödendi işaretleme. | Firma → Faturalama |
| **Aylık müşteri raporu** | Tek dosya HTML: KPI'lar, video tablosu (izlenme, izlenme oranı, tıklama, satış), hizmet bedeli özeti, firma logosu ve renkleriyle — e-postayla gönder. | Firma → Aylık rapor |
| **Kârlılık** | Dashboard'da firmalara göre kâr (hizmet bedeli + affiliate − üretim maliyeti). | Genel Bakış |
| **Otopilot** | Kural bir firmaya bağlanabilir ve çok ürünlü video üretebilir. | Otopilot |

## v2 — Dönüşüm odaklı özellikler
| Özellik | Ne yapar | Nerede |
|---|---|---|
| **Gerçek ürün sahneleri** | Ürün fotoğrafının arka planı kaldırılır (BiRefNet; yoksa beyaz fon için yerleşik kesim) ve AI arka plana gölge + yansıma ile **piksel-birebir** yerleştirilir. Alternatif: Flux Kontext ile doğal yerleştirme. | Ürünler → "Arka planı kaldır", Ayarlar → Kalite |
| **Çekim türleri** | LLM her sahneye `product_hero / product_in_use / detail / lifestyle / presenter` atar; sahnelerin ≥%50'si ürün. | otomatik |
| **Viral montaj** | Hook'ta punch-in + beyaz flaş, kesimlerde whoosh (lokal sentez), üstte ilerleme çubuğu, hero sahnede fiyat rozeti, 3 altyazı stili, hook'ta 2 kelimelik altyazı. | Ayarlar → Kalite |
| **i2v modu** | Kapalı / sadece hook sahnesi / tümü — hook modu ilk saniyeyi hareketli yapar, maliyeti düşük tutar. Klip uzunluğu konuşma süresine eşit. | Stüdyo, Otopilot |
| **Hook turnuvası** | Slot başı 3 aday hook → LLM jürisi 0-10 puanlar → en iyisi senaryoya dönüşür. Skor kartlarda ★ olarak görünür. | Ayarlar → Kalite |
| **Öğrenen açı seçimi** | Hook yaklaşımları Thompson sampling ile seçilir: dönüşüm verisi (CSV), yoksa YouTube izlenme oranı. Kazanan hook'lar prompt'a stil referansı olarak eklenir. | otomatik |
| **Otopilot** | Her gün belirlenen saatte ürün havuzundan (gelire göre ağırlıklı, %20 keşif) kampanya üretir; bitenleri 12:00/19:00/21:00 slotlarına planlar. | Otopilot |
| **Konuşan avatar (UGC)** | Wan 2.2 S2V ile kameraya konuşan persona — "Avatar hook" (sadece ilk sahne) veya "Tam UGC". Persona: kendi fotoğrafın ya da Flux ile kurgusal kişi. | Stüdyo → Görsel & Ses |
| **YouTube Analytics** | Yüklenen Shorts'ların günlük izlenme / ortalama izlenme yüzdesi / beğeni 6 saatte bir çekilir → Dashboard "Hook tutma oranı", RPM. | Ayarlar → YouTube |

Aşama sırası: **senaryo → ses → görsel → montaj** (ses önce: klip ve dudak senkronu süreleri kesinleşir). Hatalı video "Tekrar" ile son başarılı aşamadan devam eder.

### v2 ek modeller
| Dosya | Klasör | Kullanım |
|---|---|---|
| `flux1-dev-kontext_fp8_scaled.safetensors` | `models/diffusion_models` | Ürün modu "Flux Kontext" |
| `clip_l.safetensors`, `t5xxl_fp8_e4m3fn_scaled.safetensors` | `models/text_encoders` | Kontext |
| `ae.safetensors` | `models/vae` | Kontext |
| `wan2.2_s2v_14B_fp8_scaled.safetensors` | `models/diffusion_models` | Avatar (S2V) |
| `wav2vec2_large_english_fp16.safetensors` | `models/audio_encoders` | Avatar |
| `wan_2.1_vae.safetensors` | `models/vae` | Avatar |

Kaliteli ürün kesimi için: `backend\.venv\Scripts\pip install -r backend\requirements-product.txt` (rembg + BiRefNet, ilk çalıştırmada model indirilir).

> **Avatar notu:** S2V 14B fp8'in 16 GB VRAM'e sığması doğrulanmadı; ComfyUI offload ile çalışır ama yavaştır (5 sn klip ≈ 5-10 dk). Sığmazsa ComfyUI'da GGUF Q5 sürümüyle kendi workflow'unu dışa aktarıp (`{{image}} {{audio}} {{length}}` yer tutucularıyla) Ayarlar'dan yükle ve "avatar workflow" olarak seç. Gerçek kişileri taklit eden görseller kullanma.

> **YouTube Analytics:** v1'den bağlıysan Ayarlar → YouTube → "Analitik için yeniden bağlan" (yeni okuma izinleri gerekir).

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
