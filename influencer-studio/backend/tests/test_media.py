import av
import pytest

from studio.media import MediaError, extract_audio, prepare_driver, probe
from tests.media_fixtures import make_recording, make_video, make_wav, square_time, wav_onset


def test_probe(tmp_path):
    info = probe(make_video(tmp_path / "v.mp4", seconds=2, fps=30))
    assert info.has_video and info.has_audio and (info.width, info.height) == (640, 360)
    assert info.fps == 30 and info.duration == pytest.approx(2, abs=0.1)
    song = probe(make_wav(tmp_path / "a.wav", seconds=1.5, onset=0))
    assert not song.has_video and song.has_audio and song.duration == pytest.approx(1.5, abs=0.01)
    rec = tmp_path / "mic.webm"
    make_recording(rec, seconds=4)
    with av.open(str(rec)) as c:
        assert c.duration is None  # no header duration: probe must measure it
    assert probe(rec).duration == pytest.approx(4, abs=0.05)
    (tmp_path / "junk.mp4").write_bytes(b"not a video")
    with pytest.raises(MediaError):
        probe(tmp_path / "junk.mp4")


def test_driver_is_trimmed_resampled_and_cropped(tmp_path):
    src = make_video(tmp_path / "v.mp4", seconds=3, fps=30, size=(640, 360))
    frames = prepare_driver(src, tmp_path / "d.mp4", start=1.0, seconds=1.5, width=320, height=320, fps=16)
    assert frames == 24
    with av.open(str(tmp_path / "d.mp4")) as c:
        decoded = list(c.decode(video=0))
        assert len(c.streams.audio) == 0 and c.streams.video[0].average_rate == 16
    assert len(decoded) == 24 and (decoded[0].width, decoded[0].height) == (320, 320)
    for i in (0, 8, 23):  # each output frame shows the source frame on screen at start + i / 16
        assert square_time(decoded[i], (640, 360), (320, 320)) == pytest.approx(1.0 + i / 16, abs=1 / 30 + 0.01)


def test_audio_cut_is_sample_accurate(tmp_path):
    song = make_wav(tmp_path / "s.wav", seconds=4, onset=2.0)
    for start in (0.0, 1.25, 2.0):
        written = extract_audio(song, tmp_path / "o.wav", start=start, seconds=2.5)
        assert written == pytest.approx(min(2.5, 4 - start), abs=0.001)
        assert wav_onset(tmp_path / "o.wav") == pytest.approx(2.0 - start, abs=0.002)


def test_audio_from_video_and_errors(tmp_path):
    clip = make_video(tmp_path / "v.mp4", seconds=2, audio=True)
    assert extract_audio(clip, tmp_path / "o.wav", start=0.5, seconds=1) == pytest.approx(1, abs=0.01)
    silent = make_video(tmp_path / "silent.mp4", seconds=1, audio=False)
    with pytest.raises(MediaError):
        extract_audio(silent, tmp_path / "o.wav", start=0, seconds=1)
