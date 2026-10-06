# Influencer Studio · FLUX.2 (lokal)

Higgsfield AI Influencer Studio'nun lokal karşılığı. ComfyUI üzerinde **FLUX.2 [klein]** ile çalışır; görseller ve karakterler bilgisayarından çıkmaz.

| Higgsfield                        | Influencer Studio                                                                  |
| --------------------------------- | ---------------------------------------------------------------------------------- |
| Builder: 19 ayar, Average→Extreme | Builder: 18 seçim + yaş = 19 ayar, her biri Average / Notable / Extreme            |
| Add your face                     | Fotoğraf yükle → FLUX.2 referans görseli (rıza onayı zorunlu)                      |
| Soul ID                           | Kimlik paketi (8 açı) + en fazla 4 tutarlılık referansı, istersen karakter LoRA'sı |
| İçerik üretimi                    | Create: 15 sahne preset'i + serbest prompt, referanslarla aynı yüz                 |
| –                                 | LoRA veri seti dışa aktarma (ai-toolkit config'iyle)                               |
| Motion (Genjutsu)                 | Yok: FLUX.2 bir görsel modeli. Bkz. [Yol haritası](#yol-haritası)                  |

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

3. `start.bat` → <http://127.0.0.1:7860>. İlk çalıştırmada Python ortamını ve arayüzü kendisi kurar.
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

## Mimari

```
React (Vite) ──/api──► FastAPI ──HTTP + WebSocket──► ComfyUI ──► FLUX.2 [klein]
                         ├─ SQLite + PNG (data/)
                         └─ tek GPU iş kuyruğu
```

| Dosya                         | Görev                                                                             |
| ----------------------------- | --------------------------------------------------------------------------------- |
| `backend/studio/catalog.py`   | Özellik kataloğu, preset'ler, açılar. Arayüz buradan çizilir (tek kaynak)         |
| `backend/studio/prompting.py` | Seçimleri doğal dilde FLUX.2 prompt'una derler                                    |
| `backend/studio/flux2.py`     | Model profilleri + ComfyUI API grafı (ComfyUI'ın resmi FLUX.2 şablonlarıyla aynı) |
| `backend/studio/comfy.py`     | ComfyUI istemcisi: upload, `/prompt`, `/ws` ilerleme, `/history`                  |
| `backend/studio/service.py`   | Builder, karakter, kimlik paketi, içerik, veri seti                               |
| `frontend/src/pages/`         | Builder, Influencers, karakter sayfası, Create                                    |

## Geliştirme

```bash
cd backend && pip install -e ".[dev]" && pytest
python -m tests.fake_comfy --port 8188     # GPU'suz sahte ComfyUI (arayüz geliştirme için)
STUDIO_DATA_DIR=/tmp/studio python -m studio
cd frontend && npm install && npm run dev  # http://localhost:5173, /api → 7860
```

## Notlar

- Gerçek bir kişinin yüzünü yalnızca kendin ya da izin aldığın biri için kullan. Yayınladığın içeriği yapay zekâ ile üretildiğini belirterek etiketle (AB'de EU AI Act Madde 50).
- Model URL'leri ComfyUI'ın FLUX.2 şablonlarından alındı. Biri 404 verirse ComfyUI'da ilgili şablonu açınca eksik modeller indirme linkiyle listelenir.

## Yol haritası

- Motion sekmesi: Wan-Animate-2 / SCAIL-2 ile hareket aktarımı (ComfyUI'da hazır şablonları var)
- Lipsync + Türkçe ses: Chatterbox Multilingual + InfiniteTalk
