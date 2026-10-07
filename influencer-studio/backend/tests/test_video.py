import pytest

from studio.video import (
    ANIMATE2, DANCER_FRAMES, FILM, WAN22_HIGH, WAN22_LOW, DanceParams, MotionParams, MusicDanceParams,
    build_dance_graph, build_motion_graph, build_music_graph, dance_segments,
)


def nodes(graph, class_type):
    return [(i, n["inputs"]) for i, n in graph.items() if n["class_type"] == class_type]


def assert_links_valid(graph):
    for node in graph.values():
        for value in node["inputs"].values():
            if isinstance(value, list):
                assert value[0] in graph and isinstance(value[1], int)


@pytest.mark.parametrize("frames,expected", [(1, (1, 1)), (40, (41, 1)), (81, (81, 1)), (82, (81, 2)), (161, (81, 2)),
                                             (162, (81, 3)), (320, (81, 4))])
def test_dance_segments(frames, expected):
    length, windows = expected
    assert dance_segments(frames) == (length, windows)
    assert length + (windows - 1) * (length - 1) >= frames  # windows cover every frame


def test_dance_single_window():
    g = build_dance_graph(DanceParams("ref.png", "drv.mp4", 40, 480, 832, "p", 7, audio="a.wav"))
    assert_links_valid(g)
    (_, animate), = nodes(g, "WanAnimate2ToVideo")
    assert animate["length"] == 41 and animate["video_frame_offset"] == 0 and "continue_motion" not in animate
    assert nodes(g, "UNETLoader")[0][1]["unet_name"] == ANIMATE2.name
    assert nodes(g, "WanAnimate2Cache")[0][1] == {"model": ["1", 0], "device": "cpu", "dtype": "int4"}
    (_, create), = nodes(g, "CreateVideo")
    assert create["fps"] == 16 and g[create["audio"][0]]["class_type"] == "LoadAudio"
    assert g.samplers() == [nodes(g, "SamplerCustom")[0][0]]


def test_dance_windows_chain_through_continue_motion():
    g = build_dance_graph(DanceParams("ref.png", "drv.mp4", 200, 480, 832, "p", 7, pose_cache=None, smooth=True))
    assert_links_valid(g)
    animates = nodes(g, "WanAnimate2ToVideo")
    assert len(animates) == 3 and not nodes(g, "WanAnimate2Cache")
    for (prev_id, _), (_, nxt) in zip(animates, animates[1:]):
        assert nxt["video_frame_offset"] == [prev_id, 5]
        assert g[nxt["continue_motion"][0]]["class_type"] == "VAEDecode"
    # every window drops its overlapping frame(s) via the node's trim_image output
    trims = nodes(g, "ImageFromBatch")
    assert sum(1 for _, t in trims if isinstance(t["batch_index"], list)) == 3
    (_, final), = [t for t in trims if t[1]["length"] == 200]
    assert final["batch_index"] == 0
    assert len(nodes(g, "ImageBatch")) == 2 and len(g.samplers()) == 3
    (_, create), = nodes(g, "CreateVideo")
    assert create["fps"] == 32 and "audio" not in create
    assert nodes(g, "FrameInterpolationModelLoader")[0][1]["model_name"] == FILM.name


def test_music_graph():
    g = build_music_graph(MusicDanceParams("img.png", "song.wav", 15, "kpop", "high", 480, 832, 3))
    assert_links_valid(g)
    (_, pad), = nodes(g, "WanDancerPadKeyframesList")
    assert pad["num_segments"] == 3 and pad["segment_length"] == DANCER_FRAMES
    texts = [t["text"] for _, t in nodes(g, "CLIPTextEncode") if isinstance(t["text"], str)]
    assert any("韩舞" in t and "高" in t for t in texts)
    loras = [l["strength_model"] for _, l in nodes(g, "LoraLoaderModelOnly")]
    assert loras == [3.0, 1.03]
    (_, create), = nodes(g, "CreateVideo")
    assert create["fps"] == 30 and "audio" in create
    assert len(g.samplers()) == 2


def test_music_quality_mode_and_validation():
    g = build_music_graph(MusicDanceParams("i.png", "s.wav", 5, "latin", "low", 832, 480, 1, fast=False))
    assert [l["strength_model"] for _, l in nodes(g, "LoraLoaderModelOnly")] == [1.03]
    (_, guider), = nodes(g, "CFGGuider")
    assert guider["cfg"] == 5.0
    with pytest.raises(ValueError):
        build_music_graph(MusicDanceParams("i.png", "s.wav", 7, "latin", "low", 832, 480, 1))


def test_motion_graph_uses_both_wan22_experts():
    g = build_motion_graph(MotionParams("img.png", "the woman spins", 624, 624, 9))
    assert_links_valid(g)
    assert [u["unet_name"] for _, u in nodes(g, "UNETLoader")] == [WAN22_HIGH.name, WAN22_LOW.name]
    high, low = (s for _, s in nodes(g, "KSamplerAdvanced"))
    assert (high["start_at_step"], high["end_at_step"], high["noise_seed"]) == (0, 2, 9)
    assert (low["start_at_step"], low["end_at_step"], low["add_noise"]) == (2, 4, "disable")
    (_, wan), = nodes(g, "WanImageToVideo")
    assert (wan["width"], wan["height"], wan["length"]) == (624, 624, 81)
