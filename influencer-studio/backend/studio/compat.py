"""ComfyUI compatibility: which node types each mode's graphs use, and which this ComfyUI lacks.

The lists are derived from the graph builders themselves (built with placeholder inputs), so
they never drift from what the studio actually sends. An outdated ComfyUI then shows up as
"update ComfyUI: WanInfiniteTalkToVideo is missing" instead of a failed render.
"""

from __future__ import annotations

from functools import cache

from .comfy import ComfyBackend
from .flux2 import Profile, build_graph
from .hd import build_image_upscale_graph, build_video_upscale_graph
from .video import (
    DanceParams, MotionParams, MusicDanceParams, TalkParams, build_dance_graph, build_motion_graph,
    build_music_graph, build_talk_graph,
)


def _types(*graphs: dict) -> frozenset[str]:
    return frozenset(n["class_type"] for g in graphs for n in g.values())


@cache
def required_nodes(profile: Profile) -> dict[str, frozenset[str]]:
    image = _types(build_graph(profile, prompt="p", width=512, height=512, seed=1, references=["r.png"]),
                   build_graph(profile, prompt="p", width=512, height=512, seed=1, init_image="i.png", denoise=0.4))
    plain = _types(build_motion_graph(MotionParams("i.png", "p", 480, 832, 1)))
    smooth = _types(build_motion_graph(MotionParams("i.png", "p", 480, 832, 1, smooth=True))) - plain
    return {
        "image": image,
        "dance": _types(build_dance_graph(DanceParams("i.png", "d.mp4", 81, 480, 832, "p", 1, audio="a.wav"))),
        "music": _types(build_music_graph(MusicDanceParams("i.png", "a.wav", 10, "kpop", "medium", 480, 832, 1))),
        "motion": plain,
        "talk": _types(build_talk_graph(TalkParams("i.png", "a.wav", 100, 480, 832, "p", 1)),
                       build_talk_graph(TalkParams("i.png", "a.wav", 100, 480, 832, "p", 1, audio_2="b.wav",
                                                   mask_1="m1.png", mask_2="m2.png", mix="m.wav"))),
        "smooth": smooth,
        "hd": _types(build_image_upscale_graph("i.png"), build_video_upscale_graph("v.mp4", 1080, 1920)),
    }


async def missing_nodes(comfy: ComfyBackend, profile: Profile) -> dict[str, list[str]]:
    """Per mode, the node types this ComfyUI does not know ({} when it cannot be asked)."""
    try:
        known = await comfy.object_info()
    except Exception:
        return {}
    return {mode: sorted(nodes - known.keys()) for mode, nodes in required_nodes(profile).items()}
