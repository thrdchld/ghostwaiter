from __future__ import annotations
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.config import ROOT_DIR
from backend.routers import (
    auth_router,
    workspaces_router,
    chats_router,
    drafts_router,
    notes_router,
    brain_router,
    ai_router,
    system_router,
)

FRONTEND_DIR = ROOT_DIR / "frontend"

@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield

app = FastAPI(title="Ghostwaiter", version="1.0.0", docs_url="/api/docs", lifespan=lifespan)

# Enable CORS for cross-origin requests (e.g. GitHub Pages frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict):
        payload = exc.detail
    else:
        payload = {"status": "error", "message": str(exc.detail)}
    return JSONResponse(payload, status_code=exc.status_code)

# Register modular API routers
app.include_router(auth_router)
app.include_router(workspaces_router)
app.include_router(chats_router)
app.include_router(drafts_router)
app.include_router(notes_router)
app.include_router(brain_router)
app.include_router(ai_router)
app.include_router(system_router)

# Mount static frontend assets
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="static")
