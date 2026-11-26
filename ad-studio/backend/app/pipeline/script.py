"""LLM ad script generation (direct-response short-form)."""
from __future__ import annotations

import random

from pydantic import BaseModel, Field

from ..config import config
from ..models import Campaign, Product
from ..providers import ollama

ANGLES = [
    ("problem", "Problem-çözüm: izleyicinin yaşadığı somut bir sorunla aç, ürünü çözüm olarak göster."),
    ("curiosity", "Merak boşluğu: ilk cümlede şaşırtıcı bir iddia/soru, cevabı videonun sonunda."),
    ("pov", "POV/hikâye: 'POV: ...' formatında birinci tekil şahıs mini hikâye."),
    ("social_proof", "Sosyal kanıt: 'herkes bunu soruyor', yorumlar, popülerlik vurgusu."),
    ("comparison", "Karşılaştırma: eski/pahalı alternatif vs bu ürün, fiyat-performans."),
    ("listicle", "Liste: 'Bunu almadan önce bilmen gereken 3 şey' tarzı hızlı maddeler."),
    ("pattern_interrupt", "Kalıp kırıcı: beklenmedik, cesur, dikkat çekici bir açılış cümlesi."),
    ("deal", "Fırsat/aciliyet: indirim, sınırlı stok, fiyat vurgusu (abartısız, dürüst)."),
]

LANG = {"tr": "Türkçe", "en": "English", "de": "Deutsch", "es": "Español", "fr": "Français", "ar": "العربية"}


class Scene(BaseModel):
    voiceover: str = Field(description="Bu sahnede okunacak metin, 1-2 kısa cümle")
    visual_prompt: str = Field(description="English image-generation prompt, concrete subject, setting, lighting, camera")
    on_screen_text: str = Field(default="", description="Ekranda büyük yazı, en fazla 5 kelime, opsiyonel")


class AdScript(BaseModel):
    hook: str = Field(description="İlk 2 saniyede okunacak dikkat çekici açılış cümlesi, max 12 kelime")
    scenes: list[Scene]
    cta: str = Field(description="Kısa harekete geçirici kapanış cümlesi")
    caption: str = Field(description="Platform açıklaması, 1-3 cümle, emoji serbest")
    hashtags: list[str]
    title: str = Field(description="YouTube Shorts başlığı, max 70 karakter")


SYSTEM = """Sen TikTok, Instagram Reels ve YouTube Shorts için yüksek dönüşümlü kısa video reklamları yazan, \
dünya çapında bir direct-response metin yazarısın.
Kurallar:
- Toplam seslendirme 20-35 saniye (yaklaşık 55-90 kelime). Kısa, konuşma dili, ritmik cümleler.
- Hook ilk 2 saniyede izleyiciyi durdurmalı. Klişe ("Merhaba arkadaşlar") yasak.
- Ürünün yalnızca verilen gerçek özelliklerini kullan. Uydurma iddia, sahte indirim, sağlık/finans vaadi YOK.
- visual_prompt'lar İngilizce; ürünü ve kullanım anını somut tarif et; metin/yazı/logo içermesin; dikey kadraj.
- Sahneler görsel olarak çeşitli olsun (yakın plan, kullanım anı, yaşam tarzı, detay).
- CTA platforma uygun olsun (ör. "Link profilde", "Sepete ekle").
- hashtags: 4-7 adet, '#' olmadan, niş + geniş karışık.
- Yalnızca istenen JSON şemasında yanıt ver."""


def pick_angles(n: int, seed: int) -> list[tuple[str, str]]:
    rng = random.Random(seed)
    pool = ANGLES[:]
    rng.shuffle(pool)
    return [pool[i % len(pool)] for i in range(n)]


def build_prompt(product: Product, campaign: Campaign, angle: str, avoid_hooks: list[str]) -> str:
    feats = "\n".join(f"- {f.strip()}" for f in product.features.splitlines() if f.strip()) or "-"
    price = f"{product.price:g} {product.currency}" if product.price else "belirtilmedi"
    lines = [
        f"Dil: {LANG.get(campaign.language, campaign.language)} (visual_prompt hariç)",
        f"Platform: {campaign.target_platform}",
        f"Ürün: {product.name}",
        f"Açıklama: {product.description or '-'}",
        f"Özellikler:\n{feats}",
        f"Fiyat: {price}",
        f"Satış yeri: {product.platform or '-'}",
        f"Hedef kitle: {campaign.audience or 'genel'}",
        f"Ton: {campaign.tone}",
        f"Görsel stil: {campaign.visual_style or 'modern, temiz, premium'}",
        f"Sahne sayısı: tam olarak {campaign.scenes}",
        f"Yaklaşım: {angle}",
    ]
    if campaign.angle_notes:
        lines.append(f"Ek notlar: {campaign.angle_notes}")
    if avoid_hooks:
        lines.append("Bu hook'lardan farklı ol: " + " | ".join(avoid_hooks))
    return "\n".join(lines)


async def generate(product: Product, campaign: Campaign, angle_desc: str, avoid_hooks: list[str]) -> AdScript:
    s = await ollama.chat_json(SYSTEM, build_prompt(product, campaign, angle_desc, avoid_hooks), AdScript)
    return normalize(s, campaign.scenes)


def normalize(s: AdScript, n_scenes: int) -> AdScript:
    if not s.scenes:
        raise ValueError("Senaryo sahne içermiyor")
    s.scenes = s.scenes[: max(n_scenes, 1)]
    s.hashtags = [h.lstrip("#").replace(" ", "") for h in s.hashtags if h.strip()][:8]
    return s


def stub(product: Product, campaign: Campaign, angle: str, idx: int) -> AdScript:
    hooks = ["Bunu neden daha önce almadım?", "Herkes bunu soruyor, işte cevabı", "POV: sonunda doğru ürünü buldun",
             "Bu fiyata bu kalite mi?", "Almadan önce bunu izle"]
    feats = [f for f in product.features.splitlines() if f.strip()] or ["Şık tasarım", "Uzun ömür", "Kolay kullanım"]
    scenes = [Scene(voiceover=f"{feats[i % len(feats)]}. Gerçekten fark yaratıyor.",
                    visual_prompt=f"{product.name}, lifestyle shot {i}", on_screen_text=feats[i % len(feats)][:28])
              for i in range(campaign.scenes)]
    return AdScript(hook=hooks[idx % len(hooks)], scenes=scenes, cta=config.get().cta_default.replace("👆", "").strip(),
                    caption=f"{product.name} hakkında bilmen gereken her şey ✨", hashtags=["keşfet", "fırsat", "alışveriş"],
                    title=f"{product.name} | {angle}")


def full_caption(s: AdScript) -> str:
    cfg = config.get()
    tags = " ".join("#" + h for h in s.hashtags)
    parts = [s.caption, tags, cfg.ad_disclosure.strip()]
    if cfg.ai_label:
        parts.append("Bu video yapay zekâ ile üretilmiştir.")
    return "\n\n".join(p for p in parts if p)
