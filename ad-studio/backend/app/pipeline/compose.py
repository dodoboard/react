"""FFmpeg composition: per-segment clips (Ken Burns / hook punch) → concat → captions, progress bar, price badge,
cut whooshes, ducked music, loudness → 1080x1920 mp4."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..config import paths
from ..media import ass_fonts_dir, encoder_args, filter_path, run_ffmpeg, video_encoder

W, H, FPS = 1080, 1920, 30
MOTIONS = [
    ("min(zoom+0.0009,1.18)", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),            # zoom in
    ("if(eq(on,0),1.18,max(zoom-0.0009,1.0))", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),  # zoom out
    ("1.15", "(iw-iw/zoom)*on/{n}", "ih/2-(ih/zoom/2)"),                            # pan
    ("min(zoom+0.0007,1.15)", "iw/2-(iw/zoom/2)", "(ih-ih/zoom)*(1-on/{n})"),       # zoom + tilt
]
# hook: fast punch-in from 1.35 over ~8 frames, then slow push
PUNCH = ("if(lt(on,8),1.35-0.035*on,min(1.07+0.0006*(on-8),1.2))", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)")
VIDEO_EXT = (".mp4", ".webm", ".mov", ".gif", ".webp")


@dataclass
class Segment:
    media: Path
    duration: float


@dataclass
class Overlay:
    image: Path
    start: float
    end: float
    x: str = "W-w-50"
    y: str = "H*0.25"


@dataclass
class Effects:
    punch: bool = True
    progress_color: str | None = "#FFD400"
    sfx_volume: float = 0.35
    overlays: list[Overlay] = field(default_factory=list)


async def render_segment(seg: Segment, out: Path, idx: int, enc: str, punch: bool) -> Path:
    frames = max(2, round(seg.duration * FPS))
    fade = "fade=t=in:st=0:d=0.14:color=white" if punch else "fade=t=in:st=0:d=0.1"
    if seg.media.suffix.lower() in VIDEO_EXT:
        zoom = "scale=w='iw*(1+0.3*max(0,1-t/0.25))':h=-2:eval=frame," if punch else ""
        vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},{zoom}crop={W}:{H},fps={FPS},setsar=1,"
              f"trim=end_frame={frames},{fade}")
        args = ["-stream_loop", "-1", "-i", str(seg.media), "-vf", vf, "-frames:v", str(frames), "-an"]
    else:
        z, x, y = (s.replace("{n}", str(frames)) for s in (PUNCH if punch else MOTIONS[idx % len(MOTIONS)]))
        vf = (f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2},"
              f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={W}x{H}:fps={FPS},setsar=1,{fade}")
        args = ["-i", str(seg.media), "-vf", vf, "-frames:v", str(frames), "-an"]
    await run_ffmpeg([*args, *encoder_args(enc, "intermediate"), "-r", str(FPS), str(out)])
    return out


async def whoosh() -> Path:
    p = paths.root / "sfx_whoosh.wav"
    if not p.exists():
        await run_ffmpeg(["-f", "lavfi", "-i", "anoisesrc=d=0.5:c=pink:a=0.7:r=48000", "-af",
                          "highpass=f=350,lowpass=f=5000,afade=t=in:d=0.28:curve=exp,afade=t=out:st=0.28:d=0.22,volume=1.4",
                          "-ac", "2", str(p)])
    return p


def _hex(c: str) -> str:
    return "0x" + c.lstrip("#")


async def compose(segments: list[Segment], voice: Path, ass: Path, out: Path, work: Path,
                  music: Path | None, music_volume: float, fx: Effects | None = None) -> Path:
    fx = fx or Effects()
    enc = await video_encoder()
    clips = [await render_segment(s, work / f"seg_{i}.mp4", i, enc, fx.punch and i == 0) for i, s in enumerate(segments)]
    lst = work / "concat.txt"
    lst.write_text("".join(f"file '{c.resolve().as_posix()}'\n" for c in clips))
    joined = work / "joined.mp4"
    await run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined)])

    total = sum(s.duration for s in segments)
    cuts, t = [], 0.0
    for s in segments[:-1]:
        t += s.duration
        cuts.append(t)

    inputs = ["-i", str(joined), "-i", str(voice)]
    idx = 2
    mi = si = None
    if music:
        inputs += ["-stream_loop", "-1", "-i", str(music)]
        mi, idx = idx, idx + 1
    if fx.sfx_volume > 0 and cuts:
        inputs += ["-i", str(await whoosh())]
        si, idx = idx, idx + 1
    ov_idx = []
    for o in fx.overlays:
        inputs += ["-loop", "1", "-t", f"{total:.3f}", "-i", str(o.image)]
        ov_idx.append(idx)
        idx += 1

    v = [f"[0:v]subtitles=filename='{filter_path(ass)}':fontsdir='{ass_fonts_dir()}'[v0]"]
    cur = "v0"
    if fx.progress_color:
        v.append(f"[{cur}]drawbox=x=0:y=0:w='iw*t/{total:.3f}':h=12:color={_hex(fx.progress_color)}@0.95:t=fill[vp]")
        cur = "vp"
    for k, (o, ii) in enumerate(zip(fx.overlays, ov_idx)):
        v.append(f"[{ii}:v]format=rgba,fade=t=in:st={o.start:.2f}:d=0.25:alpha=1[ov{k}]")
        v.append(f"[{cur}][ov{k}]overlay=x={o.x}:y={o.y}:enable='between(t,{o.start:.2f},{o.end:.2f})'[vo{k}]")
        cur = f"vo{k}"

    a = [f"[1:a]aresample=48000,apad{',asplit=2[voice][sc]' if music else '[voice]'}"]
    mix = ["[voice]"]
    if music:
        a.append(f"[{mi}:a]aresample=48000,volume={music_volume}[mu]")
        a.append("[mu][sc]sidechaincompress=threshold=0.03:ratio=10:attack=15:release=350[duck]")
        mix.append("[duck]")
    if si is not None:
        a.append(f"[{si}:a]aresample=48000,volume={fx.sfx_volume},asplit={len(cuts)}" + "".join(f"[w{k}]" for k in range(len(cuts))))
        for k, c in enumerate(cuts):
            ms = max(0, int((c - 0.22) * 1000))
            a.append(f"[w{k}]adelay={ms}|{ms}[wd{k}]")
            mix.append(f"[wd{k}]")
    a.append(f"{''.join(mix)}amix=inputs={len(mix)}:duration=first:normalize=0,"
             f"afade=t=out:st={max(0, total - 0.6):.2f}:d=0.6,loudnorm=I=-14:TP=-1.5:LRA=11[a]")

    await run_ffmpeg([*inputs, "-filter_complex", ";".join(v + a), "-map", f"[{cur}]", "-map", "[a]",
                      *encoder_args(enc, "final"), "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                      "-t", f"{total:.3f}", "-movflags", "+faststart", str(out)])
    for c in (*clips, joined, lst):
        c.unlink(missing_ok=True)
    return out
