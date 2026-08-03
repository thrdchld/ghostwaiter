from __future__ import annotations
from pydantic import BaseModel, Field

class DraftCreateRequest(BaseModel):
    workspace_id: str
    title: str = Field(default="Untitled")

class DraftUpdateRequest(BaseModel):
    workspace_id: str
    draft_id: str
    title: str | None = Field(default=None)
    content: str | None = Field(default=None)
    collections: list[str] | None = None
    tags: list[str] | None = None

class DraftIdRequest(BaseModel):
    workspace_id: str
    draft_id: str
