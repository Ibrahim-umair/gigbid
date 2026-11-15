"""GigBid API (FastAPI). Serves the React app's typed contract (OpenAPI) and, in production, the
built frontend from apps/web/dist (with an SPA fallback so deep links like /inbox survive a
refresh)."""
from __future__ import annotations

import contextlib
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from apps.api.auth import users
from apps.api.routers.core import router
from apps.api.service import RT


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    await RT.start()
    users.init()
    yield
    await RT.stop()


app = FastAPI(title="GigBid API", version="0.2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(router, prefix="/api")

DIST = Path(__file__).resolve().parents[1] / "web/dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.exception_handler(StarletteHTTPException)
    async def spa_fallback(request: Request, exc: StarletteHTTPException):
        path = request.url.path
        if exc.status_code == 404 and not path.startswith("/api"):
            f = DIST / path.lstrip("/")
            return FileResponse(f if f.is_file() else DIST / "index.html")
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code,
                            headers=getattr(exc, "headers", None))
