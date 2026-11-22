"""Turkish UGC script templates: fill in a few fields, get a ready-to-speak script.

Numbers and prices can be written naturally ("%30", "₺499,90"): the voice studio spells them out.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Template:
    id: str
    label: str
    fields: tuple[tuple[str, str], ...]  # (key, label)
    text: str
    prompt: str = ""  # expression / setting for the talking video


TEMPLATES = (
    Template("product", "Ürün tanıtımı", (("urun", "Ürün"), ("ozellik", "Öne çıkan özellik"), ("fiyat", "Fiyat")),
             "Merhaba arkadaşlar! Bugün size {urun} göstermek istiyorum. En sevdiğim yanı {ozellik}. "
             "Fiyatı da sadece {fiyat}. Link profilimde, mutlaka göz atın!",
             "holding the product up to the camera, excited"),
    Template("discount", "İndirim duyurusu", (("marka", "Marka"), ("indirim", "İndirim (%)"), ("tarih", "Son gün")),
             "Haber vermem lazım! {marka} ürünlerinde {indirim} indirim başladı. Kampanya {tarih} tarihine kadar "
             "geçerli, kaçırmayın!", "enthusiastic, pointing at the camera"),
    Template("vlog", "Günlük vlog girişi", (("yer", "Bugün neredeyim"), ("plan", "Günün planı")),
             "Günaydın! Bugün {yer} buradayım ve planım {plan}. Hadi birlikte başlayalım!",
             "smiling, relaxed, natural daylight"),
    Template("qa", "Soru-cevap", (("soru", "Takipçi sorusu"), ("cevap", "Cevabın")),
             "En çok sorduğunuz soru: {soru} Cevabım şu: {cevap} Başka sorularınızı yorumlara yazın!",
             "friendly, thoughtful, nodding"),
    Template("review", "Dürüst yorum", (("urun", "Ürün"), ("arti", "Beğendiğin"), ("eksi", "Beğenmediğin")),
             "{urun} için dürüst yorumum: {arti} gerçekten çok iyi. Ama {eksi} beni biraz üzdü. "
             "Siz denediniz mi?", "honest, calm, slight smile"),
)
TEMPLATE_BY_ID = {t.id: t for t in TEMPLATES}


def render(template_id: str, values: dict[str, str]) -> str:
    template = TEMPLATE_BY_ID.get(template_id)
    if template is None:
        raise KeyError(template_id)
    filled = {key: (values.get(key) or "").strip() for key, _ in template.fields}
    if missing := [label for key, label in template.fields if not filled[key]]:
        raise ValueError(f"fill in: {', '.join(missing)}")
    return re.sub(r"\s+", " ", template.text.format(**filled)).strip()


def public_templates() -> list[dict]:
    return [{"id": t.id, "label": t.label, "fields": [{"key": k, "label": label} for k, label in t.fields],
             "text": t.text, "prompt": t.prompt} for t in TEMPLATES]
