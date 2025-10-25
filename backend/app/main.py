from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Ensure models are imported so Base.metadata knows about tables
from . import models  # noqa: F401
from .core.config import settings
from .core.db import Base, engine
from .routes import devices, owner, public, web, well_known


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Auto-create tables in dev (no Alembic yet)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Homebound", version="0.1.0", lifespan=lifespan)

    # CORS for mobile/web dev; tighten allowlist in prod
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ALLOW_ORIGINS_LIST,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health():
        return JSONResponse({"ok": True})

    app.include_router(owner.router, prefix="/api/v1", tags=["owner"])
    app.include_router(devices.router, prefix="/api/v1", tags=["devices"])
    app.include_router(public.router, prefix="/t", tags=["public"])
    app.include_router(web.router, prefix="/web", tags=["web"])
    app.include_router(well_known.router, tags=["well-known"])
    return app


app = create_app()
