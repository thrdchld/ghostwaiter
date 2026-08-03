from __future__ import annotations
from pydantic import BaseModel, Field

class ChatAttachment(BaseModel):
    name: str
    size: int
    type: str
    content: str  # Base64 data or text content

class ChatRequest(BaseModel):
    workspace_id: str
    message: str = Field(min_length=1)
    chat_id: str | None = None
    attachments: list[ChatAttachment] | None = None

class ChatIdRequest(BaseModel):
    workspace_id: str
    chat_id: str

class ChatRenameRequest(ChatIdRequest):
    title: str = Field(min_length=1)
