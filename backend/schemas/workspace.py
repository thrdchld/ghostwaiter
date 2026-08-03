from __future__ import annotations
from pydantic import BaseModel, Field

class WorkspaceRequest(BaseModel):
    workspace_id: str

class WorkspaceCreateRequest(BaseModel):
    name: str = Field(min_length=1)

class WorkspaceRenameRequest(WorkspaceRequest):
    name: str = Field(min_length=1)

class WorkspaceDeleteRequest(WorkspaceRequest):
    pass
