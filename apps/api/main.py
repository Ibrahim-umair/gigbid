"""GigBid API (FastAPI). Serves the React app's typed contract (OpenAPI) and, in production, the
built frontend from apps/web/dist."""
from __future__ import annotations

import contextlib
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

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
    app.mount("/", StaticFiles(directory=DIST, html=True), name="web")
