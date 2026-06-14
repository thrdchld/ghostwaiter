from __future__ import annotations

import base64
import asyncio
import hashlib
import hmac
import io
import json
import secrets
import time
import zipfile
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import Cookie, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .ai import AIUnavailable, ai_service
from .config import ROOT_DIR, settings
from .storage import new_id, now_iso, safe_id, store


FRONTEND_DIR = ROOT_DIR / "frontend"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    async def autosync_loop() -> None:
        while True:
            await asyncio.sleep(settings.sync_debounce_seconds)
            queue = store.read_json(store.root / "queue" / "pending_sync.json")
            if queue.get("items") and settings.github_token and settings.github_repo:
                try:
                    await _github_sync()
                except Exception:
                    pass

    task = asyncio.create_task(autosync_loop())
    yield
    task.cancel()


app = FastAPI(title="GhostWriter", version="1.0.0", docs_url="/api/docs", lifespan=lifespan)


class LoginRequest(BaseModel):
    password: str


class WorkspaceRequest(BaseModel):
    workspace_id: str


class WorkspaceCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class ChatRequest(BaseModel):
    workspace_id: str
    message: str = Field(min_length=1, max_length=20000)
    chat_id: str | None = None


class ChatIdRequest(BaseModel):
    workspace_id: str
    chat_id: str


class DraftCreateRequest(BaseModel):
    workspace_id: str
    title: str = Field(default="Untitled", max_length=160)


class DraftUpdateRequest(BaseModel):
    workspace_id: str
    draft_id: str
    title: str | None = Field(default=None, max_length=160)
    content: str | None = Field(default=None, max_length=500000)
    collections: list[str] | None = None
    tags: list[str] | None = None


class DraftIdRequest(BaseModel):
    workspace_id: str
    draft_id: str


class GenerateRequest(BaseModel):
    workspace_id: str
    prompt: str = Field(min_length=1, max_length=30000)
    mode: Literal["chat", "write", "rewrite", "paraphrase"] = "write"


class RevisionRequest(BaseModel):
    workspace_id: str
    ai_output: str = Field(min_length=1, max_length=100000)
    user_revision: str = Field(min_length=1, max_length=100000)


class RawWritingRequest(BaseModel):
    workspace_id: str
    content: str = Field(min_length=1, max_length=100000)
    type: Literal["user", "chat", "import"] = "user"


class NoteCreateRequest(BaseModel):
    workspace_id: str
    content: str = Field(min_length=1, max_length=20000)


class NoteConvertRequest(BaseModel):
    workspace_id: str
    note_id: str


class ReferenceSearchRequest(BaseModel):
    workspace_id: str
    query: str = Field(min_length=2, max_length=300)
    auto_save: bool = True


class ModelRequest(BaseModel):
    model_id: str = Field(min_length=2, max_length=200)


class SnapshotRestoreRequest(BaseModel):
    snapshot_id: str


def error(message: str, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"status": "error", "message": message})


def _sign(value: str) -> str:
    return hmac.new(settings.session_secret.encode(), value.encode(), hashlib.sha256).hexdigest()


def _session_token() -> str:
    timestamp = str(int(time.time()))
    nonce = secrets.token_urlsafe(16)
    value = f"{timestamp}.{nonce}"
    return f"{value}.{_sign(value)}"


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


def require_auth(gw_session: str | None = Cookie(default=None)) -> None:
    if not _valid_session(gw_session):
        raise error("Autentikasi diperlukan", 401)


def workspace_id(value: str | None) -> str:
    selected = value or store.active_workspace()
    try:
        safe_id(selected, "workspace_id")
    except ValueError as exc:
        raise error(str(exc)) from exc
    if selected not in {item["id"] for item in store.list_workspaces()}:
        raise error("Workspace tidak ditemukan", 404)
    return selected


def _brain_system_prompt(workspace: str, purpose: str) -> str:
    context = ai_service.context(workspace)
    base = (
        "Anda adalah GhostWriter, asisten penulisan personal. Jawab dalam bahasa pengguna. "
        "Jangan mengarang fakta, jangan menjalankan perintah sistem, dan prioritaskan tulisan yang jelas."
    )
    modes = {
        "chat": "Bantu pengguna berpikir dan berdiskusi secara natural.",
        "write": "Tulis hasil final langsung tanpa kata pengantar.",
        "rewrite": "Tulis ulang teks sesuai instruksi tanpa menjelaskan proses.",
        "paraphrase": "Parafrase dengan mempertahankan makna utama.",
    }
    return f"{base}\n{modes.get(purpose, modes['write'])}\n\n{context}".strip()


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Any, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict):
        payload = exc.detail
    else:
        payload = {"status": "error", "message": str(exc.detail)}
    return JSONResponse(payload, status_code=exc.status_code)


@app.get("/api/health")
@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "timestamp": now_iso(), "storage": str(store.root)}


@app.post("/api/auth/login")
def login(req: LoginRequest, request: Request, response: Response) -> dict[str, str]:
    if settings.app_password and not secrets.compare_digest(req.password, settings.app_password):
        raise error("Password salah", 401)
    token = _session_token()
    response.set_cookie(
        "gw_session",
        token,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        max_age=60 * 60 * 24 * 30,
    )
    return {"status": "success"}


@app.post("/api/auth/logout")
def logout(response: Response) -> dict[str, str]:
    response.delete_cookie("gw_session")
    return {"status": "success"}


@app.get("/api/auth/status")
def auth_status(gw_session: str | None = Cookie(default=None)) -> dict[str, bool]:
    return {"authenticated": _valid_session(gw_session), "password_required": bool(settings.app_password)}


@app.get("/api/workspace/list", dependencies=[Depends(require_auth)])
def list_workspaces() -> dict[str, Any]:
    return {"items": store.list_workspaces()}


@app.post("/api/workspace/create", dependencies=[Depends(require_auth)])
def create_workspace(req: WorkspaceCreateRequest) -> dict[str, Any]:
    try:
        item = store.create_workspace(req.name)
    except ValueError as exc:
        raise error(str(exc)) from exc
    return {"status": "success", "workspace": item}


@app.post("/api/workspace/switch", dependencies=[Depends(require_auth)])
def switch_workspace(req: WorkspaceRequest) -> dict[str, str]:
    try:
        store.set_active_workspace(req.workspace_id)
    except (ValueError, KeyError) as exc:
        raise error(str(exc), 404) from exc
    return {"status": "success", "workspace_id": req.workspace_id}


@app.get("/api/workspace/current", dependencies=[Depends(require_auth)])
def current_workspace() -> dict[str, Any]:
    active = store.active_workspace()
    return next(item for item in store.list_workspaces() if item["id"] == active)


@app.post("/api/chat/new", dependencies=[Depends(require_auth)])
def new_chat(req: WorkspaceRequest) -> dict[str, str]:
    workspace = workspace_id(req.workspace_id)
    chat_id = new_id("chat")
    timestamp = now_iso()
    store.save_entity(
        workspace,
        "chats",
        {
            "schema_version": 1,
            "id": chat_id,
            "title": "Obrolan baru",
            "messages": [],
            "created_at": timestamp,
            "updated_at": timestamp,
            "archived": False,
        },
    )
    return {"chat_id": chat_id}


@app.get("/api/chat/list", dependencies=[Depends(require_auth)])
def list_chats(workspace_id_query: str | None = Query(default=None, alias="workspace_id")) -> dict[str, Any]:
    workspace = workspace_id(workspace_id_query)
    return {"items": store.list_entities(workspace, "chats")}


@app.get("/api/chat/session/{chat_id}", dependencies=[Depends(require_auth)])
def get_chat(chat_id: str, workspace_id_query: str | None = Query(default=None, alias="workspace_id")) -> dict[str, Any]:
    try:
        return store.get_entity(workspace_id(workspace_id_query), "chats", chat_id)
    except (FileNotFoundError, ValueError) as exc:
        raise error("Chat tidak ditemukan", 404) from exc


@app.post("/api/chat/archive", dependencies=[Depends(require_auth)])
def archive_chat(req: ChatIdRequest) -> dict[str, str]:
    try:
        chat = store.get_entity(workspace_id(req.workspace_id), "chats", req.chat_id)
    except (FileNotFoundError, ValueError) as exc:
        raise error("Chat tidak ditemukan", 404) from exc
    chat["archived"] = True
    chat["updated_at"] = now_iso()
    store.save_entity(req.workspace_id, "chats", chat)
    return {"status": "success"}


async def _chat_stream(workspace: str, chat: dict[str, Any], user_message: str):
    chat["messages"].append({"role": "user", "content": user_message, "timestamp": now_iso()})
    messages = [{"role": "system", "content": _brain_system_prompt(workspace, "chat")}]
    messages.extend(
        {"role": item["role"], "content": item["content"]}
        for item in chat["messages"][-20:]
        if item["role"] in {"user", "assistant"}
    )
    chunks: list[str] = []
    try:
        async for text in ai_service.stream(messages):
            chunks.append(text)
            yield text
    except AIUnavailable as exc:
        yield f"\n\n[Error: {exc}]"
    finally:
        answer = "".join(chunks).strip()
        if answer:
            chat["messages"].append({"role": "assistant", "content": answer, "timestamp": now_iso()})
        chat["updated_at"] = now_iso()
        if chat["title"] == "Obrolan baru":
            chat["title"] = user_message[:60]
        store.save_entity(workspace, "chats", chat)


@app.post("/api/chat/send", dependencies=[Depends(require_auth)])
def send_chat(req: ChatRequest) -> StreamingResponse:
    workspace = workspace_id(req.workspace_id)
    if req.chat_id:
        try:
            chat = store.get_entity(workspace, "chats", req.chat_id)
        except (FileNotFoundError, ValueError) as exc:
            raise error("Chat tidak ditemukan", 404) from exc
    else:
        chat_id = new_id("chat")
        timestamp = now_iso()
        chat = {
            "schema_version": 1,
            "id": chat_id,
            "title": "Obrolan baru",
            "messages": [],
            "created_at": timestamp,
            "updated_at": timestamp,
            "archived": False,
        }
    return StreamingResponse(
        _chat_stream(workspace, chat, req.message),
        media_type="text/plain; charset=utf-8",
        headers={"X-Chat-Id": chat["id"], "Cache-Control": "no-cache"},
    )


@app.post("/api/draft/create", dependencies=[Depends(require_auth)])
def create_draft(req: DraftCreateRequest) -> dict[str, Any]:
    workspace = workspace_id(req.workspace_id)
    timestamp = now_iso()
    draft = {
        "schema_version": 1,
        "id": new_id("draft"),
        "title": req.title.strip() or "Untitled",
        "content": "",
        "collections": [],
        "tags": [],
        "created_at": timestamp,
        "updated_at": timestamp,
        "status": "active",
    }
    return store.save_entity(workspace, "drafts", draft)


@app.post("/api/draft/update", dependencies=[Depends(require_auth)])
def update_draft(req: DraftUpdateRequest) -> dict[str, Any]:
    workspace = workspace_id(req.workspace_id)
    try:
        draft = store.get_entity(workspace, "drafts", req.draft_id)
    except (FileNotFoundError, ValueError) as exc:
        raise error("Draft tidak ditemukan", 404) from exc
    changes = req.model_dump(exclude_none=True, exclude={"workspace_id", "draft_id"})
    draft.update(changes)
    draft["updated_at"] = now_iso()
    return store.save_entity(workspace, "drafts", draft)


@app.get("/api/draft/list", dependencies=[Depends(require_auth)])
def list_drafts(
    workspace_id_query: str | None = Query(default=None, alias="workspace_id"),
    query: str = "",
) -> dict[str, Any]:
    drafts = store.list_entities(workspace_id(workspace_id_query), "drafts")
    if query:
        needle = query.casefold()
        drafts = [item for item in drafts if needle in f"{item.get('title', '')} {item.get('content', '')}".casefold()]
    return {"items": drafts}


@app.get("/api/draft/{draft_id}", dependencies=[Depends(require_auth)])
def get_draft(draft_id: str, workspace_id_query: str | None = Query(default=None, alias="workspace_id")) -> dict[str, Any]:
    try:
        return store.get_entity(workspace_id(workspace_id_query), "drafts", draft_id)
    except (FileNotFoundError, ValueError) as exc:
        raise error("Draft tidak ditemukan", 404) from exc


@app.post("/api/draft/delete", dependencies=[Depends(require_auth)])
def delete_draft(req: DraftIdRequest) -> dict[str, str]:
    try:
        store.delete_entity(workspace_id(req.workspace_id), "drafts", req.draft_id)
    except (FileNotFoundError, ValueError) as exc:
        raise error("Draft tidak ditemukan", 404) from exc
    return {"status": "success"}


async def _generate_stream(workspace: str, prompt: str, mode: str):
    messages = [
        {"role": "system", "content": _brain_system_prompt(workspace, mode)},
        {"role": "user", "content": prompt},
    ]
    try:
        async for text in ai_service.stream(messages):
            yield text
    except AIUnavailable as exc:
        yield f"[Error: {exc}]"


@app.post("/api/ai/generate", dependencies=[Depends(require_auth)])
def generate(req: GenerateRequest) -> StreamingResponse:
    workspace = workspace_id(req.workspace_id)
    return StreamingResponse(
        _generate_stream(workspace, req.prompt, req.mode),
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "no-cache"},
    )


@app.post("/api/brain/learn/revision", dependencies=[Depends(require_auth)])
async def learn_revision(req: RevisionRequest) -> dict[str, Any]:
    workspace = workspace_id(req.workspace_id)
    try:
        analysis = await ai_service.learn_revision(req.ai_output, req.user_revision)
    except AIUnavailable as exc:
        raise error(str(exc), 503) from exc
    timestamp = now_iso()
    store.save_entity(
        workspace,
        "learning/revision_pairs",
        {
            "schema_version": 1,
            "id": new_id("rev"),
            "ai_output": req.ai_output,
            "user_revision": req.user_revision,
            "analysis": analysis,
            "created_at": timestamp,
        },
    )
    brain = store.workspace_path(workspace) / "brain"
    style = store.read_json(brain / "style_profile.json")
    thinking = store.read_json(brain / "thinking_profile.json")
    style["rules"] = list(dict.fromkeys(style.get("rules", []) + analysis["style_rules"]))[-100:]
    thinking["patterns"] = list(dict.fromkeys(thinking.get("patterns", []) + analysis["thinking_patterns"]))[-100:]
    store.write_json(brain / "style_profile.json", style)
    store.write_json(brain / "thinking_profile.json", thinking)
    store.enqueue_sync("brain", workspace, analysis)
    return {"status": "learned", "analysis": analysis}


@app.post("/api/brain/learn/raw-writing", dependencies=[Depends(require_auth)])
async def learn_raw(req: RawWritingRequest) -> dict[str, Any]:
    workspace = workspace_id(req.workspace_id)
    prompt = (
        "Analisis gaya tulisan berikut. Balas satu aturan gaya yang konkret, singkat, "
        "dan dapat diterapkan kembali. Jangan merangkum isi."
    )
    try:
        rule = (
            await ai_service.complete(
                [{"role": "system", "content": prompt}, {"role": "user", "content": req.content}],
                max_tokens=160,
                temperature=0.2,
            )
        ).strip()
    except AIUnavailable as exc:
        raise error(str(exc), 503) from exc
    item = {
        "schema_version": 1,
        "id": new_id("raw"),
        "content": req.content,
        "type": req.type,
        "analysis": rule,
        "created_at": now_iso(),
    }
    store.save_entity(workspace, "learning/raw_writing", item)
    profile_path = store.workspace_path(workspace) / "brain" / "style_profile.json"
    profile = store.read_json(profile_path)
    profile["rules"] = list(dict.fromkeys(profile.get("rules", []) + [rule]))[-100:]
    store.write_json(profile_path, profile)
    return {"status": "learned", "rule": rule}


@app.get("/api/brain/profile", dependencies=[Depends(require_auth)])
def brain_profile(workspace_id_query: str | None = Query(default=None, alias="workspace_id")) -> dict[str, Any]:
    workspace = workspace_id(workspace_id_query)
    brain = store.workspace_path(workspace) / "brain"
    return {
        "style_profile": store.read_json(brain / "style_profile.json"),
        "thinking_profile": store.read_json(brain / "thinking_profile.json"),
        "rules": store.read_json(brain / "rules.json").get("items", []),
        "memory": store.read_json(brain / "memory.json").get("items", []),
        "revision_count": len(store.list_entities(workspace, "learning/revision_pairs")),
        "raw_writing_count": len(store.list_entities(workspace, "learning/raw_writing")),
    }


@app.post("/api/note/create", dependencies=[Depends(require_auth)])
def create_note(req: NoteCreateRequest) -> dict[str, Any]:
    workspace = workspace_id(req.workspace_id)
    path = store.workspace_path(workspace) / "quick_notes.json"
    data = store.read_json(path)
    note = {
        "id": new_id("note"),
        "content": req.content,
        "converted_to_draft": False,
        "created_at": now_iso(),
    }
    data["items"].insert(0, note)
    store.write_json(path, data)
    store.enqueue_sync("note", workspace, note)
    return note


@app.get("/api/note/list", dependencies=[Depends(require_auth)])
def list_notes(workspace_id_query: str | None = Query(default=None, alias="workspace_id")) -> dict[str, Any]:
    workspace = workspace_id(workspace_id_query)
    return store.read_json(store.workspace_path(workspace) / "quick_notes.json")


@app.post("/api/note/convert-to-draft", dependencies=[Depends(require_auth)])
def convert_note(req: NoteConvertRequest) -> dict[str, Any]:
    workspace = workspace_id(req.workspace_id)
    path = store.workspace_path(workspace) / "quick_notes.json"
    notes = store.read_json(path)
    note = next((item for item in notes["items"] if item["id"] == req.note_id), None)
    if not note:
        raise error("Catatan tidak ditemukan", 404)
    timestamp = now_iso()
    draft = store.save_entity(
        workspace,
        "drafts",
        {
            "schema_version": 1,
            "id": new_id("draft"),
            "title": note["content"][:60] or "Quick note",
            "content": note["content"],
            "collections": [],
            "tags": [],
            "created_at": timestamp,
            "updated_at": timestamp,
            "status": "active",
        },
    )
    note["converted_to_draft"] = True
    store.write_json(path, notes)
    return draft


@app.post("/api/reference/search", dependencies=[Depends(require_auth)])
async def search_references(req: ReferenceSearchRequest) -> dict[str, Any]:
    workspace = workspace_id(req.workspace_id)
    if not settings.tavily_api_key:
        raise error("TAVILY_API_KEY belum dikonfigurasi untuk pencarian web", 503)
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "https://api.tavily.com/search",
            json={
                "api_key": settings.tavily_api_key,
                "query": req.query,
                "search_depth": "basic",
                "max_results": 5,
            },
        )
        response.raise_for_status()
        results = response.json().get("results", [])
    items = []
    for result in results:
        item = {
            "schema_version": 1,
            "id": new_id("ref"),
            "title": result.get("title", "Reference"),
            "source": "web",
            "url": result.get("url", ""),
            "summary": result.get("content", ""),
            "tags": [req.query],
            "created_at": now_iso(),
        }
        if req.auto_save:
            store.save_entity(workspace, "references", item)
        items.append(item)
    return {"items": items}


@app.get("/api/reference/list", dependencies=[Depends(require_auth)])
def list_references(workspace_id_query: str | None = Query(default=None, alias="workspace_id")) -> dict[str, Any]:
    return {"items": store.list_entities(workspace_id(workspace_id_query), "references")}


@app.get("/api/reference/{reference_id}", dependencies=[Depends(require_auth)])
def get_reference(
    reference_id: str,
    workspace_id_query: str | None = Query(default=None, alias="workspace_id"),
) -> dict[str, Any]:
    try:
        return store.get_entity(workspace_id(workspace_id_query), "references", reference_id)
    except (FileNotFoundError, ValueError) as exc:
        raise error("Referensi tidak ditemukan", 404) from exc


@app.get("/api/model/status", dependencies=[Depends(require_auth)])
def model_status() -> dict[str, Any]:
    return {
        "active_model": ai_service.active_model,
        "fallback_chain": list(ai_service.models),
        "configured": bool(settings.hf_token),
        "provider": settings.inference_provider,
        "last_error": ai_service.last_error,
    }


@app.post("/api/model/set-default", dependencies=[Depends(require_auth)])
def set_default_model(req: ModelRequest) -> dict[str, str]:
    path = store.root / "system" / "models.json"
    data = store.read_json(path)
    data["default_model"] = req.model_id
    store.write_json(path, data)
    ai_service.active_model = req.model_id
    return {"status": "success", "model_id": req.model_id}


@app.get("/api/model/search", dependencies=[Depends(require_auth)])
async def search_models(query: str = Query(min_length=2, max_length=100)) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            "https://huggingface.co/api/models",
            params={"search": query, "pipeline_tag": "text-generation", "sort": "downloads", "direction": -1, "limit": 20},
        )
        response.raise_for_status()
    return {
        "items": [
            {
                "id": item.get("id"),
                "downloads": item.get("downloads", 0),
                "likes": item.get("likes", 0),
                "private": item.get("private", False),
            }
            for item in response.json()
        ]
    }


def _backup_payload() -> dict[str, Any]:
    payload: dict[str, Any] = {"schema_version": 1, "created_at": now_iso(), "files": {}}
    for path in store.root.rglob("*.json"):
        if ".git" not in path.parts:
            payload["files"][str(path.relative_to(store.root))] = store.read_json(path)
    return payload


async def _github_sync() -> tuple[bool, str]:
    if not settings.github_token or not settings.github_repo:
        return False, "GITHUB_TOKEN atau GITHUB_BACKUP_REPO belum dikonfigurasi"
    owner_repo = settings.github_repo.removeprefix("https://github.com/").removesuffix(".git").strip("/")
    if owner_repo.count("/") != 1:
        return False, "Format GITHUB_BACKUP_REPO harus owner/repo"
    api_url = f"https://api.github.com/repos/{owner_repo}/contents/ghostwriter-backup.json"
    headers = {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    content = base64.b64encode(json.dumps(_backup_payload(), ensure_ascii=False).encode()).decode()
    async with httpx.AsyncClient(timeout=60, headers=headers) as client:
        current = await client.get(api_url)
        body: dict[str, Any] = {
            "message": f"GhostWriter sync {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}",
            "content": content,
        }
        if current.status_code == 200:
            body["sha"] = current.json()["sha"]
        elif current.status_code != 404:
            return False, f"GitHub API: {current.status_code} {current.text[:200]}"
        result = await client.put(api_url, json=body)
        if result.status_code not in {200, 201}:
            return False, f"GitHub API: {result.status_code} {result.text[:200]}"
    queue_path = store.root / "queue" / "pending_sync.json"
    store.write_json(queue_path, {"schema_version": 1, "items": []})
    system_path = store.root / "system" / "settings.json"
    system = store.read_json(system_path)
    system.update({"sync_status": "ok", "last_sync": now_iso()})
    store.write_json(system_path, system)
    return True, ""


@app.post("/api/sync/run", dependencies=[Depends(require_auth)])
async def run_sync() -> dict[str, Any]:
    ok, message = await _github_sync()
    if not ok:
        raise error(message, 503)
    return {"status": "success", "last_sync": now_iso()}


@app.get("/api/sync/status", dependencies=[Depends(require_auth)])
def sync_status() -> dict[str, Any]:
    system = store.read_json(store.root / "system" / "settings.json")
    queue = store.read_json(store.root / "queue" / "pending_sync.json")
    return {
        "status": system.get("sync_status", "idle"),
        "queue_size": len(queue.get("items", [])),
        "last_sync": system.get("last_sync", ""),
        "configured": bool(settings.github_token and settings.github_repo),
    }


@app.get("/api/sync/queue", dependencies=[Depends(require_auth)])
def sync_queue() -> dict[str, Any]:
    return store.read_json(store.root / "queue" / "pending_sync.json")


@app.post("/api/sync/retry", dependencies=[Depends(require_auth)])
async def retry_sync() -> dict[str, Any]:
    return await run_sync()


@app.post("/api/snapshot/create", dependencies=[Depends(require_auth)])
def create_snapshot() -> dict[str, Any]:
    return store.create_snapshot()


@app.get("/api/snapshot/list", dependencies=[Depends(require_auth)])
def list_snapshots() -> dict[str, Any]:
    return store.read_json(store.root / "snapshots" / "manifest.json")


@app.get("/api/snapshot/download/{snapshot_id}", dependencies=[Depends(require_auth)])
def download_snapshot(snapshot_id: str) -> FileResponse:
    try:
        path = store.snapshot_path(snapshot_id)
    except FileNotFoundError as exc:
        raise error("Snapshot tidak ditemukan", 404) from exc
    return FileResponse(path, media_type="application/zip", filename=path.name)


@app.post("/api/snapshot/restore", dependencies=[Depends(require_auth)])
def restore_snapshot(req: SnapshotRestoreRequest) -> dict[str, str]:
    try:
        path = store.snapshot_path(req.snapshot_id)
    except FileNotFoundError as exc:
        raise error("Snapshot tidak ditemukan", 404) from exc
    store.create_snapshot()
    with zipfile.ZipFile(path) as archive:
        root = store.root.resolve()
        for member in archive.infolist():
            target = (root / member.filename).resolve()
            if root not in target.parents and target != root:
                raise error("Snapshot mengandung path yang tidak aman")
        archive.extractall(store.root)
    return {"status": "success"}


@app.get("/api/export", dependencies=[Depends(require_auth)])
def export_data() -> StreamingResponse:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in store.root.rglob("*.json"):
            archive.write(path, path.relative_to(store.root))
    buffer.seek(0)
    filename = f"ghostwriter_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.zip"
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/offline/cache/status")
def offline_status() -> dict[str, Any]:
    return {"status": "available", "strategy": "service-worker-shell-and-local-draft"}


app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")


@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/service-worker.js", include_in_schema=False)
def service_worker() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "service-worker.js", media_type="application/javascript")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")
