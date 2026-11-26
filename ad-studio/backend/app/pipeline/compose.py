"""FFmpeg composition: per-segment normalized clips → concat → subtitles + ducked music + loudness → 1080x1920 mp4."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..media import encoder_args, filter_path, ass_fonts_dir, run_ffmpeg, video_encoder

W, H, FPS = 1080, 1920, 30
MOTIONS = [
    ("min(zoom+0.0009,1.18)", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),            # zoom in center
    ("if(eq(on,0),1.18,max(zoom-0.0009,1.0))", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),  # zoom out
    ("1.15", "(iw-iw/zoom)*on/{n}", "ih/2-(ih/zoom/2)"),                            # pan left→right
    ("min(zoom+0.0007,1.15)", "iw/2-(iw/zoom/2)", "(ih-ih/zoom)*(1-on/{n})"),       # zoom + tilt up
]


@dataclass
class Segment:
    media: Path
    duration: float


async def render_segment(seg: Segment, out: Path, idx: int, enc: str) -> Path:
    frames = max(2, round(seg.duration * FPS))
    fade = f"fade=t=in:st=0:d=0.12"
    if seg.media.suffix.lower() in (".mp4", ".webm", ".mov", ".gif", ".webp"):
        vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},setsar=1,"
              f"trim=end_frame={frames},{fade}")
        args = ["-stream_loop", "-1", "-i", str(seg.media), "-vf", vf, "-frames:v", str(frames), "-an"]
    else:
        z, x, y = (s.replace("{n}", str(frames)) for s in MOTIONS[idx % len(MOTIONS)])
        # upscale first: zoompan jitters on low-res sources
        vf = (f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2},"
              f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={W}x{H}:fps={FPS},setsar=1,{fade}")
        args = ["-i", str(seg.media), "-vf", vf, "-frames:v", str(frames), "-an"]
    await run_ffmpeg([*args, *encoder_args(enc, "intermediate"), "-r", str(FPS), str(out)])
    return out


async def compose(segments: list[Segment], voice: Path, ass: Path, out: Path, work: Path,
                  music: Path | None, music_volume: float) -> Path:
    enc = await video_encoder()
    clips = [await render_segment(s, work / f"seg_{i}.mp4", i, enc) for i, s in enumerate(segments)]
    lst = work / "concat.txt"
    lst.write_text("".join(f"file '{c.resolve().as_posix()}'\n" for c in clips))
    joined = work / "joined.mp4"
    await run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined)])

    total = sum(s.duration for s in segments)
    vf = f"[0:v]subtitles=filename='{filter_path(ass)}':fontsdir='{ass_fonts_dir()}'[v]"
    if music:
        af = (f"[1:a]aresample=48000,apad,asplit=2[vo][sc];"
              f"[2:a]aresample=48000,volume={music_volume}[mu];"
              f"[mu][sc]sidechaincompress=threshold=0.03:ratio=10:attack=15:release=350[duck];"
              f"[vo][duck]amix=inputs=2:duration=first:normalize=0,afade=t=out:st={max(0, total - 0.6):.2f}:d=0.6,"
              f"loudnorm=I=-14:TP=-1.5:LRA=11[a]")
        inputs = ["-i", str(joined), "-i", str(voice), "-stream_loop", "-1", "-i", str(music)]
    else:
        af = "[1:a]aresample=48000,apad,loudnorm=I=-14:TP=-1.5:LRA=11[a]"
        inputs = ["-i", str(joined), "-i", str(voice)]
    await run_ffmpeg([*inputs, "-filter_complex", f"{vf};{af}", "-map", "[v]", "-map", "[a]",
                      *encoder_args(enc, "final"), "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                      "-t", f"{total:.3f}", "-movflags", "+faststart", str(out)])
    for c in (*clips, joined, lst):
        c.unlink(missing_ok=True)
    return out
