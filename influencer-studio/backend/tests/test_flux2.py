import pytest

from studio.flux2 import PROFILES, build_graph

KLEIN = PROFILES["klein-4b"]


def nodes(graph: dict, class_type: str) -> list[tuple[str, dict]]:
    return [(i, n["inputs"]) for i, n in graph.items() if n["class_type"] == class_type]


def assert_links_valid(graph: dict) -> None:
    for node in graph.values():
        for value in node["inputs"].values():
            if isinstance(value, list):
                assert value[0] in graph and value[1] == 0


def test_text_to_image_graph():
    g = build_graph(KLEIN, prompt="hello", width=896, height=1120, seed=7, batch=3)
    assert_links_valid(g)
    (_, unet), = nodes(g, "UNETLoader")
    assert unet["unet_name"] == KLEIN.unet
    (_, clip), = nodes(g, "CLIPLoader")
    assert clip == {"clip_name": KLEIN.text_encoder, "type": "flux2", "device": "default"}
    (_, guider), = nodes(g, "CFGGuider")
    assert guider["cfg"] == KLEIN.cfg
    (_, sched), = nodes(g, "Flux2Scheduler")
    assert sched == {"steps": KLEIN.steps, "width": 896, "height": 1120}
    (_, latent), = nodes(g, "EmptyFlux2LatentImage")
    assert latent["batch_size"] == 3
    assert not nodes(g, "ReferenceLatent")
    assert len(nodes(g, "PreviewImage")) == 1


def test_references_chain_onto_both_conditionings():
    g = build_graph(KLEIN, prompt="p", width=1024, height=1024, seed=1, references=["a.png", "b.png"])
    assert_links_valid(g)
    assert [n["image"] for _, n in nodes(g, "LoadImage")] == ["a.png", "b.png"]
    (_, guider), = nodes(g, "CFGGuider")

    def chain_latents(link: list) -> list[str]:
        out = []
        while g[link[0]]["class_type"] == "ReferenceLatent":
            out.append(g[link[0]]["inputs"]["latent"][0])
            link = g[link[0]]["inputs"]["conditioning"]
        assert g[link[0]]["class_type"] == "CLIPTextEncode"
        return out

    pos, neg = chain_latents(guider["positive"]), chain_latents(guider["negative"])
    assert len(pos) == 2 and pos == neg


def test_too_many_references_rejected():
    with pytest.raises(ValueError):
        build_graph(KLEIN, prompt="p", width=1024, height=1024, seed=1, references=["x.png"] * (KLEIN.max_refs + 1))


def test_lora_sits_between_unet_and_guider():
    g = build_graph(KLEIN, prompt="p", width=1024, height=1024, seed=1, loras=[("me.safetensors", 0.8)])
    (lora_id, lora), = nodes(g, "LoraLoaderModelOnly")
    assert g[lora["model"][0]]["class_type"] == "UNETLoader"
    (_, guider), = nodes(g, "CFGGuider")
    assert guider["model"] == [lora_id, 0]
