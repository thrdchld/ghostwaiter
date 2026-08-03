from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field

class GenerateRequest(BaseModel):
    workspace_id: str
    prompt: str = Field(min_length=1)
    mode: Literal["chat", "write", "rewrite", "paraphrase"] = "write"

class TestConnectionRequest(BaseModel):
    provider: str
    key: str | None = None
    model: str | None = None
    custom_endpoint: str | None = None
    custom_api_type: str | None = None
