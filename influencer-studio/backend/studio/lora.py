"""Character LoRA training inside the studio, with ai-toolkit.

The influencer's reference and content images become a captioned dataset, ai-toolkit trains a
FLUX.2 [klein] 4B LoRA in its own Python environment (a subprocess; its progress bar is parsed),
and the result is copied to ComfyUI's models/loras/ and assigned to the character.
Training takes the whole GPU, so ComfyUI's models are unloaded first.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
from collections import deque
from pathlib import Path

from .comfy import ComfyBackend
from .jobs import Job, JobQueue
from .service import Invalid, NotFound, Studio, aitk_config
from .settings import Settings
from .store import Store

MIN_IMAGES = 10
DEFAULT_STEPS = 2500
LORA_STRENGTH = 0.9
_PROGRESS = re.compile(r"(\d+)/(\d+) \[")  # tqdm: " 12%|█▏      | 300/2500 [10:01<1:13:02, ..."


class LoraTrainer:
    def __init__(self, settings: Settings, store: Store, jobs: JobQueue, comfy: ComfyBackend, studio: Studio):
        self.settings, self.store, self.jobs, self.comfy, self.studio = settings, store, jobs, comfy, studio

    def _python(self) -> Path | None:
        if self.settings.aitk_python:
            return Path(self.settings.aitk_python)
        for candidate in ("venv/Scripts/python.exe", ".venv/Scripts/python.exe", "venv/bin/python", ".venv/bin/python"):
            if (path := self.settings.aitk_dir / candidate).exists():
                return path
        return None

    def _loras_dir(self) -> Path | None:
        return Path(self.settings.comfy_dir) / "models" / "loras" if self.settings.comfy_dir else None

    def status(self, character_id: str) -> dict:
        character = self.store.character(character_id)
        if not character:
            raise NotFound(f"character {character_id} not found")
        problems = []
        if not (self.settings.aitk_dir / "run.py").exists() or self._python() is None:
            problems.append("ai-toolkit is not installed: run scripts\\install_aitk.bat")
        loras = self._loras_dir()
        if loras is None or not loras.parent.is_dir():
            problems.append("set STUDIO_COMFY_DIR to your ComfyUI folder (the one containing models/)")
        images = len(self.studio.dataset_images(character_id))
        if images < MIN_IMAGES:
            problems.append(f"{images}/{MIN_IMAGES} images: generate an identity pack and some content first")
        return {"ready": not problems, "problems": problems, "images": images, "min_images": MIN_IMAGES,
                "trigger": Studio.trigger(character), "lora": character["lora"]}

    def train(self, character_id: str, steps: int = DEFAULT_STEPS) -> Job:
        status = self.status(character_id)
        if not status["ready"]:
            raise Invalid("; ".join(status["problems"]))
        character = self.store.character(character_id)
        trigger = status["trigger"]
        images = self.studio.dataset_images(character_id)

        async def run(job: Job) -> list[dict]:
            work = self.settings.data_dir / "lora" / character_id / job.id
            dataset = work / "dataset"
            dataset.mkdir(parents=True, exist_ok=True)
            for n, img in enumerate(reversed(images), start=1):
                shutil.copy(self.store.image_path(img["id"]), dataset / f"{n:03}.png")
                (dataset / f"{n:03}.txt").write_text(f"{trigger}, {img['caption']}", encoding="utf-8")
            config = work / "train.yaml"
            config.write_text(aitk_config(trigger, dataset=dataset.as_posix(), output=(work / "output").as_posix(),
                                          steps=steps), encoding="utf-8")
            try:
                await self.comfy.free()  # training needs all 16 GB
            except Exception:
                pass
            log = await self._run_aitk(job, config, steps)
            result = self._result(work / "output" / trigger, trigger)
            if result is None:
                raise RuntimeError("ai-toolkit finished without a LoRA file. Last output:\n" + "\n".join(log))
            name = f"{trigger}.safetensors"
            shutil.copy(result, self._loras_dir() / name)
            self.store.update_character(character["id"], lora=name, lora_strength=LORA_STRENGTH)
            return [{"id": character["id"], "lora": name, "steps": steps}]

        return self.jobs.submit("lora", run, group="lora")

    async def _run_aitk(self, job: Job, config: Path, steps: int) -> list[str]:
        env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
        process = await asyncio.create_subprocess_exec(
            str(self._python()), "run.py", str(config), cwd=self.settings.aitk_dir, env=env,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        tail: deque[str] = deque(maxlen=20)
        try:
            buffer = b""
            while chunk := await process.stdout.read(4096):  # tqdm redraws with \r, not \n
                buffer += chunk
                *lines, buffer = re.split(rb"[\r\n]", buffer)
                for raw in lines:
                    line = raw.decode("utf-8", "replace").strip()
                    if not line:
                        continue
                    tail.append(line)
                    for done, total in _PROGRESS.findall(line):
                        if int(total) == steps:
                            job.progress = 0.02 + 0.97 * int(done) / steps
            code = await process.wait()
        except asyncio.CancelledError:
            process.kill()
            await process.wait()
            raise
        if code != 0:
            raise RuntimeError(f"ai-toolkit exited with code {code}:\n" + "\n".join(tail))
        return list(tail)

    @staticmethod
    def _result(folder: Path, trigger: str) -> Path | None:
        final = folder / f"{trigger}.safetensors"
        if final.exists():
            return final
        saves = sorted(folder.glob(f"{trigger}_*.safetensors"))  # interim saves, step-numbered
        return saves[-1] if saves else None
