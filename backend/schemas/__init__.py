from .auth import LoginRequest
from .workspace import (
    WorkspaceRequest,
    WorkspaceCreateRequest,
    WorkspaceRenameRequest,
    WorkspaceDeleteRequest,
)
from .chat import (
    ChatAttachment,
    ChatRequest,
    ChatIdRequest,
    ChatRenameRequest,
)
from .draft import (
    DraftCreateRequest,
    DraftUpdateRequest,
    DraftIdRequest,
)
from .note import (
    NoteSaveRequest,
    NoteIdRequest,
    NoteBulkDeleteRequest,
)
from .brain import (
    BrainItemUpdateRequest,
    BrainItemDeleteRequest,
    ProposalBulkRequest,
    LearningProposalRequest,
    RevisionRequest,
    CommitRevisionRequest,
    RawWritingRequest,
)
from .ai import GenerateRequest, TestConnectionRequest, AIConfigRequest

__all__ = [
    "LoginRequest",
    "WorkspaceRequest",
    "WorkspaceCreateRequest",
    "WorkspaceRenameRequest",
    "WorkspaceDeleteRequest",
    "ChatAttachment",
    "ChatRequest",
    "ChatIdRequest",
    "ChatRenameRequest",
    "DraftCreateRequest",
    "DraftUpdateRequest",
    "DraftIdRequest",
    "NoteSaveRequest",
    "NoteIdRequest",
    "NoteBulkDeleteRequest",
    "BrainItemUpdateRequest",
    "BrainItemDeleteRequest",
    "ProposalBulkRequest",
    "LearningProposalRequest",
    "RevisionRequest",
    "CommitRevisionRequest",
    "RawWritingRequest",
    "GenerateRequest",
    "TestConnectionRequest",
    "AIConfigRequest",
]
