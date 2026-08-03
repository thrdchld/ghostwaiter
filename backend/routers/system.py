from __future__ import annotations
import base64
import io
import json
import zipfile
from datetime import UTC, datetime
import httpx
from typing import Any
from fastapi import APIRouter, Request, Depends, UploadFile, File, HTTPException
from fastapi.responses import Response, FileResponse
from backend.config import settings
from backend.storage import store, new_id, now_iso
from backend.helpers import error, require_auth, workspace_id
from backend.schemas import AIConfigRequest

router = APIRouter(tags=["system"])

async def _github_push_supabase() -> tuple[bool, str]:
    if not settings.github_token or not settings.github_repo:
        return False, "GITHUB_TOKEN or GITHUB_BACKUP_REPO is not configured"
    owner_repo = settings.github_repo.removeprefix("https://github.com/").removesuffix(".git").strip("/")
    if owner_repo.count("/") != 1:
        return False, "Format GITHUB_BACKUP_REPO harus owner/repo"
        
    headers = {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    
    try:
        workspaces_res = store.client.table("workspaces").select("id, data").execute()
        chats_res = store.client.table("chats").select("id, history").execute()
        drafts_res = store.client.table("drafts").select("id, content").execute()
        
        workspaces_data = []
        for ws in workspaces_res.data or []:
            ws_copy = dict(ws)
            if ws_copy.get("id") == "__system__" and isinstance(ws_copy.get("data"), dict):
                data_copy = dict(ws_copy["data"])
                data_copy.pop("ai_config", None)
                ws_copy["data"] = data_copy
            workspaces_data.append(ws_copy)
            
        backup_data = {
            "workspaces": workspaces_data,
            "chats": chats_res.data,
            "drafts": drafts_res.data,
            "timestamp": now_iso()
        }
        content = json.dumps(backup_data, ensure_ascii=False, indent=2)
    except Exception as e:
        return False, f"Failed to fetch data from Supabase: {e}"
        
    async with httpx.AsyncClient(timeout=60, headers=headers) as client:
        branch = "main"
        ref_url = f"https://api.github.com/repos/{owner_repo}/git/ref/heads/{branch}"
        ref_res = await client.get(ref_url)
        if ref_res.status_code == 404:
            branch = "master"
            ref_url = f"https://api.github.com/repos/{owner_repo}/git/ref/heads/{branch}"
            ref_res = await client.get(ref_url)
            
        if ref_res.status_code != 200:
            if ref_res.status_code in (404, 409):
                return False, "Repositori kosong atau tidak ada cabang main/master."
            return False, f"GitHub API (get ref): {ref_res.status_code} {ref_res.text[:200]}"
            
        commit_sha = ref_res.json()["object"]["sha"]
        commit_url = f"https://api.github.com/repos/{owner_repo}/git/commits/{commit_sha}"
        commit_res = await client.get(commit_url)
        if commit_res.status_code != 200:
            return False, f"GitHub API (get commit): {commit_res.status_code} {commit_res.text[:200]}"
            
        base_tree_sha = commit_res.json()["tree"]["sha"]
        tree = [{
            "path": "supabase_backup.json",
            "mode": "100644",
            "type": "blob",
            "content": content
        }]
        
        tree_url = f"https://api.github.com/repos/{owner_repo}/git/trees"
        tree_res = await client.post(tree_url, json={"base_tree": base_tree_sha, "tree": tree})
        if tree_res.status_code != 201:
            return False, f"GitHub API (create tree): {tree_res.status_code} {tree_res.text[:200]}"
            
        new_tree_sha = tree_res.json()["sha"]
        new_commit_url = f"https://api.github.com/repos/{owner_repo}/git/commits"
        new_commit_res = await client.post(new_commit_url, json={
            "message": f"Supabase Backup {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}",
            "tree": new_tree_sha,
            "parents": [commit_sha]
        })
        if new_commit_res.status_code != 201:
            return False, f"GitHub API (create commit): {new_commit_res.status_code} {new_commit_res.text[:200]}"
            
        new_commit_sha = new_commit_res.json()["sha"]
        patch_url = f"https://api.github.com/repos/{owner_repo}/git/refs/heads/{branch}"
        patch_res = await client.patch(patch_url, json={"sha": new_commit_sha})
        if patch_res.status_code != 200:
            return False, f"GitHub API (update ref): {patch_res.status_code} {patch_res.text[:200]}"
            
    try:
        system = store.read_json(store.root / "system" / "settings.json", {})
        system.update({"sync_status": "ok", "last_sync": now_iso()})
        store.write_json(store.root / "system" / "settings.json", system)
    except Exception:
        pass
        
    return True, ""

async def _github_pull_supabase() -> tuple[bool, str]:
    if not settings.github_token or not settings.github_repo:
        return False, "GITHUB_TOKEN or GITHUB_BACKUP_REPO is not configured"
    owner_repo = settings.github_repo.removeprefix("https://github.com/").removesuffix(".git").strip("/")
    if owner_repo.count("/") != 1:
        return False, "Format GITHUB_BACKUP_REPO harus owner/repo"
        
    headers = {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    
    async with httpx.AsyncClient(timeout=120, headers=headers) as client:
        branch = "main"
        ref_url = f"https://api.github.com/repos/{owner_repo}/git/ref/heads/{branch}"
        ref_res = await client.get(ref_url)
        if ref_res.status_code == 404:
            branch = "master"
            ref_url = f"https://api.github.com/repos/{owner_repo}/git/ref/heads/{branch}"
            ref_res = await client.get(ref_url)
            
        if ref_res.status_code != 200:
            return False, f"GitHub API (get ref): {ref_res.status_code} {ref_res.text[:200]}"
            
        commit_sha = ref_res.json()["object"]["sha"]
        tree_url = f"https://api.github.com/repos/{owner_repo}/git/trees/{commit_sha}?recursive=1"
        tree_res = await client.get(tree_url)
        if tree_res.status_code != 200:
            return False, f"GitHub API (get tree): {tree_res.status_code} {tree_res.text[:200]}"
            
        tree = tree_res.json().get("tree", [])
        backup_item = next((item for item in tree if item["path"] == "supabase_backup.json"), None)
        if not backup_item:
            return False, "Backup file 'supabase_backup.json' not found on GitHub repository"
            
        blob_url = backup_item["url"]
        blob_res = await client.get(blob_url)
        if blob_res.status_code != 200:
            return False, f"GitHub API (get blob): {blob_res.status_code} {blob_res.text[:200]}"
            
        blob_data = blob_res.json()
        content_str = base64.b64decode(blob_data["content"]).decode('utf-8')
        
        try:
            backup_data = json.loads(content_str)
            for item in backup_data.get("workspaces", []):
                if item["id"] == "__system__":
                    existing_res = store.client.table("workspaces").select("data").eq("id", "__system__").execute()
                    existing_ai_config = None
                    if existing_res.data:
                        existing_ai_config = existing_res.data[0].get("data", {}).get("ai_config")
                    
                    restored_data = item.get("data") or {}
                    if existing_ai_config:
                        restored_data["ai_config"] = existing_ai_config
                    store.client.table("workspaces").upsert({"id": "__system__", "data": restored_data}).execute()
                else:
                    store.client.table("workspaces").upsert({"id": item["id"], "data": item.get("data")}).execute()
            for item in backup_data.get("chats", []):
                store.client.table("chats").upsert({"id": item["id"], "history": item.get("history")}).execute()
            for item in backup_data.get("drafts", []):
                store.client.table("drafts").upsert({"id": item["id"], "content": item.get("content")}).execute()
        except Exception as e:
            return False, f"Failed to restore data to Supabase: {e}"
            
    try:
        system = store.read_json(store.root / "system" / "settings.json", {})
        system.update({"sync_status": "ok", "last_sync": now_iso()})
        store.write_json(store.root / "system" / "settings.json", system)
    except Exception:
        pass
        
    return True, ""

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

@router.post("/api/sync/run", dependencies=[Depends(require_auth)])
async def run_sync_combined() -> dict[str, Any]:
    if not settings.github_token or not settings.github_repo:
        raise HTTPException(status_code=400, detail="GITHUB_TOKEN or GITHUB_BACKUP_REPO is not configured")
    owner_repo = settings.github_repo.removeprefix("https://github.com/").removesuffix(".git").strip("/")
    if owner_repo.count("/") != 1:
        raise HTTPException(status_code=400, detail="Format GITHUB_BACKUP_REPO harus owner/repo")
        
    headers = {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    
    system = store.read_json(store.root / "system" / "settings.json", {})
    last_sync_str = system.get("last_sync", "")
    
    async with httpx.AsyncClient(timeout=60, headers=headers) as client:
        branch = "main"
        ref_url = f"https://api.github.com/repos/{owner_repo}/git/ref/heads/{branch}"
        ref_res = await client.get(ref_url)
        if ref_res.status_code == 404:
            branch = "master"
            ref_url = f"https://api.github.com/repos/{owner_repo}/git/ref/heads/{branch}"
            ref_res = await client.get(ref_url)
            
        if ref_res.status_code != 200:
            ok, msg = await _github_push_supabase()
            if not ok:
                raise HTTPException(status_code=503, detail=f"GitHub API Error: {ref_res.status_code}. Push fallback failed: {msg}")
            return {"status": "pushed", "last_sync": now_iso(), "detail": "Repository was empty, pushed local state"}
            
        commit_sha = ref_res.json()["object"]["sha"]
        tree_url = f"https://api.github.com/repos/{owner_repo}/git/trees/{commit_sha}?recursive=1"
        tree_res = await client.get(tree_url)
        if tree_res.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Failed to fetch tree: {tree_res.status_code}")
            
        tree = tree_res.json().get("tree", [])
        backup_item = next((item for item in tree if item["path"] == "supabase_backup.json"), None)
        
        if not backup_item:
            ok, msg = await _github_push_supabase()
            if not ok:
                raise HTTPException(status_code=503, detail=msg)
            return {"status": "pushed", "last_sync": now_iso(), "detail": "No backup file found on GitHub, pushed local state"}
            
        blob_res = await client.get(backup_item["url"])
        if blob_res.status_code != 200:
            raise HTTPException(status_code=502, detail="Failed to get backup file details from GitHub")
            
        blob_data = blob_res.json()
        content_str = base64.b64decode(blob_data["content"]).decode('utf-8')
        backup_data = json.loads(content_str)
        github_timestamp = backup_data.get("timestamp", "")

    def parse_iso(t_str):
        if not t_str:
            return datetime.min.replace(tzinfo=UTC)
        try:
            normalized = t_str.replace("Z", "+00:00")
            return datetime.fromisoformat(normalized)
        except Exception:
            return datetime.min.replace(tzinfo=UTC)

    git_time = parse_iso(github_timestamp)
    local_sync_time = parse_iso(last_sync_str)
    
    max_local_update = datetime.min.replace(tzinfo=UTC)
    try:
        ws_res = store.client.table("workspaces").select("data").execute()
        for r in ws_res.data or []:
            up = (r.get("data") or {}).get("updated_at")
            if up:
                t = parse_iso(up)
                if t > max_local_update:
                    max_local_update = t
                    
        chats_res = store.client.table("chats").select("history").execute()
        for r in chats_res.data or []:
            up = (r.get("history") or {}).get("updated_at")
            if up:
                t = parse_iso(up)
                if t > max_local_update:
                    max_local_update = t
                    
        drafts_res = store.client.table("drafts").select("content").execute()
        for r in drafts_res.data or []:
            up = (r.get("content") or {}).get("updated_at")
            if up:
                t = parse_iso(up)
                if t > max_local_update:
                    max_local_update = t
    except Exception:
        pass
        
    if git_time > local_sync_time and git_time > max_local_update:
        try:
            for item in backup_data.get("workspaces", []):
                if item["id"] == "__system__":
                    existing_res = store.client.table("workspaces").select("data").eq("id", "__system__").execute()
                    existing_ai_config = None
                    if existing_res.data:
                        existing_ai_config = existing_res.data[0].get("data", {}).get("ai_config")
                    
                    restored_data = item.get("data") or {}
                    if existing_ai_config:
                        restored_data["ai_config"] = existing_ai_config
                    store.client.table("workspaces").upsert({"id": "__system__", "data": restored_data}).execute()
                else:
                    store.client.table("workspaces").upsert({"id": item["id"], "data": item.get("data")}).execute()
            for item in backup_data.get("chats", []):
                store.client.table("chats").upsert({"id": item["id"], "history": item.get("history")}).execute()
            for item in backup_data.get("drafts", []):
                store.client.table("drafts").upsert({"id": item["id"], "content": item.get("content")}).execute()
                
            system.update({"sync_status": "ok", "last_sync": github_timestamp})
            store.write_json(store.root / "system" / "settings.json", system)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to restore pulled backup: {e}")
        return {"status": "pulled", "last_sync": github_timestamp, "detail": "Pulled newer backup from GitHub"}
        
    elif max_local_update > git_time or max_local_update > local_sync_time:
        ok, msg = await _github_push_supabase()
        if not ok:
            raise HTTPException(status_code=503, detail=msg)
        return {"status": "pushed", "last_sync": now_iso(), "detail": "Pushed newer local changes to GitHub"}
        
    else:
        try:
            system.update({"sync_status": "ok", "last_sync": last_sync_str if last_sync_str else github_timestamp})
            store.write_json(store.root / "system" / "settings.json", system)
        except Exception:
            pass
        return {"status": "synced", "last_sync": last_sync_str if last_sync_str else github_timestamp, "detail": "All data is up to date"}

@router.post("/api/sync/push", dependencies=[Depends(require_auth)])
async def run_sync_push() -> dict[str, Any]:
    ok, message = await _github_push_supabase()
    if not ok:
        raise error(message, 503)
    return {"status": "success", "last_sync": now_iso()}

@router.post("/api/sync/pull", dependencies=[Depends(require_auth)])
async def run_sync_pull() -> dict[str, Any]:
    ok, message = await _github_pull_supabase()
    if not ok:
        raise error(message, 503)
    return {"status": "success", "last_sync": now_iso()}

@router.post("/api/sync/retry", dependencies=[Depends(require_auth)])
async def retry_sync() -> dict[str, Any]:
    ok, message = await _github_push_supabase()
    if not ok:
        raise error(message, 503)
    return {"status": "success", "last_sync": now_iso()}

@router.post("/api/sync/backup-to-github", dependencies=[Depends(require_auth)])
async def backup_to_github() -> dict[str, Any]:
    ok, message = await _github_push_supabase()
    if not ok:
        raise error(message, 500)
    return {"status": "success", "message": "Backup to GitHub successful"}

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
