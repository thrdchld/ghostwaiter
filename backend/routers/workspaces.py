from __future__ import annotations
from typing import Any
from fastapi import APIRouter, HTTPException, Depends
from backend.storage import store, safe_id, DEFAULT_WORKSPACE_ID, DEFAULT_WORKSPACE_NAME
from backend.schemas import (
    WorkspaceRequest,
    WorkspaceCreateRequest,
    WorkspaceRenameRequest,
    WorkspaceDeleteRequest,
)

router = APIRouter(prefix="/api/workspace", tags=["workspace"])

@router.get("/list")
def list_workspaces() -> dict[str, Any]:
    return {"items": store.list_workspaces()}

@router.get("/current")
def get_current_workspace() -> dict[str, Any]:
    active_id = store.active_workspace()
    items = store.list_workspaces()
    for ws in items:
        if ws.get("id") == active_id:
            return ws
    return {"id": DEFAULT_WORKSPACE_ID, "name": DEFAULT_WORKSPACE_NAME}

@router.post("/switch")
def switch_workspace(req: WorkspaceRequest) -> dict[str, Any]:
    safe_id(req.workspace_id, "workspace_id")
    current = store.switch_workspace(req.workspace_id)
    return {"status": "ok", "current": current}

@router.post("/create")
def create_workspace(req: WorkspaceCreateRequest) -> dict[str, Any]:
    ws = store.create_workspace(req.name.strip())
    return {"status": "ok", "workspace": ws}

@router.post("/rename")
def rename_workspace(req: WorkspaceRenameRequest) -> dict[str, Any]:
    safe_id(req.workspace_id, "workspace_id")
    try:
        ws = store.rename_workspace(req.workspace_id, req.name.strip())
        return {"status": "ok", "workspace": ws}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/delete")
def delete_workspace(req: WorkspaceDeleteRequest) -> dict[str, Any]:
    safe_id(req.workspace_id, "workspace_id")
    try:
        store.delete_workspace(req.workspace_id)
        return {"status": "ok", "active_workspace": store.active_workspace()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
