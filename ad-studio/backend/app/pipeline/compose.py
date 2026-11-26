"""FFmpeg composition: per-segment clips (Ken Burns / hook punch) → concat → captions, progress bar, price badge,
cut whooshes, ducked music, loudness → 1080x1920 mp4."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..config import paths
from ..media import ass_fonts_dir, encoder_args, filter_path, probe, run_ffmpeg, video_encoder

@dataclass(frozen=True)
class Canvas:
    w: int = 1080
    h: int = 1920
    fps: int = 30


VERTICAL = Canvas()
WIDE = Canvas(1920, 1080, 30)
W, H, FPS = VERTICAL.w, VERTICAL.h, VERTICAL.fps
# smoothstep easing: S = p*p*(3-2p), p = on/n — camera accelerates and settles like a real dolly/gimbal
_S = "((on/{n})*(on/{n})*(3-2*(on/{n})))"
MOTIONS = [
    (f"1+0.14*{_S}", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),                       # push in
    (f"1.14-0.14*{_S}", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),                    # pull out
    ("1.12", f"(iw-iw/zoom)*(0.15+0.7*{_S})", "ih/2-(ih/zoom/2)"),                  # lateral pan
    (f"1.04+0.1*{_S}", "iw/2-(iw/zoom/2)", f"(ih-ih/zoom)*(0.7-0.4*{_S})"),         # push + tilt up
    ("1.12", f"(iw-iw/zoom)*(0.85-0.7*{_S})", "(ih-ih/zoom)*0.45"),                 # reverse pan
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
    xfade: float = 0.0  # crossfade seconds between segments (documentary)
    film: bool = False  # vignette + grain
    canvas: Canvas = VERTICAL
    lut: Path | None = None  # 3D LUT colour grade
    loudness: float = -14.0  # LUFS target (-14 social, -16 long-form)
    master_voice: bool = True  # de-ess, compress, presence EQ, room tone
    smooth_fps: bool = True  # motion-interpolate low-fps clips (S2V 16 fps) to canvas fps


async def _fps(p: Path) -> float:
    try:
        st = next(s for s in (await probe(p)).get("streams", []) if s.get("codec_type") == "video")
        num, den = st.get("avg_frame_rate", "0/1").split("/")
        return float(num) / float(den or 1)
    except (StopIteration, ValueError, ZeroDivisionError):
        return 0.0


async def render_segment(seg: Segment, out: Path, idx: int, enc: str, punch: bool, cv: Canvas = VERTICAL,
                         fade_in: bool = True, smooth_fps: bool = False) -> Path:
    W, H, FPS = cv.w, cv.h, cv.fps
    frames = max(2, round(seg.duration * FPS))
    fade = "fade=t=in:st=0:d=0.14:color=white" if punch else ("fade=t=in:st=0:d=0.1" if fade_in else "null")
    if seg.media.suffix.lower() in VIDEO_EXT:
        zoom = "scale=w='iw*(1+0.3*max(0,1-t/0.25))':h=-2:eval=frame," if punch else ""
        src_fps = await _fps(seg.media) if smooth_fps else 0.0
        rate = (f"minterpolate=fps={FPS}:mi_mode=mci:mc_mode=aobmc:vsbmc=1" if 0 < src_fps < 24 else f"fps={FPS}")
        vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},{zoom}crop={W}:{H},{rate},setsar=1,"
              f"trim=end_frame={frames},{fade}")
        args = ["-stream_loop", "-1", "-i", str(seg.media), "-vf", vf, "-frames:v", str(frames), "-an"]
    else:
        z, x, y = (s.replace("{n}", str(frames)) for s in (PUNCH if punch else MOTIONS[idx % len(MOTIONS)]))
        up = 2 if W < H else 1.5  # zoompan jitters on low-res sources; 16:9 frames are already large
        UW, UH = int(W * up) // 2 * 2, int(H * up) // 2 * 2
        vf = (f"scale={UW}:{UH}:force_original_aspect_ratio=increase,crop={UW}:{UH},"
              f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={W}x{H}:fps={FPS},setsar=1,{fade}")
        args = ["-i", str(seg.media), "-vf", vf, "-frames:v", str(frames), "-an"]
    await run_ffmpeg([*args, *encoder_args(enc, "intermediate"), "-r", str(FPS), str(out)])
    return out


async def xfade_join(clips: list[Path], durs: list[float], xf: float, out: Path, enc: str, batch: int = 40) -> Path:
    """Crossfade chain; offsets equal the original cut times. Long lists are joined in batches to bound memory."""
    if len(clips) > batch:
        parts, starts, i = [], [], 0
        while i < len(clips):
            chunk = clips[i:i + batch]
            cd = durs[i:i + batch]
            is_last = i + batch >= len(clips)
            p = out.with_name(f"{out.stem}_b{len(parts)}.mp4")
            await xfade_join(chunk, cd, xf, p, enc)
            parts.append(p)
            starts.append(sum(cd) + (0 if is_last else 0))
            i += batch
        # each batch already ends with its last clip's extra xf tail (except the final one) → chain batches the same way
        res = await xfade_join(parts, starts, xf, out, enc, batch=10 ** 9)
        for p in parts:
            p.unlink(missing_ok=True)
        return res
    args: list[str] = []
    for c in clips:
        args += ["-i", str(c)]
    chain, prev, t = [], "0:v", 0.0
    for k in range(1, len(clips)):
        t += durs[k - 1]
        lab = f"x{k}"
        chain.append(f"[{prev}][{k}:v]xfade=transition=fade:duration={xf:.3f}:offset={max(0.0, t - 0.0):.3f}[{lab}]")
        prev = lab
    graph = ";".join(chain) if chain else "[0:v]null[x0]"
    await run_ffmpeg([*args, "-filter_complex", graph, "-map", f"[{prev if chain else 'x0'}]",
                      *encoder_args(enc, "intermediate"), str(out)])
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
    cv = fx.canvas
    enc = await video_encoder()
    xf = fx.xfade if len(segments) > 1 else 0.0
    # with crossfades every clip (except the last) is rendered xf longer so cut points stay on the audio timeline
    clips = [await render_segment(Segment(s.media, s.duration + (xf if i < len(segments) - 1 else 0)),
                                  work / f"seg_{i}.mp4", i, enc, fx.punch and i == 0, cv, fade_in=not xf or i == 0,
                                  smooth_fps=fx.smooth_fps)
             for i, s in enumerate(segments)]
    lst = work / "concat.txt"
    joined = work / "joined.mp4"
    if xf:
        await xfade_join(clips, [s.duration for s in segments], xf, joined, enc)
        lst.write_text("")
    else:
        lst.write_text("".join(f"file '{c.resolve().as_posix()}'\n" for c in clips))
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

    grade = f"lut3d=file='{filter_path(fx.lut)}'," if fx.lut and fx.lut.exists() else ""  # grade before text
    subs = f"subtitles=filename='{filter_path(ass)}':fontsdir='{ass_fonts_dir()}'" if ass else "null"
    v = [f"[0:v]{grade}{subs}[v0]"]
    cur = "v0"
    if fx.film:
        v.append(f"[{cur}]vignette=PI/5,noise=alls=5:allf=t[vf]")
        cur = "vf"
    if fx.progress_color:
        v.append(f"[{cur}]drawbox=x=0:y=0:w='iw*t/{total:.3f}':h=12:color={_hex(fx.progress_color)}@0.95:t=fill[vp]")
        cur = "vp"
    for k, (o, ii) in enumerate(zip(fx.overlays, ov_idx)):
        v.append(f"[{ii}:v]format=rgba,fade=t=in:st={o.start:.2f}:d=0.25:alpha=1[ov{k}]")
        v.append(f"[{cur}][ov{k}]overlay=x={o.x}:y={o.y}:enable='between(t,{o.start:.2f},{o.end:.2f})'[vo{k}]")
        cur = f"vo{k}"

    chain = ("highpass=f=80,deesser=i=0.35,acompressor=threshold=-20dB:ratio=2.5:attack=8:release=160:makeup=1.5,"
             "equalizer=f=3200:t=q:w=1.4:g=1.8," if fx.master_voice else "")
    a = [f"[1:a]aresample=48000,{chain}apad{',asplit=2[voice][sc]' if music else '[voice]'}"]
    mix = ["[voice]"]
    if fx.master_voice:  # never true digital silence between lines — it reads as synthetic
        a.append(f"anoisesrc=d={total + 1:.2f}:c=pink:r=48000:a=0.0013,lowpass=f=6000[room]")
        mix.append("[room]")
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
             f"afade=t=out:st={max(0, total - 0.6):.2f}:d=0.6,loudnorm=I={fx.loudness:g}:TP=-1.5:LRA=11[a]")

    await run_ffmpeg([*inputs, "-filter_complex", ";".join(v + a), "-map", f"[{cur}]", "-map", "[a]",
                      *encoder_args(enc, "final"), "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                      "-t", f"{total:.3f}", "-movflags", "+faststart", str(out)])
    for c in (*clips, joined, lst):
        c.unlink(missing_ok=True)
    return out
