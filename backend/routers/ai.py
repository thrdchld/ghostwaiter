from __future__ import annotations
from typing import Any
from fastapi import APIRouter, Request, Depends
from fastapi.responses import StreamingResponse
from backend.ai import ai_service, AIUnavailable
from backend.helpers import error, require_auth, get_or_auth, workspace_id, brain_system_prompt
from backend.schemas import GenerateRequest

router = APIRouter(prefix="/api/ai", tags=["ai"])

async def _generate_stream(workspace: str, prompt: str, mode: str, api_key: str, model: str, provider: str = "openrouter"):
    messages = [
        {"role": "system", "content": brain_system_prompt(workspace, mode, "", model)},
        {"role": "user", "content": prompt},
    ]
    try:
        async for text in ai_service.stream(api_key, model, messages, provider=provider):
            yield text
    except AIUnavailable as exc:
        yield f"[Error: {exc}]"

@router.post("/generate", dependencies=[Depends(require_auth)])
def generate(req: GenerateRequest, auth: tuple[str, str, str] = Depends(get_or_auth)) -> StreamingResponse:
    ws = workspace_id(req.workspace_id)
    return StreamingResponse(
        _generate_stream(ws, req.prompt, req.mode, auth[0], auth[1], auth[2]),
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "no-cache"},
    )

@router.post("/test-connection", dependencies=[Depends(require_auth)])
async def test_ai_connection(request: Request) -> dict[str, Any]:
    api_key, model, provider = get_or_auth(request)
    connected, message = await ai_service.test_connection(api_key, model, provider)
    return {"connected": connected, "message": message}

@router.post("/list-models", dependencies=[Depends(require_auth)])
async def list_ai_models(request: Request) -> dict[str, Any]:
    api_key, _model, provider = get_or_auth(request)
    try:
        models = await ai_service.list_models(api_key, provider)
    except AIUnavailable as exc:
        raise error(str(exc), 400) from exc
    return {"models": models}
