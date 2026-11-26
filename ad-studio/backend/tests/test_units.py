import httpx
import pytest

from app.pipeline import subtitles
from app.pipeline.script import AdScript, Scene, normalize
from app.providers import comfy, ollama
from app.providers.tts import Word, estimate_words, words_from_chars


def test_words_from_chars():
    text = "Merhaba dünya  test"
    starts = [i * 0.1 for i in range(len(text))]
    ends = [s + 0.08 for s in starts]
    w = words_from_chars(list(text), starts, ends)
    assert [x.text for x in w] == ["Merhaba", "dünya", "test"]
    assert w[1].start == pytest.approx(0.8) and w[2].end == pytest.approx(1.88)


def test_estimate_words_monotonic():
    w = estimate_words("bir iki üç dört", 4.0)
    assert len(w) == 4 and all(a.start < b.start for a, b in zip(w, w[1:])) and w[-1].end <= 4.0


def test_fill_keeps_types():
    g = {"1": {"inputs": {"seed": "{{seed}}", "text": "a {{prompt}} b"}}}
    out = comfy.fill(g, {"seed": 42, "prompt": "cat"})
    assert out["1"]["inputs"] == {"seed": 42, "text": "a cat b"}
    assert g["1"]["inputs"]["seed"] == "{{seed}}"


def test_ass_turkish_upper_and_highlight(tmp_path):
    words = [Word("işte", 0, 0.3), Word("ılık", 0.3, 0.6), Word("su.", 0.6, 0.9), Word("Yeni", 1.0, 1.3)]
    p = subtitles.build(words, [(0, 1, "başlık")], tmp_path / "s.ass", "Arial", "#FFD400", "tr")
    txt = p.read_text(encoding="utf-8")
    assert "İŞTE" in txt and "ILIK" in txt and "BAŞLIK" in txt
    assert "&H00D4FF&" in txt
    assert txt.count("Dialogue: 1") == 4


def test_normalize_trims():
    s = AdScript(hook="h", scenes=[Scene(voiceover="v", visual_prompt="p")] * 6, cta="c", caption="x",
                 hashtags=["#a b", "c"], title="t")
    n = normalize(s, 4)
    assert len(n.scenes) == 4 and n.hashtags == ["ab", "c"]


@pytest.mark.asyncio
async def test_ollama_retries_invalid_json(monkeypatch):
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        content = "not json" if calls["n"] == 1 else '<think>x</think>{"hook":"h","scenes":[{"voiceover":"v","visual_prompt":"p"}],"cta":"c","caption":"x","hashtags":["a"],"title":"t"}'
        return httpx.Response(200, json={"message": {"content": content}})

    real = httpx.AsyncClient
    monkeypatch.setattr(ollama.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    s = await ollama.chat_json("sys", "u", AdScript)
    assert s.hook == "h" and calls["n"] == 2
