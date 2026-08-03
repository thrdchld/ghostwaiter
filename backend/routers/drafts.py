from __future__ import annotations
from typing import Any
from fastapi import APIRouter, Query, Depends
from backend.storage import store, new_id, now_iso
from backend.helpers import error, require_auth, workspace_id
from backend.schemas import (
    DraftCreateRequest,
    DraftUpdateRequest,
    DraftIdRequest,
)

router = APIRouter(prefix="/api/draft", tags=["draft"])

@router.post("/create", dependencies=[Depends(require_auth)])
def create_draft(req: DraftCreateRequest) -> dict[str, Any]:
    ws = workspace_id(req.workspace_id)
    draft_id = new_id("draft")
    timestamp = now_iso()
    draft = {
        "schema_version": 1,
        "id": draft_id,
        "title": req.title.strip() or "Untitled",
        "content": "",
        "collections": [],
        "tags": [],
        "created_at": timestamp,
        "updated_at": timestamp,
        "status": "active",
    }
    return store.save_entity(ws, "drafts", draft)

@router.post("/update", dependencies=[Depends(require_auth)])
def update_draft(req: DraftUpdateRequest) -> dict[str, Any]:
    ws = workspace_id(req.workspace_id)
    try:
        draft = store.get_entity(ws, "drafts", req.draft_id)
    except (FileNotFoundError, ValueError) as exc:
        raise error("Draft not found", 404) from exc
    changes = req.model_dump(exclude_none=True, exclude={"workspace_id", "draft_id"})
    draft.update(changes)
    draft["updated_at"] = now_iso()
    return store.save_entity(ws, "drafts", draft)

@router.get("/list", dependencies=[Depends(require_auth)])
def list_drafts(
    workspace_id_query: str | None = Query(default=None, alias="workspace_id"),
    query: str = "",
) -> dict[str, Any]:
    ws = workspace_id(workspace_id_query)
    drafts = store.list_entities(ws, "drafts")
    if query:
        needle = query.casefold()
        drafts = [item for item in drafts if needle in f"{item.get('title', '')} {item.get('content', '')}".casefold()]
    return {"items": drafts}

@router.get("/{draft_id}", dependencies=[Depends(require_auth)])
def get_draft(draft_id: str, workspace_id_query: str | None = Query(default=None, alias="workspace_id")) -> dict[str, Any]:
    try:
        return store.get_entity(workspace_id(workspace_id_query), "drafts", draft_id)
    except (FileNotFoundError, ValueError) as exc:
        raise error("Draft not found", 404) from exc

@router.post("/delete", dependencies=[Depends(require_auth)])
def delete_draft(req: DraftIdRequest) -> dict[str, str]:
    try:
        store.delete_entity(workspace_id(req.workspace_id), "drafts", req.draft_id)
    except (FileNotFoundError, ValueError) as exc:
        raise error("Draft not found", 404) from exc
    return {"status": "success"}
