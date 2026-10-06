"""Use cases: builder candidates, characters, identity pack, content, dataset export."""

from __future__ import annotations

import io
import random
import re
import zipfile
from typing import Sequence

from .catalog import ANGLE_BY_ID, ASPECTS, PRESET_BY_ID
from .comfy import ComfyBackend
from .flux2 import Profile, build_graph
from .jobs import Job, JobQueue
from .models import BuilderRequest, CharacterSpec, ContentRequest, CreateCharacterRequest, UpdateCharacterRequest
from .prompting import NEGATIVE, angle_prompt, character_prompt, scene_prompt
from .store import Store


class NotFound(LookupError):
    pass


class Invalid(ValueError):
    pass


class Studio:
    def __init__(self, profile: Profile, comfy: ComfyBackend, store: Store, jobs: JobQueue):
        self.profile, self.comfy, self.store, self.jobs = profile, comfy, store, jobs

    # ── helpers ─────────────────────────────────────────────────────────────
    def _character(self, character_id: str) -> dict:
        if not (c := self.store.character(character_id)):
            raise NotFound(f"character {character_id} not found")
        return c

    def _require_image(self, image_id: str) -> dict:
        if not (img := self.store.image(image_id)):
            raise NotFound(f"image {image_id} not found")
        return img

    async def _upload_references(self, image_ids: Sequence[str]) -> list[str]:
        return [
            await self.comfy.upload(self.store.image_path(i).read_bytes(), f"studio_{i}.png") for i in image_ids
        ]

    async def _render(
        self, job: Job, *, prompt: str, aspect: str, seed: int, count: int,
        references: Sequence[str], loras: Sequence[tuple[str, float]] = (), span: tuple[float, float] = (0.0, 1.0),
    ) -> list[bytes]:
        width, height = ASPECTS[aspect]
        graph = build_graph(
            self.profile, prompt=prompt, negative=NEGATIVE if self.profile.cfg > 1 else "",
            width=width, height=height, seed=seed, batch=count, references=references, loras=loras,
        )
        lo, hi = span
        return await self.comfy.run(graph, lambda p: setattr(job, "progress", lo + (hi - lo) * p))

    @staticmethod
    def _seed(seed: int | None) -> int:
        return seed if seed is not None else random.randrange(2**32)

    @staticmethod
    def _loras(character: dict) -> list[tuple[str, float]]:
        return [(character["lora"], character["lora_strength"])] if character.get("lora") else []

    # ── builder ─────────────────────────────────────────────────────────────
    def generate_candidates(self, req: BuilderRequest) -> Job:
        face = [req.face_image_id] if req.face_image_id else []
        for image_id in face:
            # Real photos need the user's confirmation that they may use this face.
            if self._require_image(image_id)["kind"] == "upload" and not req.consent:
                raise Invalid("using a real person's face requires consent")
        prompt = character_prompt(req.spec, with_face=bool(face))
        seed = self._seed(req.seed)

        async def run(job: Job) -> list[dict]:
            refs = await self._upload_references(face)
            images = await self._render(job, prompt=prompt, aspect=req.aspect, seed=seed, count=req.count, references=refs)
            return [self.store.save_image(d, kind="candidate", caption="studio portrait", prompt=prompt, seed=seed) for d in images]

        return self.jobs.submit("builder", run)

    def save_upload(self, data: bytes) -> dict:
        try:
            return self.store.save_image(data, kind="upload", normalize=True)
        except OSError as e:  # PIL.UnidentifiedImageError is an OSError
            raise Invalid("unsupported image file") from e

    # ── characters ──────────────────────────────────────────────────────────
    def create_character(self, req: CreateCharacterRequest) -> dict:
        self._require_image(req.image_id)
        return self.store.create_character(req.name.strip(), req.spec.model_dump(), req.image_id)

    def character_detail(self, character_id: str) -> dict:
        return self._character(character_id) | {"images": self.store.images(character_id)}

    def update_character(self, character_id: str, req: UpdateCharacterRequest) -> dict:
        self._character(character_id)
        refs = req.reference_ids
        if refs is not None:
            refs = list(dict.fromkeys(refs))
            if not 1 <= len(refs) <= self.profile.max_refs:
                raise Invalid(f"select between 1 and {self.profile.max_refs} reference images")
            owned = {i["id"] for i in self.store.images(character_id)}
            if missing := [r for r in refs if r not in owned]:
                raise Invalid(f"images not in this character: {missing}")
        lora = req.lora.strip() if req.lora is not None else None
        self.store.update_character(
            character_id, name=req.name, reference_ids=refs, lora=lora, lora_strength=req.lora_strength
        )
        return self.character_detail(character_id)

    def delete_character(self, character_id: str) -> None:
        self._character(character_id)
        self.store.delete_character(character_id)

    def delete_image(self, image_id: str) -> None:
        img = self._require_image(image_id)
        if img["character_id"] and (c := self.store.character(img["character_id"])):
            if image_id == c["portrait_id"]:
                raise Invalid("the portrait cannot be deleted")
            if image_id in c["reference_ids"]:
                remaining = [r for r in c["reference_ids"] if r != image_id] or [c["portrait_id"]]
                self.store.update_character(c["id"], reference_ids=remaining)
        self.store.delete_image(image_id)

    # ── identity pack ("Soul ID") ───────────────────────────────────────────
    def identity_pack(self, character_id: str, angles: Sequence[str]) -> Job:
        character = self._character(character_id)
        spec = CharacterSpec.model_validate(character["spec"])

        async def run(job: Job) -> list[dict]:
            refs = await self._upload_references([character["portrait_id"]])
            saved = []
            for i, angle_id in enumerate(angles):
                angle = ANGLE_BY_ID[angle_id]
                prompt, seed = angle_prompt(spec, angle), self._seed(None)
                (data,) = await self._render(
                    job, prompt=prompt, aspect="4:5" if angle_id == "full_body" else "1:1", seed=seed, count=1,
                    references=refs, loras=self._loras(character), span=(i / len(angles), (i + 1) / len(angles)),
                )
                saved.append(self.store.save_image(
                    data, kind="reference", caption=angle.scene, prompt=prompt, seed=seed, character_id=character_id
                ))
            return saved

        return self.jobs.submit("identity_pack", run)

    # ── content ─────────────────────────────────────────────────────────────
    def generate_content(self, character_id: str, req: ContentRequest) -> Job:
        character = self._character(character_id)
        spec = CharacterSpec.model_validate(character["spec"])
        preset = PRESET_BY_ID.get(req.preset_id or "")
        scene, extra = (preset.scene, req.prompt) if preset else (req.prompt, "")
        prompt, seed = scene_prompt(spec, scene, extra), self._seed(req.seed)
        caption = ", ".join(filter(None, (scene, extra.strip())))

        async def run(job: Job) -> list[dict]:
            refs = await self._upload_references(character["reference_ids"])
            images = await self._render(
                job, prompt=prompt, aspect=req.aspect, seed=seed, count=req.count,
                references=refs, loras=self._loras(character),
            )
            return [
                self.store.save_image(d, kind="content", caption=caption, prompt=prompt, seed=seed, character_id=character_id)
                for d in images
            ]

        return self.jobs.submit("content", run)

    # ── LoRA dataset export ─────────────────────────────────────────────────
    def export_dataset(self, character_id: str) -> tuple[str, bytes]:
        character = self._character(character_id)
        trigger = "zz_" + (re.sub(r"[^a-z0-9]+", "_", character["name"].lower()).strip("_") or character_id)
        images = [i for i in self.store.images(character_id) if i["kind"] in ("reference", "content")]
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for n, img in enumerate(reversed(images), start=1):
                zf.write(self.store.image_path(img["id"]), f"dataset/{n:03}.png")
                zf.writestr(f"dataset/{n:03}.txt", f"{trigger}, {img['caption']}")
            zf.writestr("train_flux2_klein_4b.yaml", aitk_config(trigger))
        return f"{trigger}_dataset.zip", buf.getvalue()

    # ── status ──────────────────────────────────────────────────────────────
    async def health(self) -> dict:
        profile = {"id": self.profile.id, "label": self.profile.label, "license": self.profile.license,
                   "max_refs": self.profile.max_refs}
        try:
            stats = await self.comfy.system_stats()
        except Exception as e:
            return {"comfy": False, "error": str(e), "profile": profile, "missing_models": []}
        missing = []
        for folder, name in self.profile.required.items():
            try:
                files = {f.replace("\\", "/") for f in await self.comfy.models(folder)}
            except Exception:
                files = set()
            if name not in files:
                missing.append({"folder": folder, "file": name})
        device = (stats.get("devices") or [{}])[0]
        return {"comfy": True, "profile": profile, "missing_models": missing,
                "gpu": device.get("name"), "vram_total": device.get("vram_total")}

    async def loras(self) -> list[str]:
        try:
            return await self.comfy.models("loras")
        except Exception:
            return []


def aitk_config(trigger: str) -> str:
    """ai-toolkit job for a FLUX.2 [klein] 4B character LoRA (fits 16 GB with low_vram + qfloat8)."""
    return f"""job: extension
config:
  name: {trigger}
  process:
    - type: sd_trainer
      training_folder: output
      device: cuda:0
      trigger_word: {trigger}
      network: {{ type: lora, linear: 32, linear_alpha: 32 }}
      save: {{ dtype: float16, save_every: 250, max_step_saves_to_keep: 8 }}
      datasets:
        - folder_path: ./dataset  # use an absolute path to the extracted dataset folder
          caption_ext: txt
          caption_dropout_rate: 0.05
          cache_latents_to_disk: true
          resolution: [512, 768, 1024]
      train:
        batch_size: 1
        steps: 2500
        gradient_accumulation: 1
        train_unet: true
        train_text_encoder: false
        gradient_checkpointing: true
        cache_text_embeddings: true
        noise_scheduler: flowmatch
        timestep_type: weighted
        optimizer: adamw8bit
        lr: 1e-4
        dtype: bf16
      model:
        name_or_path: black-forest-labs/FLUX.2-klein-base-4B
        arch: flux2_klein_4b
        quantize: true
        qtype: qfloat8
        quantize_te: true
        qtype_te: qfloat8
        low_vram: true
        model_kwargs: {{ match_target_res: false }}
      sample:
        sampler: flowmatch
        sample_every: 250
        width: 896
        height: 1120
        prompts:
          - "{trigger}, sitting by a sunlit cafe window holding a latte"
          - "{trigger}, walking down a neon-lit city street at night"
        seed: 42
        guidance_scale: 4
        sample_steps: 25
meta: {{ name: {trigger}, version: "1.0" }}
"""
