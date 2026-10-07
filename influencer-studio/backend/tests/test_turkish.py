import pytest

from studio.turkish import chunk, normalize, number_to_words, ordinal_to_words


@pytest.mark.parametrize("n,words", [
    (0, "sıfır"), (7, "yedi"), (11, "on bir"), (40, "kırk"), (99, "doksan dokuz"), (100, "yüz"), (101, "yüz bir"),
    (342, "üç yüz kırk iki"), (1000, "bin"), (1001, "bin bir"), (2026, "iki bin yirmi altı"), (10_000, "on bin"),
    (100_000, "yüz bin"), (1_000_000, "bir milyon"), (1_250_000, "bir milyon iki yüz elli bin"),
    (2_000_000_000, "iki milyar"), (-5, "eksi beş"),
])
def test_cardinals(n, words):
    assert number_to_words(n) == words


@pytest.mark.parametrize("n,words", [
    (1, "birinci"), (2, "ikinci"), (3, "üçüncü"), (4, "dördüncü"), (6, "altıncı"), (9, "dokuzuncu"),
    (10, "onuncu"), (24, "yirmi dördüncü"), (40, "kırkıncı"), (60, "altmışıncı"), (100, "yüzüncü"),
    (1000, "bininci"), (1_000_000, "bir milyonuncu"),
])
def test_ordinals_follow_vowel_harmony(n, words):
    assert ordinal_to_words(n) == words


@pytest.mark.parametrize("text,spoken", [
    ("%25 indirim", "yüzde yirmi beş indirim"),
    ("% 3,5 faiz", "yüzde üç virgül beş faiz"),
    ("3. gün", "üçüncü gün"),
    ("21. yüzyılda", "yirmi birinci yüzyılda"),
    ("2026'da başladık.", "iki bin yirmi altıda başladık."),
    ("Saat 14:30'da", "Saat on dört otuzda"),
    ("09:05 treni", "dokuz sıfır beş treni"),
    ("Saat 10:00.", "Saat on."),
    ("₺49,90", "kırk dokuz lira doksan kuruş"),
    ("1.250 TL", "bin iki yüz elli lira"),
    ("49,9 TL", "kırk dokuz lira doksan kuruş"),
    ("$20 ve €5", "yirmi dolar ve beş avro"),
    ("0,05 oranında", "sıfır virgül sıfır beş oranında"),
    ("5 km koştum", "beş kilometre koştum"),
    ("Dr. Ayşe & Prof. Can vb.", "doktor Ayşe ve profesör Can ve benzeri"),
    ("iPhone 17 Pro", "iPhone on yedi Pro"),
    ("Merhaba, nasılsın?", "Merhaba, nasılsın?"),
])
def test_normalize(text, spoken):
    assert normalize(text) == spoken


def test_chunk_keeps_sentences_and_limits_length():
    text = "Merhaba! Bugün size yeni rutinimi göstereceğim. " * 10 + "\n\nİkinci paragraf burada."
    chunks = chunk(text, max_chars=120)
    assert all(len(c) <= 120 for c in chunks)
    assert " ".join(chunks).split() == text.split()
    assert chunks[-1] == "İkinci paragraf burada."  # paragraphs never merge


def test_chunk_splits_run_on_sentences():
    long = ", ".join(["çok uzun bir cümle parçası"] * 20)
    chunks = chunk(long, max_chars=100)
    assert all(len(c) <= 100 for c in chunks) and " ".join(chunks).split() == long.split()
    no_punct = "kelime " * 80
    assert all(len(c) <= 100 for c in chunk(no_punct, max_chars=100))
