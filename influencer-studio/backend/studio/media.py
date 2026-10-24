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
            duration = container.duration / av.time_base if container.duration else _scan_duration(path)
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


def _scan_duration(path: Path) -> float:
    """Duration of files without one in the header (browser MediaRecorder WebM): demux to the last packet."""
    with av.open(str(path)) as container:
        end = 0.0
        for packet in container.demux():
            if packet.pts is not None and packet.time_base:
                end = max(end, float((packet.pts + (packet.duration or 0)) * packet.time_base))
        return max(0.0, end - _origin(container))


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


def split_video(src: Path, dst_dir: Path, frames_per_chunk: int) -> list[Path]:
    """Silent, near-lossless (crf 12) MP4 chunks of `frames_per_chunk` frames at the source size and rate.

    Lets a long clip go through a per-frame model (upscaling) a few seconds at a time instead of
    holding every upscaled frame in RAM at once.
    """
    chunks: list[Path] = []
    out = enc = None

    def close() -> None:
        if out is not None:
            for packet in enc.encode():
                out.mux(packet)
            out.close()

    with av.open(str(src)) as inp:
        stream = inp.streams.video[0]
        rate = stream.average_rate or 25
        written = frames_per_chunk
        for frame in inp.decode(stream):
            if written == frames_per_chunk:
                close()
                chunks.append(dst_dir / f"chunk_{len(chunks):03}.mp4")
                out = av.open(str(chunks[-1]), "w", format="mp4")
                enc = out.add_stream("libx264", rate=rate)
                enc.width, enc.height, enc.pix_fmt = frame.width, frame.height, "yuv420p"
                enc.options = {"crf": "12", "preset": "veryfast"}
                written = 0
            image = frame.reformat(format="yuv420p")
            image.pts = written
            image.time_base = enc.codec_context.time_base
            for packet in enc.encode(image):
                out.mux(packet)
            written += 1
        close()
    if not chunks:
        raise MediaError("no video frames")
    return chunks


def join_video(chunks: list[Path], dst: Path, *, rate, audio_src: Path | None = None) -> int:
    """Concatenate video chunks into one H.264 MP4 (crf 18) with `audio_src`'s audio as AAC. Returns frames."""
    with av.open(str(chunks[0])) as first:
        width, height = first.streams.video[0].codec_context.width, first.streams.video[0].codec_context.height
    with av.open(str(dst), "w", format="mp4", options={"movflags": "+faststart"}) as out:
        video = out.add_stream("libx264", rate=rate)
        video.width, video.height, video.pix_fmt = width, height, "yuv420p"
        video.options = {"crf": "18", "preset": "fast"}
        audio_in = av.open(str(audio_src)) if audio_src else None
        try:
            has_audio = bool(audio_in and audio_in.streams.audio)
            audio = out.add_stream("aac", rate=48000, layout="stereo") if has_audio else None
            if audio is not None:
                audio.bit_rate = 192_000
            frames = 0
            for chunk in chunks:
                with av.open(str(chunk)) as inp:
                    for frame in inp.decode(video=0):
                        image = frame.reformat(width=width, height=height, format="yuv420p")
                        image.pts = frames
                        image.time_base = video.codec_context.time_base
                        for packet in video.encode(image):
                            out.mux(packet)
                        frames += 1
            for packet in video.encode():
                out.mux(packet)
            if audio is not None:
                resampler = av.AudioResampler(format="fltp", layout="stereo", rate=48000)
                samples, limit = 0, round(frames / float(rate) * 48000)  # never run past the picture
                for frame in [*audio_in.decode(audio=0), None]:
                    for chunk in resampler.resample(frame):
                        if samples >= limit:
                            break
                        chunk.pts = samples
                        samples += chunk.samples
                        for packet in audio.encode(chunk):
                            out.mux(packet)
                for packet in audio.encode():
                    out.mux(packet)
        finally:
            if audio_in is not None:
                audio_in.close()
    return frames
