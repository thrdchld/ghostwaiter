from __future__ import annotations
import asyncio
from typing import Any
from fastapi import APIRouter, Query, Depends, HTTPException
from fastapi.responses import StreamingResponse
from backend.storage import store, new_id, now_iso
from backend.ai import ai_service, AIUnavailable
from backend.context import build_chat_context
from backend.helpers import error, require_auth, get_or_auth, workspace_id, brain_system_prompt
from backend.schemas import (
    WorkspaceRequest,
    ChatRequest,
    ChatIdRequest,
    ChatRenameRequest,
    ChatAttachment,
)

router = APIRouter(prefix="/api/chat", tags=["chat"])

async def _analyze_chat_background(workspace: str, chat_id: str, api_key: str, model: str, provider: str = "openrouter") -> None:
    try:
        chat = store.get_entity(workspace, "chats", chat_id)
        analysis = await ai_service.analyze_chat(api_key, model, chat.get("messages", []), chat.get("summary", ""), provider=provider)
        chat["summary"] = analysis["summary"]
        chat["updated_at"] = now_iso()
        store.save_entity(workspace, "chats", chat)

        root = store.workspace_path(workspace)
        memory_path = root / "brain" / "conversation_memory.json"
        memory = store.read_json(memory_path)
        known_concepts = {
            (item.get("content", "") if isinstance(item, dict) else str(item)).casefold()
            for item in memory.get("items", [])
        }
        for concept in analysis["concepts"]:
            if concept.casefold() not in known_concepts:
                memory["items"].append(
                    {
                        "id": new_id("concept"),
                        "content": concept,
                        "source_chat_id": chat_id,
                        "created_at": now_iso(),
                    }
                )
        memory["items"] = memory["items"][-200:]
        store.write_json(memory_path, memory)

        proposal_path = root / "brain" / "learning_proposals.json"
        proposals = store.read_json(proposal_path)
        existing = {
            (item.get("type"), item.get("content", "").casefold())
            for item in proposals.get("items", [])
            if isinstance(item, dict) and item.get("status", "pending") != "rejected"
        }
        for item in analysis["proposals"]:
            key = (item["type"], item["content"].casefold())
            if key not in existing:
                proposals["items"].insert(
                    0,
                    {
                        "id": new_id("learn"),
                        "type": item["type"],
                        "content": item["content"],
                        "source_chat_id": chat_id,
                        "status": "pending",
                        "created_at": now_iso(),
                        "updated_at": now_iso(),
                    },
                )
        proposals["items"] = proposals["items"][:200]
        store.write_json(proposal_path, proposals)

        summary_path = root / "summary" / "workspace_summary.json"
        workspace_summary = store.read_json(summary_path)
        summaries = [
            item.get("summary", "")
            for item in store.list_entities(workspace, "chats")[:12]
            if item.get("summary") and not item.get("archived")
        ]
        workspace_summary["content"] = "\n".join(f"- {item}" for item in summaries)
        workspace_summary["updated_at"] = now_iso()
        store.write_json(summary_path, workspace_summary)
        store.enqueue_sync("brain", workspace, {"chat_id": chat_id, "analysis": "updated"})
    except Exception:
        return

async def _chat_stream(workspace: str, chat: dict[str, Any], user_message: str, api_key: str, model: str, provider: str = "openrouter", attachments: list[ChatAttachment] | None = None):
    user_msg_obj = {"role": "user", "content": user_message, "timestamp": now_iso()}
    if attachments:
        user_msg_obj["attachments"] = [
            {
                "name": att.name,
                "size": att.size,
                "type": att.type,
                "content": att.content
            }
            for att in attachments
        ]
    chat["messages"].append(user_msg_obj)
    
    app_context, accessed_workspaces = build_chat_context(workspace, user_message)
    chat["accessed_workspaces"] = accessed_workspaces
    messages = [{"role": "system", "content": brain_system_prompt(workspace, "chat", app_context, model)}]
    if chat.get("summary"):
        messages.append(
            {"role": "system", "content": f"Previous conversation summary:\n{chat['summary']}"}
        )
    
    for item in chat["messages"][-14:]:
        if item.get("role") not in {"user", "assistant"}:
            continue
        
        role = item["role"]
        content = item["content"]
        
        item_attachments = item.get("attachments", [])
        if item_attachments:
            content_list = [{"type": "text", "text": content}]
            for att in item_attachments:
                if att.get("type", "").startswith("image/"):
                    img_type = att.get("type", "image/jpeg")
                    img_data = att.get("content", "")
                    if not img_data.startswith("data:"):
                        img_data = f"data:{img_type};base64,{img_data}"
                    content_list.append({
                        "type": "image_url",
                        "image_url": {"url": img_data}
                    })
                else:
                    file_name = att.get("name", "file")
                    file_content = att.get("content", "")
                    content_list[0]["text"] += f"\n\n[Attached File: {file_name}]\n---\n{file_content}\n---"
            messages.append({"role": role, "content": content_list})
        else:
            messages.append({"role": role, "content": content})
            
    chunks: list[str] = []
    try:
        async for text in ai_service.stream(api_key, model, messages, provider=provider):
            chunks.append(text)
            yield text
    except AIUnavailable as exc:
        yield f"\n\n[Error: {exc}]"
    finally:
        answer = "".join(chunks).strip()
        if answer:
            chat["messages"].append({"role": "assistant", "content": answer, "timestamp": now_iso()})
        chat["updated_at"] = now_iso()
        if chat["title"] == "New Chat":
            chat["title"] = user_message[:60]
        store.save_entity(workspace, "chats", chat)
        if answer:
            asyncio.create_task(_analyze_chat_background(workspace, chat["id"], api_key, model, provider))

@router.post("/new", dependencies=[Depends(require_auth)])
def new_chat(req: WorkspaceRequest) -> dict[str, str]:
    ws = workspace_id(req.workspace_id)
    chat_id = new_id("chat")
    timestamp = now_iso()
    store.save_entity(
        ws,
        "chats",
        {
            "schema_version": 1,
            "id": chat_id,
            "title": "New Chat",
            "messages": [],
            "created_at": timestamp,
            "updated_at": timestamp,
            "archived": False,
            "summary": "",
            "accessed_workspaces": [],
        },
    )
    return {"chat_id": chat_id}

@router.get("/list", dependencies=[Depends(require_auth)])
def list_chats(
    workspace_id_query: str | None = Query(default=None, alias="workspace_id"),
    archived: bool | None = Query(default=None),
) -> dict[str, Any]:
    ws = workspace_id(workspace_id_query)
    items = store.list_entities(ws, "chats")
    if archived is not None:
        items = [item for item in items if bool(item.get("archived")) is archived]
    return {"items": items}

@router.get("/session/{chat_id}", dependencies=[Depends(require_auth)])
def get_chat(chat_id: str, workspace_id_query: str | None = Query(default=None, alias="workspace_id")) -> dict[str, Any]:
    try:
        return store.get_entity(workspace_id(workspace_id_query), "chats", chat_id)
    except (FileNotFoundError, ValueError) as exc:
        raise error("Chat not found", 404) from exc

@router.post("/archive", dependencies=[Depends(require_auth)])
def archive_chat(req: ChatIdRequest) -> dict[str, str]:
    try:
        chat = store.get_entity(workspace_id(req.workspace_id), "chats", req.chat_id)
    except (FileNotFoundError, ValueError) as exc:
        raise error("Chat not found", 404) from exc
    chat["archived"] = True
    chat["updated_at"] = now_iso()
    store.save_entity(req.workspace_id, "chats", chat)
    return {"status": "success"}

@router.post("/restore", dependencies=[Depends(require_auth)])
def restore_chat(req: ChatIdRequest) -> dict[str, str]:
    try:
        chat = store.get_entity(workspace_id(req.workspace_id), "chats", req.chat_id)
    except (FileNotFoundError, ValueError) as exc:
        raise error("Chat not found", 404) from exc
    chat["archived"] = False
    chat["updated_at"] = now_iso()
    store.save_entity(req.workspace_id, "chats", chat)
    return {"status": "success"}

@router.post("/rename", dependencies=[Depends(require_auth)])
def rename_chat(req: ChatRenameRequest) -> dict[str, str]:
    try:
        chat = store.get_entity(workspace_id(req.workspace_id), "chats", req.chat_id)
    except (FileNotFoundError, ValueError) as exc:
        raise error("Chat not found", 404) from exc
    chat["title"] = " ".join(req.title.split())
    chat["updated_at"] = now_iso()
    store.save_entity(req.workspace_id, "chats", chat)
    return {"status": "success", "title": chat["title"]}

@router.post("/delete-permanent", dependencies=[Depends(require_auth)])
def permanently_delete_chat(req: ChatIdRequest) -> dict[str, str]:
    try:
        chat = store.get_entity(workspace_id(req.workspace_id), "chats", req.chat_id)
        if not chat.get("archived"):
            raise error("Chat must be archived before permanent deletion")
        store.permanently_delete_entity(req.workspace_id, "chats", req.chat_id)
    except HTTPException:
        raise
    except (FileNotFoundError, ValueError) as exc:
        raise error("Chat not found", 404) from exc
    return {"status": "success"}

@router.post("/send", dependencies=[Depends(require_auth)])
def send_chat(req: ChatRequest, auth: tuple[str, str, str] = Depends(get_or_auth)) -> StreamingResponse:
    ws = workspace_id(req.workspace_id)
    if req.chat_id:
        try:
            chat = store.get_entity(ws, "chats", req.chat_id)
        except (FileNotFoundError, ValueError) as exc:
            raise error("Chat not found", 404) from exc
        if chat.get("archived"):
            raise error("Chat is archived. Please restore it before continuing.", 409)
    else:
        chat_id = new_id("chat")
        timestamp = now_iso()
        chat = {
            "schema_version": 1,
            "id": chat_id,
            "title": "New Chat",
            "messages": [],
            "created_at": timestamp,
            "updated_at": timestamp,
            "archived": False,
            "summary": "",
            "accessed_workspaces": [],
        }

    api_key, model, provider = auth
    headers = {"X-Chat-Id": chat["id"]}
    return StreamingResponse(
        _chat_stream(ws, chat, req.message.strip(), api_key, model, provider=provider, attachments=req.attachments),
        media_type="text/plain",
        headers=headers,
    )
