"""Topic backlog: niche-driven ideas, duplicate filter, sensitivity gate (AI persona + sensitive topic = not monetizable)."""
from __future__ import annotations

import difflib
import random
import re

from pydantic import BaseModel, Field

from ...models import Channel, Character, Episode, EpisodeStat, Topic, session
from ...providers import ollama
from ..script import LANG

# Hard block list (case-insensitive substrings). The LLM classifier catches the rest.
SENSITIVE_PATTERNS = [
    r"\bseçim\b", r"\bsiyas", r"\bparti\b", r"\bcumhurbaşkan", r"\bbakan\b", r"\bsava[sş]\b.*\b20[12]\d\b",
    r"\bdeprem\b.*\b20[12]\d\b", r"\bkanser\b", r"\btedavi\b", r"\bila[cç]\b", r"\bdiyet\b", r"\başı\b",
    r"\bborsa\b", r"\bkripto\b", r"\byatırım tavsiye", r"\bintihar\b", r"\bterör", r"\bsoykırım",
    r"\belection\b", r"\bvaccine\b", r"\bcancer\b", r"\bcrypto\b", r"\bsuicide\b", r"\bterror",
]


class TopicIdea(BaseModel):
    title: str = Field(description="YouTube başlığı, merak uyandıran, aranabilir, max 70 karakter, clickbait yalanı yok")
    angle: str = Field(description="Belgeselin bakış açısı, 1 cümle")
    hook: str = Field(description="Videonun ilk cümlesi")
    score: float = Field(ge=0, le=10, description="İzlenme potansiyeli tahmini")


class TopicBatch(BaseModel):
    topics: list[TopicIdea]


class SensitiveItem(BaseModel):
    index: int
    sensitive: bool
    reason: str = ""


class SensitiveBatch(BaseModel):
    items: list[SensitiveItem]


SYSTEM = """Sen başarılı belgesel YouTube kanalları için konu bulan bir editörsün.
Konular: zamansız (evergreen), merak uyandıran, araştırılabilir, görsel olarak anlatılabilir.
Kaçın: güncel haber, siyaset, sağlık/tıbbi tavsiye, finansal tavsiye, yaşayan kişiler hakkında iddia, trajedi istismarı.
Başlıklar yanıltıcı olmasın. Birbirinden farklı olsun. Yalnızca JSON döndür."""

CLASSIFIER = """Her konu için 'sensitive' alanını belirle. Hassas sayılır: siyaset/seçim, güncel haber ve afetler,
sağlık-tıp-diyet, finans-yatırım, din tartışması, yaşayan gerçek kişiler hakkında iddialar, şiddet/trajedi odaklı içerik,
çocuklar. Tarih, bilim, doğa, mühendislik, kültür, gizemler (gerçek kişileri suçlamadan) hassas değildir."""


def keyword_flag(text: str) -> str | None:
    low = text.lower()
    for p in SENSITIVE_PATTERNS:
        if re.search(p, low):
            return f"Anahtar kelime: {p.strip(chr(92) + 'b')}"
    return None


def similar(a: str, b: str) -> bool:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio() > 0.78


def winners(channel_id: int, k: int = 5) -> list[str]:
    with session() as s:
        eps = {e.id: e for e in s.query(Episode).filter(Episode.channel_id == channel_id, Episode.yt_id != "").all()}
        views: dict[int, int] = {}
        for st in s.query(EpisodeStat).filter(EpisodeStat.episode_id.in_(list(eps))).all() if eps else []:
            views[st.episode_id] = views.get(st.episode_id, 0) + st.views
    ranked = sorted((e for e in eps.values() if views.get(e.id)), key=lambda e: -views[e.id])
    return [e.title for e in ranked[:k]]


def existing_titles(channel_id: int) -> list[str]:
    with session() as s:
        return [t.title for t in s.query(Topic).filter(Topic.channel_id == channel_id).all()]


async def generate(channel: Channel, character: Character | None, n: int, dry_run: bool) -> list[Topic]:
    have = existing_titles(channel.id)
    if dry_run:
        ideas = stub(channel, n, len(have))
        flags = [(bool(keyword_flag(i.title)), keyword_flag(i.title) or "") for i in ideas]
    else:
        prompt = [f"Kanal nişi: {channel.niche}", f"Dil: {LANG.get(channel.language, channel.language)}",
                  f"{n} yeni konu üret."]
        if character:
            prompt.append(f"Sunucu karakter: {character.name} — {character.persona[:300]}")
        if have:
            prompt.append("Daha önce işlenen/planlanan (tekrarlama): " + " | ".join(have[-40:]))
        if w := winners(channel.id):
            prompt.append("En çok izlenen bölümlerimiz (benzer tarzda ama farklı konular): " + " | ".join(w))
        ideas = (await ollama.chat_json(SYSTEM, "\n".join(prompt), TopicBatch)).topics
        listing = "\n".join(f"{i}. {t.title} — {t.angle}" for i, t in enumerate(ideas))
        cls = await ollama.chat_json(CLASSIFIER, listing, SensitiveBatch, temperature=0.0)
        by = {c.index: c for c in cls.items}
        flags = []
        for i, t in enumerate(ideas):
            kw = keyword_flag(f"{t.title} {t.angle}")
            c = by.get(i)
            flags.append((bool(kw) or bool(c and c.sensitive), kw or (c.reason if c and c.sensitive else "")))
    out: list[Topic] = []
    with session() as s:
        for idea, (sens, reason) in zip(ideas, flags):
            if any(similar(idea.title, h) for h in have):
                continue
            have.append(idea.title)
            status = "rejected" if sens else ("approved" if idea.score >= 6 else "idea")
            t = Topic(channel_id=channel.id, title=idea.title.strip()[:120], angle=idea.angle, hook=idea.hook,
                      score=round(idea.score, 1), sensitive=sens, sensitive_reason=reason, status=status)
            s.add(t)
            s.commit()
            s.refresh(t)
            out.append(t)
    return out


STUB_TITLES = [
    "Kayıp Şehir {n}: Kumların Altındaki Sır", "Okyanusun En Derin Noktasında Ne Var? ({n})",
    "Antik Mühendislerin Unutulan Buluşu #{n}", "Bir Haritanın Değiştirdiği Dünya ({n})",
    "Gece Göğündeki Garip Işık #{n}", "Bin Yıllık Ağacın Hikâyesi ({n})", "Kaybolan Gemi {n}",
    "Diyet Tedavisi Mucizesi {n}",  # deliberately sensitive → rejected
]


def stub(channel: Channel, n: int, offset: int) -> list[TopicIdea]:
    rng = random.Random(channel.id * 100 + offset)
    out = []
    for i in range(n):
        tpl = STUB_TITLES[(offset + i) % len(STUB_TITLES)]
        title = tpl.format(n=offset + i + 1)
        out.append(TopicIdea(title=title, angle=f"{channel.niche or 'Tarih'} perspektifinden bakış",
                             hook="Bu hikâyeyi duyduğunuzda bakış açınız değişecek.", score=round(rng.uniform(6, 9.5), 1)))
    return out


def next_topic(channel_id: int) -> Topic | None:
    with session() as s:
        return s.query(Topic).filter(Topic.channel_id == channel_id, Topic.status == "approved") \
            .order_by(Topic.score.desc(), Topic.id).first()
