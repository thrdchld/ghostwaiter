from __future__ import annotations
from typing import Any
from fastapi import APIRouter, HTTPException, Depends
from backend.storage import store, safe_id, DEFAULT_WORKSPACE_ID, DEFAULT_WORKSPACE_NAME
from backend.helpers import require_auth, error
from backend.schemas import (
    WorkspaceRequest,
    WorkspaceCreateRequest,
    WorkspaceRenameRequest,
    WorkspaceDeleteRequest,
)

router = APIRouter(prefix="/api/workspace", tags=["workspace"])

@router.get("/list", dependencies=[Depends(require_auth)])
def list_workspaces() -> dict[str, Any]:
    return {"items": store.list_workspaces()}

@router.get("/current", dependencies=[Depends(require_auth)])
def get_current_workspace() -> dict[str, Any]:
    active_id = store.active_workspace()
    items = store.list_workspaces()
    for ws in items:
        if ws.get("id") == active_id:
            return ws
    return {"id": DEFAULT_WORKSPACE_ID, "name": DEFAULT_WORKSPACE_NAME}

@router.post("/switch", dependencies=[Depends(require_auth)])
def switch_workspace(req: WorkspaceRequest) -> dict[str, Any]:
    safe_id(req.workspace_id, "workspace_id")
    try:
        store.set_active_workspace(req.workspace_id)
        return {"status": "success", "workspace_id": req.workspace_id}
    except (ValueError, KeyError) as exc:
        raise error(str(exc), 404) from exc

@router.post("/create", dependencies=[Depends(require_auth)])
def create_workspace(req: WorkspaceCreateRequest) -> dict[str, Any]:
    try:
        ws = store.create_workspace(req.name.strip())
        return {"status": "success", "workspace": ws}
    except ValueError as exc:
        raise error(str(exc)) from exc

@router.post("/rename", dependencies=[Depends(require_auth)])
def rename_workspace(req: WorkspaceRenameRequest) -> dict[str, Any]:
    safe_id(req.workspace_id, "workspace_id")
    try:
        ws = store.rename_workspace(req.workspace_id, req.name.strip())
        return {"status": "success", "workspace": ws}
    except (ValueError, KeyError) as exc:
        raise error(str(exc), 404) from exc

@router.post("/delete", dependencies=[Depends(require_auth)])
def delete_workspace(req: WorkspaceDeleteRequest) -> dict[str, Any]:
    safe_id(req.workspace_id, "workspace_id")
    try:
        store.delete_workspace(req.workspace_id)
        return {"status": "success"}
    except (ValueError, KeyError) as exc:
        raise error(str(exc), 404) from exc
