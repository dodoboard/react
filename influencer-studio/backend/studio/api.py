from __future__ import annotations

import asyncio
import contextlib
from typing import AsyncIterator

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .catalog import public_catalog
from .comfy import ComfyBackend, ComfyClient
from .flux2 import PROFILES
from .jobs import JobQueue
from .models import (
    BuilderRequest, ContentRequest, CreateCharacterRequest, IdentityPackRequest,
    PromptPreviewRequest, UpdateCharacterRequest,
)
from .prompting import character_prompt
from .service import Invalid, NotFound, Studio
from .settings import Settings
from .store import Store

MAX_UPLOAD_BYTES = 15 * 1024 * 1024


def create_app(settings: Settings | None = None, comfy: ComfyBackend | None = None) -> FastAPI:
    settings = settings or Settings()
    if settings.profile not in PROFILES:
        raise SystemExit(f"Unknown STUDIO_PROFILE '{settings.profile}'. Options: {', '.join(PROFILES)}")
    comfy = comfy or ComfyClient(settings.comfy_url)
    store = Store(settings.data_dir)
    jobs = JobQueue()
    studio = Studio(PROFILES[settings.profile], comfy, store, jobs)

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        worker = asyncio.create_task(jobs.run_forever())
        yield
        worker.cancel()
        await comfy.aclose()
        store.close()

    app = FastAPI(title="Influencer Studio", lifespan=lifespan)
    app.state.studio = studio

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

    if settings.frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=settings.frontend_dist, html=True), name="frontend")

    return app
