from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field
from .workspace import WorkspaceRequest

class BrainItemUpdateRequest(WorkspaceRequest):
    type: Literal["style", "thinking", "memory"]
    id_or_content: str
    new_content: str = Field(min_length=1)

class BrainItemDeleteRequest(WorkspaceRequest):
    type: Literal["style", "thinking", "memory"]
    id_or_content: str

class ProposalBulkRequest(WorkspaceRequest):
    action: Literal["approve", "reject"]
    proposal_ids: list[str]

class LearningProposalRequest(BaseModel):
    workspace_id: str
    proposal_id: str
    content: str | None = Field(default=None, min_length=1)

class RevisionRequest(BaseModel):
    workspace_id: str
    ai_output: str = Field(min_length=1)
    user_revision: str = Field(min_length=1)

class CommitRevisionRequest(BaseModel):
    workspace_id: str
    revised_text: str = Field(min_length=1)
    learning_notes: str = Field(default="")

class RawWritingRequest(BaseModel):
    workspace_id: str
    text: str = Field(min_length=1)
    context: str = Field(default="")
