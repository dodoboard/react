import asyncio

import pytest

from studio.bench import bench
from studio.settings import Settings


@pytest.mark.parametrize("mode, label", [("image", "512×512"), ("motion", "81 frames"), ("talk", "50 frames")])
def test_bench_times_each_run(fake_comfy, tmp_path, capsys, mode, label):
    settings = Settings(comfy_url=fake_comfy.url, data_dir=tmp_path)
    assert asyncio.run(bench(settings, mode, runs=2)) == 0
    out = capsys.readouterr().out
    assert label in out and "run 1:" in out and "includes model load" in out and "run 2:" in out
    seeds = {n["inputs"]["noise_seed"] for g in fake_comfy.prompts for n in g.values() if "noise_seed" in n["inputs"]}
    assert len(seeds) >= 2  # a new seed per run, or ComfyUI would serve the cached output


def test_bench_reports_missing_models(fake_comfy, tmp_path, capsys):
    fake_comfy.app.state.models = {}
    assert asyncio.run(bench(Settings(comfy_url=fake_comfy.url, data_dir=tmp_path), "talk")) == 1
    assert "wav2vec2" in capsys.readouterr().out
