# Influencer Studio · FLUX.2 (lokal)

Higgsfield AI Influencer Studio'nun lokal karşılığı. ComfyUI üzerinde görseller için **FLUX.2 [klein]**, dans ve hareket videoları için **Wan** modelleriyle çalışır; görseller, videolar ve karakterler bilgisayarından çıkmaz.

| Higgsfield                        | Influencer Studio                                                                  |
| --------------------------------- | ---------------------------------------------------------------------------------- |
| Builder: 19 ayar, Average→Extreme | Builder: 18 seçim + yaş = 19 ayar, her biri Average / Notable / Extreme            |
| Add your face                     | Fotoğraf yükle → FLUX.2 referans görseli (rıza onayı zorunlu)                      |
| Soul ID                           | Kimlik paketi (8 açı) + en fazla 4 tutarlılık referansı, istersen karakter LoRA'sı |
| İçerik üretimi                    | Create: 15 sahne preset'i + serbest prompt, referanslarla aynı yüz                 |
| –                                 | LoRA veri seti dışa aktarma (ai-toolkit config'iyle)                               |
| Motion (Genjutsu)                 | Motion: dans aktarımı, müzikle dans, hareket şablonları. Bkz. [Motion](#motion)    |
| Konuşan video / lipsync           | Talk: Türkçe TTS, ses klonlama, InfiniteTalk dudak senkronu. Bkz. [Talk](#talk)    |

## Gereksinimler

- NVIDIA GPU, 16 GB VRAM (RTX 5080 Laptop hedeflendi), 32 GB RAM
- Güncel [ComfyUI](https://github.com/Comfy-Org/ComfyUI) (FLUX.2 [klein] destekli; graflar ComfyUI 0.39.0 ile doğrulandı)
- Python 3.11+, Node.js 22+

## Kurulum (Windows)

1. ComfyUI Portable'ı kur ve başlat (`run_nvidia_gpu.bat`). 32 GB RAM için `--fast-disk` bayrağı önerilir.
2. Modelleri indir (varsayılan profil, yaklaşık 12 GB):

   ```bat
   python scripts\download_models.py --comfy C:\ComfyUI_windows_portable\ComfyUI
   ```

   Video modelleri ayrıca, kullanacağın modlara göre indirilir (bkz. [Motion](#motion)).

3. `start.bat` → <http://127.0.0.1:7860>. Python ortamını ve arayüzü kendisi kurar; `git pull` sonrası değişen bağımlılıkları da yeniden kurar.
4. Uçtan uca kontrol (512 px deneme render'ı):

   ```bat
   .venv\Scripts\python -m studio doctor
   ```

Linux / WSL için aynı adımlar `start.sh` ile.

## Model profilleri

| `STUDIO_PROFILE`        | Model                            | Adım / CFG | Lisans                           |
| ----------------------- | -------------------------------- | ---------- | -------------------------------- |
| `klein-4b` (varsayılan) | FLUX.2 [klein] 4B distilled, fp8 | 4 / 1.0    | Apache-2.0                       |
| `klein-4b-base`         | FLUX.2 [klein] 4B base, fp8      | 20 / 5.0   | Apache-2.0                       |
| `klein-9b`              | FLUX.2 [klein] 9B distilled, fp8 | 4 / 1.0    | FLUX Non-Commercial (`HF_TOKEN`) |

FLUX.2 [dev] (32B) 16 GB VRAM + 32 GB RAM'e sığmadığı için profil olarak eklenmedi.

Diğer ayarlar: `STUDIO_COMFY_URL` (varsayılan `http://127.0.0.1:8188`), `STUDIO_DATA_DIR` (varsayılan `./data`), `STUDIO_HOST`, `STUDIO_PORT`.

## İş akışı

1. **Builder**: özellikleri seç, istersen yüzünü ekle, 1–4 varyasyon üret, beğendiğini **Save as influencer** ile kaydet.
2. **Karakter sayfası**: **Identity pack** ile farklı açılar üret, en iyilerini ★ ile referans yap (en fazla 4).
3. **Create**: preset seç veya sahneyi yaz. Her üretimde referanslar FLUX.2'ye `ReferenceLatent` olarak verilir.
4. **Daha güçlü tutarlılık**: **Export LoRA dataset** → zip'teki `train_flux2_klein_4b.yaml` ile [ai-toolkit](https://github.com/ostris/ai-toolkit)'te eğit → `.safetensors` dosyasını `ComfyUI/models/loras/` içine koy → karakter sayfasında seç.

## Motion

Karakterin bir görselinden (tercihen Create'te üretilmiş tam boy bir kare) video üretir. Üç mod var:

| Mod             | Ne yapar                                                                        | Model                           | Süre                   |
| --------------- | ------------------------------------------------------------------------------- | ------------------------------- | ---------------------- |
| **Dance video** | Yüklediğin dans klibindeki hareketi ve kamerayı karakterine aktarır, sesi korur | Wan-Animate-2 Distilled (int8)  | 1–20 sn, 16 fps        |
| **Music dance** | Şarkının ritminden koreografi üretir: K-Pop, Street, Latin, Tap, Klasik         | Wan-Dancer-14B (global + local) | 5–30 sn, 30 fps, sesli |
| **Motion**      | 12 hazır hareket (dans, saç savurma, podyum, dönüş...) veya kendi tarifin       | Wan 2.2 I2V A14B + 4 adım LoRA  | 5 sn, 16 fps           |

İsteğe bağlı **Smooth motion**, FILM kare ara doldurmasıyla fps'i ikiye katlar. Wan-Animate-2, Wan-Dancer ve Wan 2.2 Apache-2.0 lisanslı.

Modelleri indir (ortak dosyalar bir kez iner; yaklaşık dance 25 GB, music 38 GB, motion 37 GB, smooth 0,1 GB):

```bat
python scripts\download_models.py --comfy C:\ComfyUI_windows_portable\ComfyUI --profile none --video dance,smooth
python scripts\download_models.py --comfy C:\ComfyUI_windows_portable\ComfyUI --profile none --video all
```

Dans klibi backend'de ön işlenir: seçilen aralık kesilir, 16 fps'e indirilir, hedef boyuta kırpılır, telefon videolarındaki döndürme düzeltilir ve müzik ayrı bir WAV olarak çıkarılır. ComfyUI'a yalnızca bu küçük dosya gider; ham 1080p/60 fps klip 32 GB RAM'i doldururdu. 5 sn'den uzun danslar, 81 karelik pencerelerin `continue_motion` ile zincirlenmesiyle üretilir.

**16 GB VRAM / 32 GB RAM için:**

- ComfyUI'ı `--fast-disk` ile başlat; 14B modeller VRAM'e sığmaz, ComfyUI parçaları diskten akıtır.
- 480p'de üret, gerekirse ayrıca büyüt. 720p yaklaşık iki kat süre ve bellek ister.
- Wan-Animate-2'nin poz önbelleği üretimi yaklaşık yarıya indirir ve sistem RAM'inde durur: `STUDIO_POSE_CACHE=int4` (varsayılan, ~3 GB), `int8` (~6 GB) veya `off`.
- Referans hız: ComfyUI'ın Wan 2.2 şablonundaki ölçüm, RTX 4090D'de 640×640 ve 4 adımla klip başına ~70–100 sn. Laptop GPU'sunda daha uzun sürer.
- Dans klibi: tek kişi, tam boy, sabit kamera en iyi sonucu verir. Yalnızca hakkına sahip olduğun klipleri kullan.

## Talk

Karakterini konuşturur: yazdığın metni karakterin sesiyle okur ve dudak senkronlu video üretir.

| Adım      | Ne olur                                                                                                       | Model                                              |
| --------- | ------------------------------------------------------------------------------------------------------------- | -------------------------------------------------- |
| **Ses**   | Karaktere 10–15 sn'lik ses örneği ata (yükle ya da mikrofonla kaydet). Atanmamışsa yerleşik ses kullanılır    | Chatterbox Multilingual (MIT, Türkçe dahil 22 dil) |
| **Metin** | Türkçe metin okunmadan önce düzenlenir: sayılar, %, para, saat, sıra sayıları, kısaltmalar. Cümlelere bölünür | `backend/studio/turkish.py`                        |
| **Video** | Ses + başlangıç karesi → konuşan video: 480p, 25 fps, en fazla 30 sn                                          | InfiniteTalk (Wan 2.1 I2V 480p + lightx2v LoRA)    |

Örnekler: `%25 indirim` → "yüzde yirmi beş indirim", `₺49,90` → "kırk dokuz lira doksan kuruş", `14:30'da` → "on dört otuzda", `21. yüzyıl` → "yirmi birinci yüzyıl".

- **Write a script**: metni yaz, **Preview voice** ile dinle. Her deneme **Speech takes** altında kalır; beğendiğini **Lip-sync this** ile aynen videoya çevir.
- **Use a recording**: kendi seslendirmeni yükle ya da mikrofonla kaydet. TTS atlanır.
- **Expressiveness** duygu yoğunluğunu, **Pacing** konuşma temposunu ayarlar (düşük = daha yavaş ve sakin).

Kurulum. TTS ayrı bir sunucuda, kendi Python ortamında çalışır: Chatterbox'ın sabitlediği torch/transformers sürümleri ComfyUI'ınkiyle çakışır, RTX 50 serisi için de torch'un CUDA 12.8 derlemesi gerekir. Kurulum betiği ikisini de halleder.

```bat
tts\install.bat
tts\start.bat
python scripts\download_models.py --comfy C:\ComfyUI_windows_portable\ComfyUI --profile none --video talk
```

- TTS <http://127.0.0.1:7870> adresinde dinler; model ağırlıkları (~3 GB) ilk istekte Hugging Face'ten iner. Farklı bir adres için `STUDIO_TTS_URL`.
- TTS GPU'dayken stüdyo seslendirmeden önce ComfyUI'ın modellerini VRAM'den boşaltır: ikisi aynı anda 16 GB'a sığmaz. VRAM'i tamamen ComfyUI'a bırakmak için TTS'i `set TTS_DEVICE=cpu` ile başlat (daha yavaş).
- Mikrofon kaydı tarayıcıda yalnızca `http://127.0.0.1` / `localhost` ya da HTTPS üzerinden çalışır.
- 30 sn'den uzun konuşmaları parçalara böl. Her 81 karelik pencere (~3 sn) bir önceki pencerenin son 9 karesiyle devam eder.
- En iyi sonuç: yüzü ve ağzı net görünen, karşıdan çekilmiş bir kare.

Yalnızca kendi sesini ya da açık izin aldığın birinin sesini klonla. Chatterbox her çıktıya duyulamayan bir yapay zekâ filigranı (Perth) ekler; yayınladığın konuşan videoları da yapay zekâ ile üretildiğini belirterek etiketle.

## Mimari

```
React (Vite) ──/api──► FastAPI ──HTTP + WebSocket──► ComfyUI ──► FLUX.2 [klein] · Wan
                         ├─ SQLite + PNG/MP4/WAV (data/)
                         ├─ PyAV: video/ses ön işleme
                         ├─ tek GPU iş kuyruğu
                         └─ HTTP ──► TTS sunucusu (tts/, Chatterbox, ayrı venv)
```

| Dosya                         | Görev                                                                             |
| ----------------------------- | --------------------------------------------------------------------------------- |
| `backend/studio/catalog.py`   | Özellik kataloğu, preset'ler, açılar. Arayüz buradan çizilir (tek kaynak)         |
| `backend/studio/prompting.py` | Seçimleri doğal dilde FLUX.2 prompt'una derler                                    |
| `backend/studio/flux2.py`     | Model profilleri + ComfyUI API grafı (ComfyUI'ın resmi FLUX.2 şablonlarıyla aynı) |
| `backend/studio/comfy.py`     | ComfyUI istemcisi: upload, `/prompt`, `/ws` ilerleme, `/history`                  |
| `backend/studio/service.py`   | Builder, karakter, kimlik paketi, içerik, veri seti                               |
| `backend/studio/video.py`     | Video modelleri + Wan-Animate-2, Wan-Dancer, Wan 2.2 grafları                     |
| `backend/studio/media.py`     | PyAV ile klip kesme, fps/boyut dönüştürme, ses çıkarma                            |
| `backend/studio/motion.py`    | Motion işleri: yükleme doğrulama, dans, müzikle dans, hareket şablonları          |
| `backend/studio/turkish.py`   | Türkçe metin normalleştirme (sayı, para, saat, kısaltma) ve cümle bölme           |
| `backend/studio/voice.py`     | Talk işleri: TTS istemcisi, ses klonlama, InfiniteTalk lipsync                    |
| `tts/server.py`               | Chatterbox Multilingual TTS sunucusu (ayrı venv, port 7870)                       |
| `frontend/src/pages/`         | Builder, Influencers, karakter sayfası, Create, Motion, Talk                      |

## Geliştirme

```bash
cd backend && pip install -e ".[dev]" && pytest
python -m tests.fake_comfy --port 8188     # GPU'suz sahte ComfyUI (arayüz geliştirme için)
python -m tests.fake_tts --port 7870       # modelsiz sahte TTS
STUDIO_DATA_DIR=/tmp/studio python -m studio
cd frontend && npm install && npm run dev  # http://localhost:5173, /api → 7860
```

## Notlar

- Gerçek bir kişinin yüzünü yalnızca kendin ya da izin aldığın biri için kullan. Yayınladığın içeriği yapay zekâ ile üretildiğini belirterek etiketle (AB'de EU AI Act Madde 50).
- Model URL'leri ComfyUI'ın FLUX.2 şablonlarından alındı. Biri 404 verirse ComfyUI'da ilgili şablonu açınca eksik modeller indirme linkiyle listelenir.

## Yol haritası

- Videodaki bir kişiyi karakterle değiştirme: SCAIL-2 (ComfyUI'da hazır şablonu var)
- Var olan bir videoyu dublajlama (video-to-video lipsync): ComfyUI çekirdeğindeki InfiniteTalk şimdilik yalnızca görselden video üretiyor
- İki kişilik diyalog: InfiniteTalk `two_speakers` modu
