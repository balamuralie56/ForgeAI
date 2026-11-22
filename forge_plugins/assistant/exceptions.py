"""
Exceptions raised by the ForgeAI Assistant Plugin.
"""


class AssistantError(Exception):
    """Base class for every assistant failure."""


class AssistantStorageError(AssistantError):
    """Raised when the conversation database cannot be read or written."""


class InvalidProjectError(AssistantError):
    """Raised when a project folder does not exist or is not allowed."""


class UnsafePathError(AssistantError):
    """Raised when a path points outside the project or into a protected folder."""


class ConversationNotFoundError(AssistantError):
    """Raised when a conversation does not exist."""


class ChangeSetNotFoundError(AssistantError):
    """Raised when a change set does not exist."""


class ChangeSetStateError(AssistantError):
    """Raised when a change set cannot move to the requested status."""


class ChangeConflictError(AssistantError):
    """Raised when a file changed on disk after the change set was proposed."""


class ConversationBusyError(AssistantError):
    """Raised when a conversation already has a reply in progress."""
