from __future__ import annotations
from pydantic import BaseModel

class NoteSaveRequest(BaseModel):
    workspace_id: str
    id: str | None = None
    title: str = ""
    content: str = ""
    pinned: bool = False
    tags: list[str] = []
    image: str | None = None

class NoteIdRequest(BaseModel):
    workspace_id: str
    note_id: str

class NoteBulkDeleteRequest(BaseModel):
    workspace_id: str
    note_ids: list[str]
