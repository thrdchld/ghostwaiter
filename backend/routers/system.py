from __future__ import annotations
import httpx
from typing import Any
from fastapi import APIRouter, Request, Depends, UploadFile, File
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
