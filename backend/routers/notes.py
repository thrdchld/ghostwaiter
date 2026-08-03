from __future__ import annotations
from typing import Any
from fastapi import APIRouter, Query, Depends
from backend.storage import store, new_id, now_iso
from backend.helpers import error, require_auth, workspace_id
from backend.schemas import (
    NoteSaveRequest,
    NoteIdRequest,
    NoteBulkDeleteRequest,
)

router = APIRouter(prefix="/api/notes", tags=["notes"])

@router.post("/save", dependencies=[Depends(require_auth)])
def save_note(req: NoteSaveRequest) -> dict[str, Any]:
    ws = workspace_id(req.workspace_id)
    timestamp = now_iso()
    note_id = req.id
    
    if not note_id:
        note_id = new_id("note")
        note = {
            "schema_version": 1,
            "id": note_id,
            "title": req.title,
            "content": req.content,
            "pinned": req.pinned,
            "tags": req.tags,
            "image": req.image,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
    else:
        try:
            note = store.get_entity(ws, "notes", note_id)
        except (FileNotFoundError, ValueError):
            note = {
                "schema_version": 1,
                "id": note_id,
                "created_at": timestamp,
            }
        note.update({
            "title": req.title,
            "content": req.content,
            "pinned": req.pinned,
            "tags": req.tags,
            "image": req.image,
            "updated_at": timestamp,
        })
        
    return store.save_entity(ws, "notes", note)

@router.get("/list", dependencies=[Depends(require_auth)])
def list_notes(
    workspace_id_query: str | None = Query(default=None, alias="workspace_id"),
    query: str = "",
    tag: str = "",
) -> dict[str, Any]:
    ws = workspace_id(workspace_id_query)
    notes = store.list_entities(ws, "notes")
    
    if query:
        needle = query.casefold()
        notes = [n for n in notes if needle in f"{n.get('title', '')} {n.get('content', '')}".casefold()]
        
    if tag:
        tag_needle = tag.casefold()
        notes = [n for n in notes if any(t.casefold() == tag_needle for t in n.get("tags", []))]
        
    # Sort pinned first, then updated_at descending
    notes.sort(key=lambda n: (not n.get("pinned", False), n.get("updated_at", "")), reverse=True)
    return {"items": notes}

@router.post("/delete", dependencies=[Depends(require_auth)])
def delete_note(req: NoteIdRequest) -> dict[str, str]:
    try:
        store.delete_entity(workspace_id(req.workspace_id), "notes", req.note_id)
    except (FileNotFoundError, ValueError) as exc:
        raise error("Note not found", 404) from exc
    return {"status": "success"}

@router.post("/delete-bulk", dependencies=[Depends(require_auth)])
def delete_notes_bulk(req: NoteBulkDeleteRequest) -> dict[str, Any]:
    ws = workspace_id(req.workspace_id)
    deleted_count = 0
    for note_id in req.note_ids:
        try:
            store.delete_entity(ws, "notes", note_id)
            deleted_count += 1
        except (FileNotFoundError, ValueError):
            continue
    return {"status": "success", "count": deleted_count}
