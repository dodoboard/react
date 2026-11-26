"""LLM ad script generation (direct-response short-form)."""
from __future__ import annotations

import random
from typing import Literal

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


SHOTS = ("product_hero", "product_in_use", "lifestyle", "detail", "presenter")
PRODUCT_SHOTS = {"product_hero", "product_in_use", "detail"}


class Scene(BaseModel):
    voiceover: str = Field(description="Bu sahnede okunacak metin, 1-2 kısa cümle")
    visual_prompt: str = Field(description="English image-generation prompt, concrete subject, setting, lighting, camera")
    on_screen_text: str = Field(default="", description="Ekranda büyük yazı, en fazla 5 kelime, opsiyonel")
    shot: Literal["product_hero", "product_in_use", "lifestyle", "detail", "presenter"] = Field(
        default="lifestyle", description="product_hero: ürün tek başına kahraman çekim; product_in_use: ürün kullanılırken; "
                                         "detail: ürün yakın plan detay; lifestyle: ürünsüz atmosfer; presenter: kameraya konuşan kişi")


class AdScript(BaseModel):
    hook: str = Field(description="İlk 2 saniyede okunacak dikkat çekici açılış cümlesi, max 12 kelime")
    scenes: list[Scene]
    cta: str = Field(description="Kısa harekete geçirici kapanış cümlesi")
    caption: str = Field(description="Platform açıklaması, 1-3 cümle, emoji serbest")
    hashtags: list[str]
    title: str = Field(description="YouTube Shorts başlığı, max 70 karakter")


class HookIdea(BaseModel):
    angle: str
    hook: str


class HookBatch(BaseModel):
    hooks: list[HookIdea]


class HookScore(BaseModel):
    index: int
    score: float = Field(ge=0, le=10)
    reason: str = ""


class HookScores(BaseModel):
    scores: list[HookScore]


SYSTEM = """Sen TikTok, Instagram Reels ve YouTube Shorts için yüksek dönüşümlü kısa video reklamları yazan, \
dünya çapında bir direct-response metin yazarısın.
Kurallar:
- Toplam seslendirme 20-35 saniye (yaklaşık 55-90 kelime). Kısa, konuşma dili, ritmik cümleler.
- Hook ilk 2 saniyede izleyiciyi durdurmalı. Klişe ("Merhaba arkadaşlar") yasak.
- Ürünün yalnızca verilen gerçek özelliklerini kullan. Uydurma iddia, sahte indirim, sağlık/finans vaadi YOK.
- Her sahneye bir shot türü ver. Sahnelerin en az yarısı ürünü göstermeli (product_hero / product_in_use / detail); \
ilk iki sahneden biri product_hero olmalı.
- visual_prompt'lar İngilizce. Ürün sahnelerinde ürünün KONUMUNU ve ORTAMINI tarif et (yüzey, ışık, eller, mekân); \
ürünün kendisini yeniden tasarlama. Metin/yazı/logo içermesin; dikey kadraj.
- Sahneler görsel olarak çeşitli olsun (yakın plan, kullanım anı, yaşam tarzı, detay).
- CTA platforma uygun olsun (ör. "Link profilde", "Sepete ekle").
- hashtags: 4-7 adet, '#' olmadan, niş + geniş karışık.
- Yalnızca istenen JSON şemasında yanıt ver."""

HOOK_SYSTEM = """Kısa video reklamları için scroll durduran açılış cümleleri (hook) yazıyorsun.
Her hook max 12 kelime, konuşma dili, somut, ürünün gerçek özelliklerine dayalı; klişe ve abartı yok.
Her hook verilen yaklaşımlardan birine ait olmalı ve birbirinden belirgin şekilde farklı olmalı."""

JUDGE_SYSTEM = """Sen kısa video reklam performansını tahmin eden acımasız bir editörsün.
Her hook'u 0-10 puanla. Ölçütler: (1) ilk 1 saniyede kaydırmayı durdurur mu, (2) somut ve spesifik mi,
(3) merak/duygusal gerilim yaratıyor mu, (4) tek okumada anlaşılır mı, (5) kısa mı (<=10 kelime ideal).
Klişe, genel, abartılı veya yanıltıcı hook'ları sert cezalandır. Yalnızca JSON döndür."""


def pick_angles(n: int, seed: int) -> list[tuple[str, str]]:
    rng = random.Random(seed)
    pool = ANGLES[:]
    rng.shuffle(pool)
    return [pool[i % len(pool)] for i in range(n)]


def angle_desc(key: str) -> str:
    return next((d for k, d in ANGLES if k == key), ANGLES[0][1])


def product_block(product: Product, campaign: Campaign) -> str:
    feats = "\n".join(f"- {f.strip()}" for f in product.features.splitlines() if f.strip()) or "-"
    price = f"{product.price:g} {product.currency}" if product.price else "belirtilmedi"
    return "\n".join([
        f"Dil: {LANG.get(campaign.language, campaign.language)} (visual_prompt hariç)",
        f"Platform: {campaign.target_platform}",
        f"Ürün: {product.name}",
        f"Açıklama: {product.description or '-'}",
        f"Özellikler:\n{feats}",
        f"Fiyat: {price}",
        f"Satış yeri: {product.platform or '-'}",
        f"Hedef kitle: {campaign.audience or 'genel'}",
        f"Ton: {campaign.tone}",
    ])


def build_prompt(product: Product, campaign: Campaign, angle: str, avoid_hooks: list[str],
                 fixed_hook: str = "", winners: list[str] | None = None) -> str:
    lines = [
        product_block(product, campaign),
        f"Görsel stil: {campaign.visual_style or 'modern, temiz, premium'}",
        f"Sahne sayısı: tam olarak {campaign.scenes}",
        f"Yaklaşım: {angle}",
    ]
    if campaign.format == "avatar_full":
        lines.append("Format: UGC — tüm sahneler 'presenter' (kameraya konuşan kişi); ürünü elinde tutup gösterir.")
    elif campaign.format == "avatar_hook":
        lines.append("Format: İlk sahne 'presenter' (kameraya konuşan kişi), diğerleri ürün/b-roll.")
    if fixed_hook:
        lines.append(f"Hook TAM OLARAK şu olmalı (değiştirme): {fixed_hook}")
    if campaign.angle_notes:
        lines.append(f"Ek notlar: {campaign.angle_notes}")
    if winners:
        lines.append("Geçmişte en çok kazandıran hook'lar (stil referansı, kopyalama):\n" + "\n".join(f"- {w}" for w in winners))
    if avoid_hooks:
        lines.append("Bu hook'lardan farklı ol: " + " | ".join(avoid_hooks))
    return "\n".join(lines)


async def generate(product: Product, campaign: Campaign, angle: str, avoid_hooks: list[str],
                   fixed_hook: str = "", winners: list[str] | None = None) -> AdScript:
    s = await ollama.chat_json(SYSTEM, build_prompt(product, campaign, angle_desc(angle), avoid_hooks, fixed_hook, winners), AdScript)
    if fixed_hook:
        s.hook = fixed_hook
    return normalize(s, campaign)


async def tournament(product: Product, campaign: Campaign, angles: list[str], winners: list[str],
                     per_slot: int = 3) -> list[tuple[str, str, float]]:
    """Generate per_slot candidate hooks per requested angle, LLM-judge them, return best one per slot."""
    uniq = list(dict.fromkeys(angles))
    req = "\n".join(f"- {a}: {angle_desc(a)}" for a in uniq)
    prompt = (f"{product_block(product, campaign)}\n\nHer yaklaşım için {per_slot} farklı hook yaz "
              f"(angle alanına yaklaşım anahtarını yaz):\n{req}")
    if winners:
        prompt += "\nGeçmişte kazanan hook'lar (stil referansı):\n" + "\n".join(f"- {w}" for w in winners)
    batch = await ollama.chat_json(HOOK_SYSTEM, prompt, HookBatch)
    cands = [h for h in batch.hooks if h.hook.strip() and h.angle in uniq] or batch.hooks
    if not cands:
        raise ValueError("Hook üretilemedi")
    listing = "\n".join(f"{i}. {h.hook}" for i, h in enumerate(cands))
    judged = await ollama.chat_json(JUDGE_SYSTEM, f"Ürün: {product.name}\nHook'lar:\n{listing}", HookScores, temperature=0.1)
    score = {x.index: x.score for x in judged.scores if 0 <= x.index < len(cands)}
    return select(angles, [(h.angle, h.hook, score.get(i, 0.0)) for i, h in enumerate(cands)])


def select(angles: list[str], scored: list[tuple[str, str, float]]) -> list[tuple[str, str, float]]:
    """Best unused hook per requested angle slot; falls back to best remaining overall."""
    pool = sorted(scored, key=lambda x: x[2], reverse=True)
    out = []
    for a in angles:
        pick = next((x for x in pool if x[0] == a), None) or (pool[0] if pool else None)
        if pick is None:
            break
        pool.remove(pick)
        out.append((a, pick[1], pick[2]))
    return out


def normalize(s: AdScript, campaign: Campaign) -> AdScript:
    if not s.scenes:
        raise ValueError("Senaryo sahne içermiyor")
    s.scenes = s.scenes[: max(campaign.scenes, 1)]
    if campaign.format == "avatar_full":
        for sc in s.scenes:
            sc.shot = "presenter"
    elif campaign.format == "avatar_hook":
        s.scenes[0].shot = "presenter"
    else:
        for sc in s.scenes:
            if sc.shot == "presenter":
                sc.shot = "product_in_use"
        if not any(sc.shot in PRODUCT_SHOTS for sc in s.scenes[:2]):
            s.scenes[min(1, len(s.scenes) - 1)].shot = "product_hero"
    s.hashtags = [h.lstrip("#").replace(" ", "") for h in s.hashtags if h.strip()][:8]
    return s


STUB_HOOKS = ["Bunu neden daha önce almadım?", "Herkes bunu soruyor, işte cevabı", "POV: sonunda doğru ürünü buldun",
              "Bu fiyata bu kalite mi?", "Almadan önce bunu izle", "Kimse bundan bahsetmiyor", "3 saniyede fikrini değiştireceğim"]


def stub_tournament(angles: list[str], seed: int) -> list[tuple[str, str, float]]:
    rng = random.Random(seed)
    scored = [(a, h, round(rng.uniform(5, 9.5), 1)) for a in dict.fromkeys(angles) for h in rng.sample(STUB_HOOKS, 3)]
    return select(angles, scored)


def stub(product: Product, campaign: Campaign, angle: str, idx: int, fixed_hook: str = "") -> AdScript:
    feats = [f for f in product.features.splitlines() if f.strip()] or ["Şık tasarım", "Uzun ömür", "Kolay kullanım"]
    shots = ["product_hero", "lifestyle", "product_in_use", "detail"]
    scenes = [Scene(voiceover=f"{feats[i % len(feats)]}. Gerçekten fark yaratıyor.",
                    visual_prompt=f"{product.name}, scene {i}", on_screen_text=feats[i % len(feats)][:28],
                    shot=shots[i % len(shots)])
              for i in range(campaign.scenes)]
    s = AdScript(hook=fixed_hook or STUB_HOOKS[idx % len(STUB_HOOKS)], scenes=scenes,
                 cta=config.get().cta_default.replace("👆", "").strip(),
                 caption=f"{product.name} hakkında bilmen gereken her şey ✨", hashtags=["keşfet", "fırsat", "alışveriş"],
                 title=f"{product.name} | {angle}")
    return normalize(s, campaign)


def full_caption(s: AdScript) -> str:
    cfg = config.get()
    tags = " ".join("#" + h for h in s.hashtags)
    parts = [s.caption, tags, cfg.ad_disclosure.strip()]
    if cfg.ai_label:
        parts.append("Bu video yapay zekâ ile üretilmiştir.")
    return "\n\n".join(p for p in parts if p)
