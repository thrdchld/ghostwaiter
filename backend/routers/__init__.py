from .auth import router as auth_router
from .workspaces import router as workspaces_router
from .chats import router as chats_router
from .drafts import router as drafts_router
from .notes import router as notes_router
from .brain import router as brain_router
from .ai import router as ai_router
from .system import router as system_router

__all__ = [
    "auth_router",
    "workspaces_router",
    "chats_router",
    "drafts_router",
    "notes_router",
    "brain_router",
    "ai_router",
    "system_router",
]
