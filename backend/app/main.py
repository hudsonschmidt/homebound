from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .routes import owner, public


def create_app() -> FastAPI:
    app = FastAPI(title="Homebound", version="0.1.0")

    @app.get("/health")
    async def health():
        return JSONResponse({"ok": True})

    app.include_router(owner.router, prefix="/api/v1", tags=["owner"])
    app.include_router(public.router, prefix="/t", tags=["public"])

    return app


app = create_app()
