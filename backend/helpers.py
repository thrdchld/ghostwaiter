from __future__ import annotations
import hmac
import hashlib
import time
import secrets
from typing import Any
from fastapi import HTTPException, Request, Depends, Cookie, Header
from backend.config import settings
from backend.storage import store, safe_id
from backend.ai import ai_service

def error(message: str, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"status": "error", "message": message})

def _sign(value: str) -> str:
    return hmac.new(settings.session_secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()

def _valid_session(token: str | None) -> bool:
    if not settings.app_password:
        return True
    if not token:
        return False
    try:
        timestamp, nonce, signature = token.split(".", 2)
        value = f"{timestamp}.{nonce}"
        return (
            hmac.compare_digest(signature, _sign(value))
            and int(time.time()) - int(timestamp) < 60 * 60 * 24 * 30
        )
    except (ValueError, TypeError):
        return False

def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    return token if scheme.casefold() == "bearer" and token else None

def get_or_auth(request: Request) -> tuple[str, str, str]:
    return (
        request.headers.get("X-OpenRouter-Key", ""),
        request.headers.get("X-OpenRouter-Model", ""),
        request.headers.get("X-AI-Provider", "openrouter"),
    )

def require_auth(
    gw_session: str | None = Cookie(default=None),
    authorization: str | None = Header(default=None),
) -> None:
    if not _valid_session(gw_session) and not _valid_session(_bearer_token(authorization)):
        raise error("Authentication required", 401)

def workspace_id(value: str | None) -> str:
    selected = value or store.active_workspace()
    try:
        safe_id(selected, "workspace_id")
    except ValueError as exc:
        raise error(str(exc), 400) from exc
    return selected

def brain_system_prompt(workspace: str, purpose: str, context: str = "", model: str = "") -> str:
    base = (
        "You are Ghostwaiter, an intelligent personal digital assistant and brainstorming companion. "
        "Your goal is to help the user write, brainstorm, take notes, and assist with any digital tasks. "
        "You act as an all-in-one assistant for thinking, creating content, and executing digital workflows. "
        "You may respond in any language the user requests. "
        "Do not fabricate facts, do not execute system commands. "
        f"You are currently using AI model: {model}."
    )
    modes = {
        "chat": "Help the user think and discuss naturally and fluidly.",
        "write": "Write the final output directly without introductory pleasantries.",
        "rewrite": "Rewrite the text according to instructions without explaining the process.",
        "paraphrase": "Paraphrase the text while maintaining its original meaning.",
    }
    formatting = (
        "IMPORTANT: Do not use Markdown formatting symbols (like *, **, ***, ###, or ---) in your writing unless explicitly requested. "
        "Use plain text with proper paragraphs and indentation."
    )
    return f"{base}\n{modes.get(purpose, modes['write'])}\n{formatting}\n\n{context or ai_service.context(workspace)}".strip()
