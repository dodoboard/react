"""Video/audio probing and pre-processing with PyAV (bundled FFmpeg, no system install needed).

Driving clips are converted *before* they reach ComfyUI: trimmed, resampled to the model's
frame rate and center-cropped to the target size. Sending a raw 1080p/60 fps phone clip
would make ComfyUI decode every frame at full size into RAM (tens of GB for 20 seconds).
"""

from __future__ import annotations

import wave
from dataclasses import asdict, dataclass
from pathlib import Path

import av
from PIL import Image, ImageOps

AUDIO_RATE = 44100


class MediaError(ValueError):
    pass


@dataclass(frozen=True)
class MediaInfo:
    duration: float
    has_video: bool
    has_audio: bool
    width: int = 0
    height: int = 0
    fps: float = 0.0

    def public(self) -> dict:
        return asdict(self)


def probe(path: Path) -> MediaInfo:
    try:
        with av.open(str(path)) as container:
            video = next((s for s in container.streams if s.type == "video"), None)
            audio = next((s for s in container.streams if s.type == "audio"), None)
            duration = container.duration / av.time_base if container.duration else 0.0
            if video is None:
                return MediaInfo(duration=duration, has_video=False, has_audio=audio is not None)
            width, height = video.codec_context.width, video.codec_context.height
            frame = next(container.decode(video), None)  # decoding one frame proves the stream is usable
            if frame is not None and abs(frame.rotation) == 90:  # phone clips: report display size
                width, height = height, width
            return MediaInfo(duration=duration, has_video=True, has_audio=audio is not None,
                             width=width, height=height, fps=float(video.average_rate or 0))
    except (av.FFmpegError, StopIteration) as e:
        raise MediaError(f"unreadable media file: {e}") from e


def _origin(container: av.container.InputContainer) -> float:
    """Timeline zero: players (and FFmpeg) count time from the container's first timestamp."""
    return container.start_time / av.time_base if container.start_time else 0.0


def _upright(frame: av.VideoFrame) -> Image.Image:
    img = frame.to_image()
    # `rotation` is the counterclockwise angle needed for display, as PIL's rotate() expects.
    return img.rotate(frame.rotation, expand=True) if frame.rotation else img


def prepare_driver(src: Path, dst: Path, *, start: float, seconds: float, width: int, height: int,
                   fps: int) -> int:
    """Write a silent H.264 clip of `seconds` at `fps`, cropped to width x height. Returns frames written."""
    wanted = max(1, round(seconds * fps))
    written = 0
    with av.open(str(src)) as inp, av.open(str(dst), "w", format="mp4") as out:
        stream = inp.streams.video[0]
        stream.thread_type = "AUTO"
        enc = out.add_stream("libx264", rate=fps)
        enc.width, enc.height, enc.pix_fmt = width, height, "yuv420p"
        enc.options = {"crf": "17", "preset": "veryfast"}

        def emit(frame: av.VideoFrame) -> None:
            nonlocal written
            img = ImageOps.fit(_upright(frame).convert("RGB"), (width, height), Image.Resampling.LANCZOS)
            for packet in enc.encode(av.VideoFrame.from_image(img)):
                out.mux(packet)
            written += 1

        origin = _origin(inp)
        if start > 0:  # lands on the keyframe before `start`
            inp.seek(int((origin + start) / stream.time_base), stream=stream)
        previous = None
        for frame in inp.decode(stream):
            if frame.time is None:
                continue
            # Output frame i shows whatever source frame is on screen at start + i / fps.
            while written < wanted and frame.time - origin > start + written / fps + 1e-6:
                emit(previous if previous is not None else frame)
            previous = frame
            if written >= wanted:
                break
        while previous is not None and written < wanted:  # callers clamp `seconds`; this only absorbs rounding
            emit(previous)
        for packet in enc.encode():
            out.mux(packet)
    if written == 0:
        raise MediaError("no video frames in the selected range")
    return written


def extract_audio(src: Path, dst: Path, *, start: float, seconds: float) -> float:
    """Write `seconds` of audio from `start` as 16-bit stereo WAV. Returns the duration written."""
    # Cut by decoded sample count rather than packet timestamps: MP3 timestamps ignore the
    # encoder delay the decoder trims, and seeking lands tens of ms off. Decoding a song from
    # the top takes well under a second.
    want = int(seconds * AUDIO_RATE)
    pcm = bytearray()
    skip: int | None = None  # samples to drop before `start`
    produced = 0

    def take(chunk: av.AudioFrame) -> None:  # packed s16 stereo: 4 bytes per sample frame
        nonlocal produced
        lo, hi = max(0, skip - produced), min(chunk.samples, skip + want - produced)
        if hi > lo:
            pcm.extend(bytes(chunk.planes[0])[lo * 4: hi * 4])
        produced += chunk.samples

    with av.open(str(src)) as inp:
        if not inp.streams.audio:
            raise MediaError("the file has no audio track")
        stream = inp.streams.audio[0]
        resampler = av.AudioResampler(format="s16", layout="stereo", rate=AUDIO_RATE)
        origin = _origin(inp)
        for frame in inp.decode(stream):
            if skip is None:  # audio may begin after the video does (a delayed track)
                offset = max(0.0, (frame.time or origin) - origin)
                skip = max(0, round((start - offset) * AUDIO_RATE))
                if start < offset:
                    pcm.extend(bytes(min(want, round((offset - start) * AUDIO_RATE)) * 4))
            for chunk in resampler.resample(frame):
                take(chunk)
            if produced >= skip + want:
                break
        if skip is not None:
            for chunk in resampler.resample(None):
                take(chunk)
    data = bytes(pcm[: want * 4])
    if not data:
        raise MediaError("no audio in the selected range")
    with wave.open(str(dst), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(AUDIO_RATE)
        w.writeframes(data)
    return len(data) / 4 / AUDIO_RATE
