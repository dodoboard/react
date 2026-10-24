import pytest

from studio.subtitles import clip_cues, cues_from_words, retime, window, words_from_segments


def test_words_follow_syllables_of_the_spoken_form():
    words = words_from_segments([{"start": 1.0, "end": 3.0, "text": "Bugün %30 indirim!"}])
    assert [w["text"] for w in words] == ["Bugün", "%30", "indirim!"]
    # bu-gün (2), yüz-de o-tuz (4), in-di-rim (3): 9 syllables over 2 s
    durations = [w["end"] - w["start"] for w in words]
    assert durations == pytest.approx([2 / 9 * 2, 4 / 9 * 2, 3 / 9 * 2], abs=0.002)
    assert words[0]["start"] == 1.0 and words[-1]["end"] == pytest.approx(3.0)


def test_cues_are_short_and_break_at_punctuation_and_pauses():
    words = words_from_segments([
        {"start": 0, "end": 4, "text": "Merhaba arkadaşlar! Bugün size en sevdiğim kahve tarifini göstereceğim."},
        {"start": 5.5, "end": 6.5, "text": "Hazır mısınız?"},
    ])
    cues = cues_from_words(words)
    texts = [c["text"] for c in cues]
    assert texts[0] == "Merhaba arkadaşlar!"  # sentence end closes the cue
    assert all(len(c["words"]) <= 4 and len(c["text"]) <= 24 or len(c["words"]) == 1 for c in cues)
    assert texts[-1] == "Hazır mısınız?" and cues[-1]["start"] == 5.5  # after a 1.5 s pause
    assert " ".join(texts).split() == " ".join(w["text"] for w in words).split()
    assert all(c["words"][0]["start"] == c["start"] and c["words"][-1]["end"] == c["end"] for c in cues)


def test_retime_and_sources():
    cue = {"start": 2.0, "end": 3.0, "text": "Merhba dunya", "words": []}
    fixed = retime(cue, "Merhaba dünya")
    assert fixed["text"] == "Merhaba dünya" and fixed["words"][-1]["end"] == pytest.approx(3.0)
    segments = [{"start": 0, "end": 1, "text": "Selam!"}]
    assert clip_cues({"meta": {"segments": segments}})[0]["text"] == "Selam!"
    words = [{"text": "Hi", "start": 0, "end": 0.4}, {"text": "there.", "start": 0.4, "end": 0.9}]
    assert clip_cues({"meta": {"segments": segments, "words": words}})[0]["text"] == "Hi there."
    assert clip_cues({"meta": {"cues": [fixed], "words": words}}) == [fixed]  # edits win
    assert clip_cues({"meta": {}}) == []


def test_window_trims_and_shifts():
    cues = cues_from_words([{"text": t, "start": i, "end": i + 1} for i, t in enumerate(["a", "b", "c", "d."])])
    (cue,) = window(cues, start=1.5, end=3.5, offset=10)
    assert cue["text"] == "b c d." and cue["start"] == 10 and cue["end"] == 12
    assert [w["start"] for w in cue["words"]] == [10, 10.5, 11.5]
    assert window(cues, start=5, end=6, offset=0) == []
