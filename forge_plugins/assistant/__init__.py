"""
ForgeAI Assistant Plugin: a local coding assistant that answers questions
about a project and makes checked, reversible changes to it.
"""

from .exceptions import (
    AssistantError,
    ChangeConflictError,
    ChangeSetNotFoundError,
    ChangeSetStateError,
    ConversationBusyError,
    ConversationNotFoundError,
    InvalidProjectError,
    UnsafePathError,
)
from .models import AssistantMode, ChangeSet, Conversation, Message
from .plugin import AssistantPlugin
from .service import AssistantService, ForgeAIAssistant, TurnHandle

__all__ = [
    "AssistantPlugin",
    "AssistantService",
    "ForgeAIAssistant",
    "TurnHandle",
    "AssistantMode",
    "ChangeSet",
    "Conversation",
    "Message",
    "AssistantError",
    "ChangeConflictError",
    "ChangeSetNotFoundError",
    "ChangeSetStateError",
    "ConversationBusyError",
    "ConversationNotFoundError",
    "InvalidProjectError",
    "UnsafePathError",
]
