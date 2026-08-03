from __future__ import annotations
import secrets
import hmac
import time
from typing import Any
from fastapi import APIRouter, Cookie, Header, Response, HTTPException
from backend.config import settings
from backend.schemas import LoginRequest

router = APIRouter(prefix="/api/auth", tags=["auth"])

def _sign(value: str) -> str:
    return hmac.new(settings.session_secret.encode("utf-8"), value.encode("utf-8"), "sha256").hexdigest()

def _session_token() -> str:
    timestamp = str(int(time.time()))
    nonce = secrets.token_urlsafe(16)
    value = f"{timestamp}.{nonce}"
    return f"{value}.{_sign(value)}"

def valid_session(token: str | None) -> bool:
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

def bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    return token if scheme.casefold() == "bearer" and token else None

@router.get("/status")
def auth_status(
    gw_session: str | None = Cookie(default=None),
    authorization: str | None = Header(default=None),
) -> dict[str, bool]:
    return {
        "authenticated": valid_session(gw_session) or valid_session(bearer_token(authorization)),
        "password_required": bool(settings.app_password),
    }

@router.post("/login")
def login(req: LoginRequest, response: Response) -> dict[str, Any]:
    if settings.app_password and not secrets.compare_digest(req.password, settings.app_password):
        raise HTTPException(status_code=401, detail="Password salah")
    token = _session_token()
    response.set_cookie(
        key="gw_session",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 30,
    )
    return {"status": "success", "session_token": token}

@router.post("/logout")
def logout(response: Response) -> dict[str, str]:
    response.delete_cookie("gw_session")
    return {"status": "success"}
