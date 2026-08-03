from __future__ import annotations
from typing import Any
from fastapi import APIRouter, Query, Depends
from backend.storage import store, new_id, now_iso
from backend.ai import ai_service, AIUnavailable
from backend.helpers import error, require_auth, get_or_auth, workspace_id
from backend.schemas import (
    WorkspaceRequest,
    BrainItemUpdateRequest,
    BrainItemDeleteRequest,
    ProposalBulkRequest,
    LearningProposalRequest,
    RevisionRequest,
    CommitRevisionRequest,
    RawWritingRequest,
)

router = APIRouter(prefix="/api/brain", tags=["brain"])

@router.get("/profile", dependencies=[Depends(require_auth)])
def brain_profile(workspace_id_query: str | None = Query(default=None, alias="workspace_id")) -> dict[str, Any]:
    ws = workspace_id(workspace_id_query)
    brain = store.workspace_path(ws) / "brain"
    return {
        "style_profile": store.read_json(brain / "style_profile.json"),
        "thinking_profile": store.read_json(brain / "thinking_profile.json"),
        "rules": store.read_json(brain / "rules.json").get("items", []),
        "memory": store.read_json(brain / "memory.json").get("items", []),
        "conversation_memory": store.read_json(brain / "conversation_memory.json").get("items", []),
        "pending_proposals": len(
            [
                item
                for item in store.read_json(brain / "learning_proposals.json").get("items", [])
                if item.get("status", "pending") == "pending"
            ]
        ),
        "revision_count": len(store.list_entities(ws, "learning/revision_pairs")),
        "raw_writing_count": len(store.list_entities(ws, "learning/raw_writing")),
    }

@router.post("/item/update", dependencies=[Depends(require_auth)])
def update_brain_item(req: BrainItemUpdateRequest) -> dict[str, Any]:
    ws = workspace_id(req.workspace_id)
    brain = store.workspace_path(ws) / "brain"
    
    if req.type == "style":
        path = brain / "style_profile.json"
        data = store.read_json(path)
        rules = data.get("rules", [])
        if req.id_or_content in rules:
            idx = rules.index(req.id_or_content)
            rules[idx] = req.new_content
        else:
            rules.append(req.new_content)
        data["rules"] = rules
        store.write_json(path, data)
    elif req.type == "thinking":
        path = brain / "thinking_profile.json"
        data = store.read_json(path)
        patterns = data.get("patterns", [])
        if req.id_or_content in patterns:
            idx = patterns.index(req.id_or_content)
            patterns[idx] = req.new_content
        else:
            patterns.append(req.new_content)
        data["patterns"] = patterns
        store.write_json(path, data)
    elif req.type == "memory":
        path = brain / "conversation_memory.json"
        data = store.read_json(path)
        items = data.get("items", [])
        updated = False
        for item in items:
            if isinstance(item, dict) and item.get("id") == req.id_or_content:
                item["content"] = req.new_content
                updated = True
                break
        if not updated:
            items.append({"id": req.id_or_content, "content": req.new_content, "created_at": now_iso()})
        data["items"] = items
        store.write_json(path, data)
        
    return {"status": "success"}

@router.post("/item/delete", dependencies=[Depends(require_auth)])
def delete_brain_item(req: BrainItemDeleteRequest) -> dict[str, Any]:
    ws = workspace_id(req.workspace_id)
    brain = store.workspace_path(ws) / "brain"
    
    if req.type == "style":
        path = brain / "style_profile.json"
        data = store.read_json(path)
        data["rules"] = [r for r in data.get("rules", []) if r != req.id_or_content]
        store.write_json(path, data)
    elif req.type == "thinking":
        path = brain / "thinking_profile.json"
        data = store.read_json(path)
        data["patterns"] = [p for p in data.get("patterns", []) if p != req.id_or_content]
        store.write_json(path, data)
    elif req.type == "memory":
        path = brain / "conversation_memory.json"
        data = store.read_json(path)
        data["items"] = [
            i for i in data.get("items", [])
            if not (isinstance(i, dict) and i.get("id") == req.id_or_content)
        ]
        store.write_json(path, data)
        
    return {"status": "success"}

@router.get("/proposals", dependencies=[Depends(require_auth)])
def list_proposals(
    workspace_id_query: str | None = Query(default=None, alias="workspace_id"),
    status: str = "pending",
) -> dict[str, Any]:
    ws = workspace_id(workspace_id_query)
    path = store.workspace_path(ws) / "brain" / "learning_proposals.json"
    data = store.read_json(path)
    items = data.get("items", [])
    if status != "all":
        items = [i for i in items if i.get("status", "pending") == status]
    return {"items": items}

@router.post("/proposals/bulk", dependencies=[Depends(require_auth)])
def bulk_proposals(req: ProposalBulkRequest) -> dict[str, Any]:
    ws = workspace_id(req.workspace_id)
    brain = store.workspace_path(ws) / "brain"
    path = brain / "learning_proposals.json"
    data = store.read_json(path)
    items = data.get("items", [])
    
    style_path = brain / "style_profile.json"
    thinking_path = brain / "thinking_profile.json"
    style_data = store.read_json(style_path)
    thinking_data = store.read_json(thinking_path)
    
    processed = 0
    for item in items:
        if item.get("id") in req.proposal_ids:
            item["status"] = "approved" if req.action == "approve" else "rejected"
            item["updated_at"] = now_iso()
            processed += 1
            
            if req.action == "approve":
                content = item.get("content", "").strip()
                if content:
                    if item.get("type") == "style":
                        style_data["rules"] = list(dict.fromkeys(style_data.get("rules", []) + [content]))
                    elif item.get("type") == "thinking":
                        thinking_data["patterns"] = list(dict.fromkeys(thinking_data.get("patterns", []) + [content]))
                        
    store.write_json(path, data)
    if req.action == "approve":
        store.write_json(style_path, style_data)
        store.write_json(thinking_path, thinking_data)
        
    return {"status": "success", "processed": processed}

@router.post("/learn/revision", dependencies=[Depends(require_auth)])
async def learn_revision(req: RevisionRequest, auth: tuple[str, str, str] = Depends(get_or_auth)) -> dict[str, Any]:
    ws = workspace_id(req.workspace_id)
    try:
        analysis = await ai_service.learn_revision(auth[0], auth[1], req.ai_output, req.user_revision, provider=auth[2])
    except AIUnavailable as exc:
        raise error(str(exc), 503) from exc
    timestamp = now_iso()
    store.save_entity(
        ws,
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
    brain = store.workspace_path(ws) / "brain"
    style = store.read_json(brain / "style_profile.json")
    thinking = store.read_json(brain / "thinking_profile.json")
    style["rules"] = list(dict.fromkeys(style.get("rules", []) + analysis["style_rules"]))[-100:]
    thinking["patterns"] = list(dict.fromkeys(thinking.get("patterns", []) + analysis["thinking_patterns"]))[-100:]
    store.write_json(brain / "style_profile.json", style)
    store.write_json(brain / "thinking_profile.json", thinking)
    store.enqueue_sync("brain", ws, analysis)
    return {"status": "learned", "analysis": analysis}

@router.post("/compare-revision", dependencies=[Depends(require_auth)])
async def compare_revision(req: RevisionRequest, auth: tuple[str, str, str] = Depends(get_or_auth)) -> dict[str, Any]:
    try:
        analysis = await ai_service.learn_revision(auth[0], auth[1], req.ai_output, req.user_revision, provider=auth[2])
    except AIUnavailable as exc:
        raise error(str(exc), 503) from exc
    return {"status": "analyzed", "analysis": analysis}

@router.post("/commit-revision", dependencies=[Depends(require_auth)])
async def commit_revision(req: CommitRevisionRequest) -> dict[str, Any]:
    ws = workspace_id(req.workspace_id)
    brain = store.workspace_path(ws) / "brain"
    style = store.read_json(brain / "style_profile.json")
    thinking = store.read_json(brain / "thinking_profile.json")
    if req.revised_text:
        style["rules"] = list(dict.fromkeys(style.get("rules", []) + [req.revised_text]))[-100:]
    if req.learning_notes:
        thinking["patterns"] = list(dict.fromkeys(thinking.get("patterns", []) + [req.learning_notes]))[-100:]
    store.write_json(brain / "style_profile.json", style)
    store.write_json(brain / "thinking_profile.json", thinking)
    return {"status": "learned"}

@router.post("/learn/raw-writing", dependencies=[Depends(require_auth)])
async def learn_raw(req: RawWritingRequest, auth: tuple[str, str, str] = Depends(get_or_auth)) -> dict[str, Any]:
    ws = workspace_id(req.workspace_id)
    prompt = (
        "Analyze the following writing style. Reply with one concrete, concise style rule "
        "that can be reapplied. Do not summarize the content. "
        "Write the rule in the same language as the writing sample."
    )
    try:
        rule = (
            await ai_service.complete(
                auth[0], auth[1],
                [{"role": "system", "content": prompt}, {"role": "user", "content": req.text}],
                provider=auth[2],
                max_tokens=160,
                temperature=0.2,
            )
        ).strip()
    except AIUnavailable as exc:
        raise error(str(exc), 503) from exc
    item = {
        "schema_version": 1,
        "id": new_id("raw"),
        "content": req.text,
        "context": req.context,
        "analysis": rule,
        "created_at": now_iso(),
    }
    store.save_entity(ws, "learning/raw_writing", item)
    profile_path = store.workspace_path(ws) / "brain" / "style_profile.json"
    profile = store.read_json(profile_path)
    profile["rules"] = list(dict.fromkeys(profile.get("rules", []) + [rule]))[-100:]
    store.write_json(profile_path, profile)
    return {"status": "learned", "rule": rule}
