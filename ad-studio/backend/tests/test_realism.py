import asyncio
import json
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image

from app.pipeline import luts, realism, speech
from app.providers.tts import Word

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import setup_models  # noqa: E402


def test_turkish_normalization():
    assert speech.spoken("MÖ 1250 yılında 3. firavun", "tr") == "milattan önce bin iki yüz elli yılında üçüncü firavun"
    assert speech.spoken("Fiyat 1.299 TL, %40 indirim!", "tr") == "Fiyat bin iki yüz doksan dokuz lira, yüzde kırk indirim!"
    assert speech.spoken("XV. yüzyıl", "tr") == "on beşinci yüzyıl"
    assert speech.spoken("3,5 km", "tr") == "üç virgül beş kilometre"
    assert speech.tr_int(1001) == "bin bir" and speech.tr_int(2_400_000) == "iki milyon dört yüz bin"
    assert speech.normalize_en("In 1922, 40% of") == "In nineteen twenty-two, forty percent of"


def test_tags_stripped_and_original_spelling_restored():
    orig = ["[whispers] Oda 1922 yılında bulundu.", "Sonra her şey değişti."]
    spoken = [speech.strip_tags(speech.spoken(o, "tr", keep_tags=True)) for o in orig]
    flat = " ".join(spoken).split()
    words = [Word(t, i * 0.3, i * 0.3 + 0.25) for i, t in enumerate(["[whispers]"] + flat)]
    out = speech.remap(speech.clean_words(words), orig, spoken)
    assert [w.text for w in out] == ["Oda", "1922", "yılında", "bulundu.", "Sonra", "her", "şey", "değişti."]
    assert all(a.start <= b.start for a, b in zip(out, out[1:]))
    j = speech.join_with_breaks(["Bir.", "İki?"], ["narration", "presenter"], "eleven_multilingual_v2", "elevenlabs")
    assert '<break time="0.4s" />' in j


def test_lut_file_and_ffmpeg_apply(tmp_path, monkeypatch):
    txt = luts.cube_text("warm_film", size=5)
    rows = [l for l in txt.splitlines() if re.match(r"^[0-9.]+ [0-9.]+ [0-9.]+$", l)]
    assert "LUT_3D_SIZE 5" in txt and len(rows) == 125
    p = tmp_path / "w.cube"
    p.write_text(txt)
    Image.new("RGB", (64, 64), (120, 120, 120)).save(tmp_path / "g.png")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(tmp_path / "g.png"), "-vf", f"lut3d=file={p}",
                    str(tmp_path / "o.png")], check=True)
    r, g, b = Image.open(tmp_path / "o.png").convert("RGB").getpixel((10, 10))
    assert r > b  # warm grade


def test_eased_ken_burns_renders(tmp_path):
    from app.pipeline.compose import WIDE, Segment, render_segment
    Image.new("RGB", (1344, 768), (40, 90, 140)).save(tmp_path / "s.png")
    for i in range(5):
        out = asyncio.run(render_segment(Segment(tmp_path / "s.png", 1.0), tmp_path / f"o{i}.mp4", i, "libx264", False, WIDE))
        assert out.exists() and out.stat().st_size > 1000


def test_voice_mastering_hits_loudness(tmp_path):
    from app.pipeline.compose import WIDE, Effects, Segment, compose
    Image.new("RGB", (1344, 768), (20, 20, 20)).save(tmp_path / "s.png")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=f=220:d=4", "-af", "volume=0.05",
                    str(tmp_path / "v.mp3")], check=True)
    out = asyncio.run(compose([Segment(tmp_path / "s.png", 4.0)], tmp_path / "v.mp3", None, tmp_path / "o.mp4", tmp_path,
                              None, 0, Effects(punch=False, progress_color=None, sfx_volume=0, canvas=WIDE, loudness=-16,
                                               lut=luts.lut_path("cool_doc"))))
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(out), "-af", "loudnorm=print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True)
    stats = json.loads(r.stderr[r.stderr.rindex("{"):])
    assert abs(float(stats["input_i"]) + 16) < 2.0


def test_realism_recipe():
    p = realism.recipe("old harbor with fishing boats, wide shot", "", "doc", key="x")
    assert p.startswith("old harbor") and "establishing" in p and "shot on" in p
    assert "plastic skin" in realism.negative()
    assert realism.doc_shot_type("aerial view of the delta") == "aerial"


def test_workflow_validator():
    from app.api.doctor import node_hint, validate_workflow
    from app.providers import comfy
    graph = comfy.load_workflow("flux_realism")
    info = {"CheckpointLoaderSimple": {"input": {"required": {"ckpt_name": [["flux1-dev-fp8.safetensors"]]}}},
            "CLIPTextEncode": {}, "FluxGuidance": {}, "EmptySD3LatentImage": {}, "KSampler": {}, "LatentUpscaleBy": {},
            "VAEDecode": {}, "UpscaleModelLoader": {"input": {"required": {"model_name": [["other.pth"]]}}},
            "ImageUpscaleWithModel": {}, "SaveImage": {}}
    nodes, models = validate_workflow(graph, info)
    assert nodes == ["ImageScale"] and models == [("model_name", "4x-UltraSharp.pth")]
    assert "PuLID" in node_hint("ApplyPulidFlux")
    talk = comfy.load_workflow("infinitetalk")
    assert any(n["class_type"] == "WanInfiniteTalkToVideo" for n in talk.values())
    assert "_requires" not in comfy.load_workflow("pulid_flux")


def test_setup_manifest(tmp_path):
    entries = setup_models.load()
    sel = setup_models.select(entries, ["infinitetalk"], None)
    assert {e["feature"] for e in sel} == {"infinitetalk", "wan-common"}
    assert setup_models.target(sel[0], tmp_path, tmp_path).parts[-3] == "models"
    f = setup_models.select(entries, ["fonts"], None)[0]
    assert setup_models.target(f, None, tmp_path) == tmp_path / "fonts" / f["file"]
    assert setup_models.main(["--comfy", str(tmp_path), "--only", "upscaler", "--dry-run"]) == 0


def test_pick_animated_budget():
    from app.pipeline.docu.runner import Item, pick_animated
    items = [Item(0, 0, "presenter", 0, 5, "", "", ""), Item(0, 1, "narration", 5, 9, "", "", ""),
             Item(0, 2, "narration", 9, 20, "", "", ""), Item(1, 0, "narration", 20, 23, "", "", ""),
             Item(1, 1, "narration", 23, 25, "", "", "")]
    assert pick_animated(items, 0) == set()
    assert pick_animated(items, 0.5) == {1, 3}  # chapter openers first
    assert pick_animated(items, 0.75) == {1, 3, 2}  # then the longest


def test_doctor_endpoint_reports():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        r = c.get("/api/doctor").json()
        ids = {x["id"] for x in r["checks"]}
        assert {"ffmpeg", "filters", "ollama", "comfy", "yt_lib"} <= ids
        assert next(x for x in r["checks"] if x["id"] == "ollama")["status"] == "fail"  # no Ollama in CI
        assert next(x for x in r["checks"] if x["id"] == "filters")["status"] == "ok"
        assert c.get("/api/doctor/manifest").json()[0]["feature"] == "flux"
