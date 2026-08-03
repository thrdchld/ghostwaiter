from __future__ import annotations
import io
import json
import zipfile
import httpx
from typing import Any
from fastapi import APIRouter, Request, Depends, UploadFile, File
from fastapi.responses import Response, FileResponse
from backend.config import settings
from backend.storage import store, new_id, now_iso
from backend.helpers import error, require_auth, workspace_id
from backend.schemas import AIConfigRequest

router = APIRouter(tags=["system"])

@router.head("/api/health")
@router.get("/api/health")
@router.head("/health")
@router.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "timestamp": now_iso(), "storage": str(store.root)}

@router.get("/api/sync/status", dependencies=[Depends(require_auth)])
def sync_status() -> dict[str, Any]:
    try:
        if not settings.supabase_url or not settings.supabase_key or store.client.__class__.__name__ == "MockSupabaseClient":
            supabase_connected = False
        else:
            store.client.table("workspaces").select("id").limit(1).execute()
            supabase_connected = True
    except Exception as e:
        print(f"Supabase connection check failed: {e}", flush=True)
        supabase_connected = False

    return {
        "supabase_configured": bool(settings.supabase_url and settings.supabase_key),
        "supabase_connected": supabase_connected,
    }

@router.get("/api/sync/queue", dependencies=[Depends(require_auth)])
def sync_queue() -> dict[str, Any]:
    return store.read_json(store.root / "queue" / "pending_sync.json", {})

@router.get("/api/ai/config", dependencies=[Depends(require_auth)])
def get_ai_config() -> dict[str, Any]:
    try:
        res = store.client.table("workspaces").select("data").eq("id", "__system__").execute()
        if res.data:
            data = res.data[0].get("data") or {}
            return data.get("ai_config") or {"provider": "", "model": "", "keys": {}}
    except Exception as e:
        print(f"Failed to get AI config: {e}", flush=True)
    return {"provider": "", "model": "", "keys": {}}

@router.post("/api/ai/config", dependencies=[Depends(require_auth)])
def save_ai_config(req: AIConfigRequest) -> dict[str, str]:
    try:
        res = store.client.table("workspaces").select("data").eq("id", "__system__").execute()
        current_data = {}
        if res.data:
            current_data = res.data[0].get("data") or {}
        current_data["ai_config"] = req.model_dump()
        store.client.table("workspaces").upsert({"id": "__system__", "data": current_data}).execute()
        return {"status": "success"}
    except Exception as e:
        raise error(f"Failed to save AI config: {e}", 500)

@router.get("/api/reference/list", dependencies=[Depends(require_auth)])
def list_references(workspace_id_query: str | None = None) -> dict[str, Any]:
    ws = workspace_id(workspace_id_query)
    refs = store.list_entities(ws, "references")
    return {"items": refs}

@router.get("/api/export", dependencies=[Depends(require_auth)])
def export_data() -> Response:
    mem_file = io.BytesIO()
    with zipfile.ZipFile(mem_file, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in store.root.rglob("*"):
            if file_path.is_file():
                rel_path = file_path.relative_to(store.root)
                zf.write(file_path, rel_path)
    mem_file.seek(0)
    return Response(
        mem_file.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=ghostwaiter_export_{int(now_iso()) if hasattr(now_iso(), '__int__') else 'data'}.zip"}
    )

@router.post("/api/import", dependencies=[Depends(require_auth)])
async def import_data(file: UploadFile = File(...)) -> dict[str, Any]:
    if not file.filename.endswith(".zip"):
        raise error("File format must be ZIP", 400)
    contents = await file.read()
    mem_file = io.BytesIO(contents)
    try:
        with zipfile.ZipFile(mem_file, "r") as zf:
            zf.extractall(store.root)
        return {"status": "success", "message": "Import completed"}
    except Exception as e:
        raise error(f"Import failed: {e}", 400)

@router.post("/api/snapshot/create", dependencies=[Depends(require_auth)])
def create_snapshot() -> dict[str, Any]:
    return store.create_snapshot()

@router.get("/api/snapshot/list", dependencies=[Depends(require_auth)])
def list_snapshots() -> dict[str, Any]:
    manifest_path = store.root / "snapshots" / "manifest.json"
    if manifest_path.exists():
        return store.read_json(manifest_path)
    return {"items": []}

@router.get("/api/snapshot/download/{snapshot_id}", dependencies=[Depends(require_auth)])
def download_snapshot(snapshot_id: str) -> FileResponse:
    try:
        path = store.snapshot_path(snapshot_id)
    except (FileNotFoundError, ValueError) as exc:
        raise error("Snapshot not found", 404) from exc
    return FileResponse(path, media_type="application/zip", filename=path.name)
