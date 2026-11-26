"""Documentary script: outline → chapter-by-chapter writing in the presenter character's voice → quality gate."""
from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field

from ...models import Channel, Character, Topic
from ...providers import ollama
from ..script import LANG, tag_rule

WPM = 140  # spoken words per minute (documentary pace)
SHORT_WORDS = 125  # ~50 s


class ChapterPlan(BaseModel):
    title: str
    beats: list[str] = Field(description="Bu bölümde anlatılacak 2-5 olay/bilgi")
    on_camera: bool = Field(default=False, description="Bölüm sunucu karakterin kameraya konuşmasıyla mı açılıyor")


class Outline(BaseModel):
    title: str = Field(description="YouTube başlığı, max 70 karakter")
    description: str = Field(description="2-4 cümlelik video açıklaması")
    tags: list[str]
    thumbnail_text: str = Field(description="Kapak görselinde 2-4 kelime, büyük harf olacak")
    thumbnail_prompt: str = Field(description="English prompt for a dramatic cinematic thumbnail background, no text")
    chapters: list[ChapterPlan]


class Segment(BaseModel):
    kind: Literal["presenter", "narration"]
    text: str = Field(description="Seslendirilecek metin")
    visual_prompt: str = Field(default="", description="narration için: English cinematic documentary shot prompt, no text")
    lower_third: str = Field(default="", description="Opsiyonel ekran altı yazısı: yer, tarih, isim (max 40 karakter)")


class Chapter(BaseModel):
    title: str
    segments: list[Segment]


class DocScript(BaseModel):
    title: str
    description: str
    tags: list[str]
    thumbnail_text: str
    thumbnail_prompt: str
    chapters: list[Chapter]

    def words(self) -> int:
        return sum(len(s.text.split()) for c in self.chapters for s in c.segments)


class Verdict(BaseModel):
    score: float = Field(ge=0, le=10)
    hook: float = Field(ge=0, le=10)
    flow: float = Field(ge=0, le=10)
    originality: float = Field(ge=0, le=10)
    accuracy_risk: float = Field(ge=0, le=10, description="10 = çok riskli, kesin dille kanıtsız iddialar")
    issues: list[str] = []
    rewrite_notes: str = ""


def persona_block(ch: Character | None) -> str:
    if not ch:
        return "Sunucu: sakin, bilgili bir anlatıcı."
    return "\n".join(x for x in [
        f"Sunucu karakter: {ch.name}",
        f"Kişilik/biyografi: {ch.persona}",
        f"Konuşma tarzı: {ch.speaking_style}" if ch.speaking_style else "",
        f"Sık kullandığı ifadeler (abartmadan): {ch.catchphrases}" if ch.catchphrases else "",
        f"İmza açılış: {ch.opening_line}" if ch.opening_line else "",
        f"İmza kapanış: {ch.closing_line}" if ch.closing_line else "",
    ] if x)


SYSTEM = """Sen ödüllü belgesel senaristisin. Anlatım sinematik, sakin ama merak uyandırıcı; somut detaylar, isimler,
yerler, zaman çizelgesi. Kurallar:
- Kesin bilinmeyen şeyleri temkinli dille anlat ("kayıtlara göre", "tarihçiler tartışıyor"). Uydurma alıntı, rakam, kaynak YOK.
- Gerçek yaşayan kişiler hakkında olumsuz iddia yok. Sağlık/finans tavsiyesi yok.
- Sunucu karakter kendi kişiliğiyle konuşur ama konunun önüne geçmez.
- visual_prompt'lar İngilizce, belgesel görüntü yönetmeninin çekim listesi gibi: çekim türü (establishing wide / close-up
  detail / aerial / archival photograph / reconstruction) + özne + dönem + mekân + ışık + hava. Boş sıfat ("epic,
  stunning, 8k") yok; metin/yazı/logo yok. Aynı bölümde çekim türlerini çeşitlendir.
- Yalnızca istenen JSON şemasında yanıt ver."""


def _plan_prompt(channel: Channel, ch: Character | None, topic: Topic, kind: str) -> str:
    lang = LANG.get(channel.language, channel.language)
    if kind == "short":
        shape = ("Shorts (dikey, ~50 sn): 3 bölüm — 1) 'Kanca' (on_camera=true, 1 vuruş), 2) 'Hikâye' (2-3 vuruş), "
                 "3) 'Final' (şaşırtıcı son bilgi + kanala davet, on_camera=true).")
    else:
        n = max(3, min(8, round(channel.target_minutes / 1.6)))
        shape = (f"Uzun belgesel (~{channel.target_minutes:g} dk): ilk bölüm 'Soğuk açılış' (on_camera=true, en çarpıcı an), "
                 f"ardından {n - 2} ana bölüm (bazıları on_camera=true olabilir), son bölüm 'Kapanış' (on_camera=true).")
    return "\n".join([persona_block(ch), f"Dil: {lang}", f"Kanal nişi: {channel.niche}", f"Konu: {topic.title}",
                      f"Açı: {topic.angle}", f"Önerilen ilk cümle: {topic.hook}", shape])


async def outline(channel: Channel, ch: Character | None, topic: Topic, kind: str) -> Outline:
    o = await ollama.chat_json(SYSTEM, _plan_prompt(channel, ch, topic, kind), Outline)
    if len(o.chapters) < (3 if kind == "long" else 2):
        raise ValueError("Taslak çok kısa")
    o.chapters[0].on_camera = True
    o.chapters[-1].on_camera = True
    return o


def chapter_words(channel: Channel, kind: str, n_chapters: int, idx: int) -> int:
    total = SHORT_WORDS if kind == "short" else int(channel.target_minutes * WPM)
    if kind == "long" and n_chapters > 2:  # cold open and outro are short
        edge = max(30, int(total * 0.07))  # >= ~12 s so YouTube chapters stay valid
        return edge if idx in (0, n_chapters - 1) else int((total - 2 * edge) / (n_chapters - 2))
    return max(25, total // n_chapters)


async def write_chapter(channel: Channel, ch: Character | None, o: Outline, idx: int, kind: str,
                        previous: list[Chapter], notes: str = "") -> Chapter:
    plan = o.chapters[idx]
    words = chapter_words(channel, kind, len(o.chapters), idx)
    rules = [
        f"Belgesel: {o.title}",
        "Bölüm planı: " + json.dumps([c.title for c in o.chapters], ensure_ascii=False),
        f"Şimdi yazılacak bölüm #{idx + 1}: {plan.title}",
        "Vuruşlar: " + " | ".join(plan.beats),
        f"Uzunluk: yaklaşık {words} kelime.",
        "Segment kuralları: narration segmentleri 12-20 kelime (her biri yeni bir görüntü, visual_prompt zorunlu); "
        "presenter segmentleri sunucu kameraya konuşur, en fazla 25 kelime, visual_prompt boş.",
        "Bölüm sunucunun kameraya konuşmasıyla başlasın." if plan.on_camera else "Bölüm narration ile başlasın.",
    ]
    if idx == 0 and ch and ch.opening_line:
        rules.append(f"İlk segmentte imza açılışı doğal biçimde kullan: {ch.opening_line}")
    if idx == len(o.chapters) - 1:
        rules.append("Videoyu bağla, izleyiciyi yorum yapmaya ve abone olmaya nazikçe davet et."
                     + (f" İmza kapanış: {ch.closing_line}" if ch and ch.closing_line else ""))
    if previous:
        last = previous[-1].segments[-1].text if previous[-1].segments else ""
        rules.append(f"Önceki bölümün son cümlesi (devamlılık): {last}")
    if notes:
        rules.append(f"Editör notları (mutlaka uygula): {notes}")
    if tr := tag_rule():
        rules.append(tr)
    prompt = persona_block(ch) + "\nDil: " + LANG.get(channel.language, channel.language) + "\n" + "\n".join(rules)
    c = await ollama.chat_json(SYSTEM, prompt, Chapter)
    c.title = plan.title
    c.segments = [s for s in c.segments if s.text.strip()]
    for s in c.segments:
        if s.kind == "narration" and not s.visual_prompt:
            s.visual_prompt = f"cinematic documentary shot about {o.title}"
    if not c.segments:
        raise ValueError(f"Bölüm {idx + 1} boş döndü")
    return c


async def write(channel: Channel, ch: Character | None, o: Outline, kind: str, notes: str = "",
                progress=None) -> DocScript:
    chapters: list[Chapter] = []
    for i in range(len(o.chapters)):
        chapters.append(await write_chapter(channel, ch, o, i, kind, chapters, notes))
        if progress:
            await progress((i + 1) / len(o.chapters))
    return DocScript(title=o.title, description=o.description, tags=o.tags, thumbnail_text=o.thumbnail_text,
                     thumbnail_prompt=o.thumbnail_prompt, chapters=chapters)


JUDGE = """Sen YouTube belgesel kanalının baş editörüsün. Senaryoyu 0-10 puanla (score = genel).
hook: ilk 30 saniye tutar mı; flow: akış ve geçişler; originality: şablon/tekrar hissi yok mu, özgün bakış var mı;
accuracy_risk: kanıtsız kesin iddia, uydurma rakam/alıntı riski (10 = çok riskli).
Platform kuralları: düşük emekli, tekrarlayan veya yanıltıcı içerik düşük puan alır. Sorunları issues'a yaz,
rewrite_notes'a somut düzeltme talimatları ver. Yalnızca JSON döndür."""


async def judge(sc: DocScript) -> Verdict:
    body = "\n\n".join(f"## {c.title}\n" + "\n".join(f"[{s.kind}] {s.text}" for s in c.segments) for c in sc.chapters)
    v = await ollama.chat_json(JUDGE, f"Başlık: {sc.title}\n\n{body[:14000]}", Verdict, temperature=0.1)
    if v.accuracy_risk >= 7:
        v.score = min(v.score, 5.5)
    return v


# ---------- stubs (DRY_RUN) ----------
def stub_outline(topic: Topic, kind: str, channel: Channel) -> Outline:
    n = 3 if kind == "short" else max(3, min(8, round(channel.target_minutes / 1.6)))
    names = ["Soğuk açılış", *[f"Bölüm {i}" for i in range(1, n - 1)], "Kapanış"] if kind == "long" else ["Kanca", "Hikâye", "Final"]
    return Outline(title=topic.title, description=f"{topic.title} — belgesel.", tags=["belgesel", "tarih", "gizem"],
                   thumbnail_text=" ".join(topic.title.split()[:3]), thumbnail_prompt="dramatic ancient ruins at dusk",
                   chapters=[ChapterPlan(title=t, beats=["giriş", "gelişme"], on_camera=i in (0, n - 1))
                             for i, t in enumerate(names[:n])])


def stub_script(o: Outline, channel: Channel, kind: str) -> DocScript:
    chapters = []
    for i, p in enumerate(o.chapters):
        w = chapter_words(channel, kind, len(o.chapters), i)
        segs = []
        if p.on_camera:
            segs.append(Segment(kind="presenter", text="Merhaba, ben sizin rehberinizim ve bugün çok ilginç bir hikâyeye bakıyoruz."))
        while sum(len(s.text.split()) for s in segs) < w:
            k = len(segs)
            segs.append(Segment(kind="narration", text=f"{p.title} içinde anlatılan olay {k}, yüzyıllar boyunca merak edildi ve hâlâ konuşuluyor.",
                                visual_prompt=f"documentary shot {i}-{k}", lower_third=("Mısır, MÖ 1250" if k == 1 else "")))
        chapters.append(Chapter(title=p.title, segments=segs))
    return DocScript(title=o.title, description=o.description, tags=o.tags, thumbnail_text=o.thumbnail_text,
                     thumbnail_prompt=o.thumbnail_prompt, chapters=chapters)


async def stub_judge(sc: DocScript) -> Verdict:
    return Verdict(score=8.2, hook=8, flow=8, originality=7.5, accuracy_risk=2, issues=[], rewrite_notes="")
