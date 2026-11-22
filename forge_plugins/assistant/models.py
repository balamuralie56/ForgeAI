"""
Data models for the ForgeAI Assistant Plugin: conversations, messages, the
change sets the assistant proposes, and the results of checking them.
"""

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, Dict, List, Optional

from .diffing import unified_diff


class AssistantMode(StrEnum):
    """How the assistant handles a request."""

    ASK = "ask"
    EDIT = "edit"


class MessageRole(StrEnum):
    """Who a stored message is from."""

    USER = "user"
    ASSISTANT = "assistant"
    CHECK = "check"


class ChangeSetStatus(StrEnum):
    """Lifecycle of a proposed change set."""

    PENDING = "pending"
    APPLIED = "applied"
    DISCARDED = "discarded"
    REVERTED = "reverted"


@dataclass(frozen=True)
class AssistantSettings:
    """
    Tuning knobs for the assistant, read from the `assistant` config section.

    Attributes:
        model (str): Model to use; empty means the configured default model.
        context_tokens (int): Context window requested from the model.
        answer_tokens (int): Maximum reply length for questions.
        edit_tokens (int): Maximum reply length for code changes.
        temperature (float): Sampling temperature.
        max_edit_attempts (int): Tries per change before giving up, counting
            retries after an edit fails to apply or breaks the code.
        max_fix_rounds (int): Apply-check-fix rounds in auto-fix mode.
        check_timeout (float): Seconds before a check command is stopped.
        max_indexed_files (int): Upper bound on files indexed per project.
        max_file_bytes (int): Larger files are not indexed or edited.
        database_path (str): SQLite file that stores conversations.
    """

    model: str = ""
    context_tokens: int = 8192
    answer_tokens: int = 1024
    edit_tokens: int = 2048
    temperature: float = 0.2
    max_edit_attempts: int = 3
    max_fix_rounds: int = 3
    check_timeout: float = 300.0
    max_indexed_files: int = 4000
    max_file_bytes: int = 262144
    database_path: str = "forge_data/databases/forge_assistant.db"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AssistantSettings":
        """
        Builds settings from a config section, ignoring unknown keys and
        falling back to defaults for invalid values.

        Args:
            data (Dict[str, Any]): The `assistant` configuration section.

        Returns:
            AssistantSettings: Validated settings.
        """
        defaults = cls()

        def _int(key: str, minimum: int) -> int:
            value = data.get(key, getattr(defaults, key))
            if isinstance(value, bool) or not isinstance(value, int):
                return int(getattr(defaults, key))
            return max(minimum, value)

        def _float(key: str, minimum: float, maximum: float) -> float:
            value = data.get(key, getattr(defaults, key))
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return float(getattr(defaults, key))
            return min(maximum, max(minimum, float(value)))

        model = data.get("model", defaults.model)
        database_path = data.get("database_path", defaults.database_path)
        return cls(
            model=model if isinstance(model, str) else defaults.model,
            context_tokens=_int("context_tokens", 2048),
            answer_tokens=_int("answer_tokens", 128),
            edit_tokens=_int("edit_tokens", 256),
            temperature=_float("temperature", 0.0, 2.0),
            max_edit_attempts=_int("max_edit_attempts", 1),
            max_fix_rounds=_int("max_fix_rounds", 1),
            check_timeout=_float("check_timeout", 5.0, 3600.0),
            max_indexed_files=_int("max_indexed_files", 50),
            max_file_bytes=_int("max_file_bytes", 4096),
            database_path=(
                database_path
                if isinstance(database_path, str) and database_path
                else defaults.database_path
            ),
        )


@dataclass(frozen=True)
class Conversation:
    """
    One assistant conversation, bound to a project folder.

    Attributes:
        id (str): Unique identifier.
        title (str): Display title.
        project_root (str): Absolute path of the project the assistant works on.
        check_command (str): Command that checks the project (e.g. tests);
            empty when none is configured. Only ever set by the user.
        auto_fix (bool): Apply changes, run the check, and fix failures
            automatically instead of waiting for approval.
        created_at (float): Unix timestamp of creation.
        updated_at (float): Unix timestamp of the latest activity.
    """

    id: str
    title: str
    project_root: str
    check_command: str
    auto_fix: bool
    created_at: float
    updated_at: float

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the conversation to a plain dictionary."""
        return asdict(self)


@dataclass(frozen=True)
class Message:
    """
    One stored message of a conversation.

    Attributes:
        id (str): Unique identifier.
        conversation_id (str): Owning conversation.
        role (MessageRole): Who the message is from.
        mode (AssistantMode): The mode the request was made in.
        content (str): Message text.
        metadata (Dict[str, Any]): Extra details (context used, attempts,
            token usage, errors, check results).
        created_at (float): Unix timestamp.
    """

    id: str
    conversation_id: str
    role: MessageRole
    mode: AssistantMode
    content: str
    metadata: Dict[str, Any]
    created_at: float

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the message to a plain dictionary."""
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "role": self.role.value,
            "mode": self.mode.value,
            "content": self.content,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class FileChange:
    """
    One file of a change set.

    Attributes:
        path (str): Project-relative POSIX path.
        original (Optional[str]): Content before the change; None for a new file.
        updated (str): Content after the change.
    """

    path: str
    original: Optional[str]
    updated: str

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the file change to a plain dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FileChange":
        """Restores a file change from its dictionary form."""
        original = data.get("original")
        return cls(
            path=str(data.get("path", "")),
            original=original if isinstance(original, str) else None,
            updated=str(data.get("updated", "")),
        )


@dataclass(frozen=True)
class VerificationIssue:
    """
    A problem a static check found in changed code.

    Attributes:
        severity (str): "error" or "warning".
        check (str): Which check found it.
        path (str): Project-relative path.
        message (str): Human-readable description.
        line (Optional[int]): 1-based line, when known.
    """

    severity: str
    check: str
    path: str
    message: str
    line: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the issue to a plain dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VerificationIssue":
        """Restores an issue from its dictionary form."""
        line = data.get("line")
        return cls(
            severity=str(data.get("severity", "error")),
            check=str(data.get("check", "")),
            path=str(data.get("path", "")),
            message=str(data.get("message", "")),
            line=line if isinstance(line, int) else None,
        )


@dataclass(frozen=True)
class VerificationResult:
    """
    Static checks of a change set, run before anything is written to disk.
    Only issues the change introduces are reported; pre-existing problems
    elsewhere in the project are not the change's fault.

    Attributes:
        checked_files (int): Files the checks covered.
        issues (List[VerificationIssue]): New problems, errors first.
        skipped_reason (str): Why the checks were limited, if they were.
    """

    checked_files: int
    issues: List[VerificationIssue] = field(default_factory=list)
    skipped_reason: str = ""

    @property
    def errors(self) -> List[VerificationIssue]:
        """Issues with error severity."""
        return [i for i in self.issues if i.severity == "error"]

    @property
    def passed(self) -> bool:
        """True when the change introduces no errors."""
        return not self.errors

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the result to a plain dictionary."""
        return {
            "passed": self.passed,
            "checked_files": self.checked_files,
            "error_count": len(self.errors),
            "warning_count": len(self.issues) - len(self.errors),
            "issues": [i.to_dict() for i in self.issues],
            "skipped_reason": self.skipped_reason,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VerificationResult":
        """Restores a result from its dictionary form."""
        raw_issues = data.get("issues")
        return cls(
            checked_files=int(data.get("checked_files", 0) or 0),
            issues=[
                VerificationIssue.from_dict(i)
                for i in (raw_issues if isinstance(raw_issues, list) else [])
                if isinstance(i, dict)
            ],
            skipped_reason=str(data.get("skipped_reason", "")),
        )


@dataclass(frozen=True)
class CheckResult:
    """
    The outcome of running the user's check command.

    Attributes:
        command (str): The command as configured.
        resolved_command (List[str]): The argument vector actually executed.
        exit_code (Optional[int]): Process exit code; None if it never ran
            or was stopped.
        passed (bool): True when the command exited with code 0.
        output (str): Combined stdout/stderr, trimmed to the useful part.
        duration_seconds (float): Wall-clock duration.
        timed_out (bool): True when the command was stopped for running too long.
        error (str): Why the command could not run, if it could not.
    """

    command: str
    resolved_command: List[str]
    exit_code: Optional[int]
    passed: bool
    output: str
    duration_seconds: float
    timed_out: bool = False
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the result to a plain dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CheckResult":
        """Restores a result from its dictionary form."""
        exit_code = data.get("exit_code")
        resolved = data.get("resolved_command")
        return cls(
            command=str(data.get("command", "")),
            resolved_command=(
                [str(a) for a in resolved] if isinstance(resolved, list) else []
            ),
            exit_code=exit_code if isinstance(exit_code, int) else None,
            passed=bool(data.get("passed", False)),
            output=str(data.get("output", "")),
            duration_seconds=float(data.get("duration_seconds", 0.0) or 0.0),
            timed_out=bool(data.get("timed_out", False)),
            error=str(data.get("error", "")),
        )


@dataclass(frozen=True)
class ChangeSet:
    """
    A set of file edits the assistant proposed in one reply.

    Attributes:
        id (str): Unique identifier.
        conversation_id (str): Owning conversation.
        message_id (str): The assistant message that proposed it.
        status (ChangeSetStatus): Pending, applied, discarded or reverted.
        summary (str): One-line description of what changed.
        files (List[FileChange]): The edited files, before and after.
        verification (Optional[VerificationResult]): Static checks of the change.
        check (Optional[CheckResult]): The check command run after applying.
        created_at (float): Unix timestamp of creation.
        updated_at (float): Unix timestamp of the latest status change.
    """

    id: str
    conversation_id: str
    message_id: str
    status: ChangeSetStatus
    summary: str
    files: List[FileChange]
    verification: Optional[VerificationResult]
    check: Optional[CheckResult]
    created_at: float
    updated_at: float

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the change set, including a unified diff per file."""
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "message_id": self.message_id,
            "status": self.status.value,
            "summary": self.summary,
            "files": [
                {
                    "path": f.path,
                    "is_new": f.original is None,
                    "diff": unified_diff(f.path, f.original, f.updated),
                }
                for f in self.files
            ],
            "verification": (
                self.verification.to_dict() if self.verification else None
            ),
            "check": self.check.to_dict() if self.check else None,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
