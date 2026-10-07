from __future__ import annotations

import asyncio
import contextlib
from typing import AsyncIterator

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .catalog import public_catalog
from .comfy import ComfyBackend, ComfyClient
from .flux2 import PROFILES
from .jobs import JobQueue
from .models import (
    BuilderRequest, ContentRequest, CreateCharacterRequest, DanceRequest, IdentityPackRequest,
    MotionPresetRequest, MusicDanceRequest, PromptPreviewRequest, SpeakRequest, TalkRequest,
    UpdateCharacterRequest,
)
from .motion import MotionStudio, new_upload_path, public_schema
from .voice import TTSClient, VoiceStudio
from .voice import public_schema as voice_schema
from .prompting import character_prompt
from .service import Invalid, NotFound, Studio
from .settings import Settings
from .store import Store

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_MEDIA_BYTES = 500 * 1024 * 1024


def create_app(settings: Settings | None = None, comfy: ComfyBackend | None = None,
               tts: TTSClient | None = None) -> FastAPI:
    settings = settings or Settings()
    if settings.profile not in PROFILES:
        raise SystemExit(f"Unknown STUDIO_PROFILE '{settings.profile}'. Options: {', '.join(PROFILES)}")
    comfy = comfy or ComfyClient(settings.comfy_url)
    store = Store(settings.data_dir)
    jobs = JobQueue()
    studio = Studio(PROFILES[settings.profile], comfy, store, jobs)
    if settings.pose_cache not in ("off", "int4", "int8", "default"):
        raise SystemExit("STUDIO_POSE_CACHE must be off, int4, int8 or default")
    motion = MotionStudio(comfy, store, jobs, settings.data_dir / "work",
                          None if settings.pose_cache == "off" else settings.pose_cache)
    tts = tts or TTSClient(settings.tts_url)
    voice = VoiceStudio(comfy, tts, store, jobs, motion)

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        worker = asyncio.create_task(jobs.run_forever())
        yield
        worker.cancel()
        await comfy.aclose()
        await tts.aclose()
        store.close()

    app = FastAPI(title="Influencer Studio", lifespan=lifespan)
    app.state.studio = studio
    app.state.voice = voice

    @app.exception_handler(NotFound)
    async def _not_found(_: Request, e: NotFound) -> JSONResponse:
        return JSONResponse({"detail": str(e)}, status_code=404)

    @app.exception_handler(Invalid)
    async def _invalid(_: Request, e: Invalid) -> JSONResponse:
        return JSONResponse({"detail": str(e)}, status_code=422)

    def job_response(job) -> dict:
        return job.public(jobs.position(job))

    @app.get("/api/schema")
    def schema() -> dict:
        return public_catalog() | {"max_refs": studio.profile.max_refs}

    @app.get("/api/health")
    async def health() -> dict:
        return await studio.health()

    @app.get("/api/loras")
    async def loras() -> list[str]:
        return await studio.loras()

    @app.post("/api/prompt-preview")
    def prompt_preview(req: PromptPreviewRequest) -> dict:
        return {"prompt": character_prompt(req.spec, with_face=req.with_face)}

    @app.post("/api/uploads")
    async def upload(file: UploadFile = File(...)) -> dict:
        data = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "image larger than 15 MB")
        return studio.save_upload(data)

    @app.post("/api/builder/generate")
    async def builder_generate(req: BuilderRequest) -> dict:
        return job_response(studio.generate_candidates(req))

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: str) -> dict:
        if not (job := jobs.get(job_id)):
            raise HTTPException(404, "job not found")
        return job_response(job)

    @app.get("/api/characters")
    def list_characters() -> list[dict]:
        return store.characters()

    @app.post("/api/characters", status_code=201)
    def create_character(req: CreateCharacterRequest) -> dict:
        return studio.create_character(req)

    @app.get("/api/characters/{character_id}")
    def get_character(character_id: str) -> dict:
        return studio.character_detail(character_id)

    @app.patch("/api/characters/{character_id}")
    def update_character(character_id: str, req: UpdateCharacterRequest) -> dict:
        return studio.update_character(character_id, req)

    @app.delete("/api/characters/{character_id}", status_code=204)
    def delete_character(character_id: str) -> Response:
        studio.delete_character(character_id)
        return Response(status_code=204)

    @app.post("/api/characters/{character_id}/identity-pack")
    async def identity_pack(character_id: str, req: IdentityPackRequest) -> dict:
        return job_response(studio.identity_pack(character_id, req.angles))

    @app.post("/api/characters/{character_id}/content")
    async def content(character_id: str, req: ContentRequest) -> dict:
        return job_response(studio.generate_content(character_id, req))

    @app.get("/api/characters/{character_id}/dataset.zip")
    def dataset(character_id: str) -> Response:
        filename, data = studio.export_dataset(character_id)
        return Response(data, media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="{filename}"'})

    @app.get("/api/images/{image_id}")
    def image(image_id: str) -> FileResponse:
        if not store.image(image_id):
            raise HTTPException(404, "image not found")
        return FileResponse(store.image_path(image_id), media_type="image/png",
                            headers={"Cache-Control": "public, max-age=31536000, immutable"})

    @app.delete("/api/images/{image_id}", status_code=204)
    def delete_image(image_id: str) -> Response:
        studio.delete_image(image_id)
        return Response(status_code=204)

    # ── Motion studio ───────────────────────────────────────────────────────
    @app.get("/api/motion/schema")
    def motion_schema() -> dict:
        return public_schema()

    @app.get("/api/motion/health")
    async def motion_health() -> dict:
        return await motion.health()

    @app.post("/api/motion/uploads", status_code=201)
    async def motion_upload(kind: str = Query(...), file: UploadFile = File(...)) -> dict:
        tmp = new_upload_path(motion.work_dir, file.filename or "upload")
        size = 0
        try:
            with tmp.open("wb") as f:  # stream to disk: dance clips can be hundreds of MB
                while chunk := await file.read(1 << 20):
                    size += len(chunk)
                    if size > MAX_MEDIA_BYTES:
                        raise HTTPException(413, "file larger than 500 MB")
                    f.write(chunk)
            return motion.save_upload(kind, file.filename or tmp.name, tmp)
        finally:
            tmp.unlink(missing_ok=True)

    @app.get("/api/motion/uploads")
    def motion_uploads(kind: str = Query(...)) -> list[dict]:
        return motion.uploads(kind)

    @app.post("/api/characters/{character_id}/motion/dance")
    async def motion_dance(character_id: str, req: DanceRequest) -> dict:
        return job_response(motion.dance(character_id, req))

    @app.post("/api/characters/{character_id}/motion/music")
    async def motion_music(character_id: str, req: MusicDanceRequest) -> dict:
        return job_response(motion.music_dance(character_id, req))

    @app.post("/api/characters/{character_id}/motion/preset")
    async def motion_preset(character_id: str, req: MotionPresetRequest) -> dict:
        return job_response(motion.motion(character_id, req))

    @app.get("/api/characters/{character_id}/clips")
    def character_clips(character_id: str) -> list[dict]:
        return motion.clips(character_id)

    @app.get("/api/clips/{clip_id}")
    def clip_file(clip_id: str) -> FileResponse:
        if not (clip := store.clip(clip_id)):
            raise HTTPException(404, "clip not found")
        return FileResponse(store.clip_path(clip), media_type=clip["media_type"],
                            headers={"Cache-Control": "public, max-age=31536000, immutable"})

    @app.delete("/api/clips/{clip_id}", status_code=204)
    def delete_clip(clip_id: str) -> Response:
        motion.delete_clip(clip_id)
        return Response(status_code=204)

    # ── Voice studio ────────────────────────────────────────────────────────
    @app.get("/api/voice/schema")
    def voice_schema_route() -> dict:
        return voice_schema()

    @app.get("/api/voice/health")
    async def voice_health() -> dict:
        return await voice.health()

    @app.post("/api/voice/speak")
    async def voice_speak(req: SpeakRequest) -> dict:
        return job_response(voice.speak(req))

    @app.post("/api/characters/{character_id}/talk")
    async def character_talk(character_id: str, req: TalkRequest) -> dict:
        return job_response(voice.talk(character_id, req))

    if settings.frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=settings.frontend_dist, html=True), name="frontend")

    return app
