"""
Service interface and implementation of the ForgeAI Assistant: a local
coding assistant that answers questions about a project and makes checked
changes to it, with every conversation and change stored on disk.
"""

import logging
import queue
import threading
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

from forge_core.configuration.service import ConfigurationService
from forge_core.event_bus.models import Event
from forge_core.event_bus.service import EventBusService
from forge_core.kernel.exceptions import ServiceNotFoundError
from forge_core.kernel.service_registry import ServiceRegistry
from forge_core.model_router.service import ModelRouterService

from .components.agent import AssistantAgent, Prompts, check_summary
from .components.check_runner import split_command
from .components.workspace import validate_project_root
from .exceptions import (
    AssistantError,
    ChangeSetNotFoundError,
    ChangeSetStateError,
    ConversationBusyError,
    ConversationNotFoundError,
)
from .models import (
    AssistantMode,
    AssistantSettings,
    ChangeSet,
    ChangeSetStatus,
    Conversation,
    Message,
)
from .store import SQLiteAssistantStore

logger = logging.getLogger("ForgeAI.Plugins.Assistant.Service")

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_TITLE_CHARS = 60


class TurnHandle:
    """
    A running assistant turn. Its events are produced on a worker thread and
    can be consumed from any other thread; the turn keeps going (and is
    stored) even if nobody is listening, until it finishes or is cancelled.
    """

    def __init__(self, conversation_id: str) -> None:
        """
        Args:
            conversation_id (str): The conversation the turn belongs to.
        """
        self.conversation_id = conversation_id
        self.cancel_event = threading.Event()
        self._events: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self._finished = threading.Event()

    def publish(self, event: Dict[str, Any]) -> None:
        """Queues an event for listeners (worker thread side)."""
        self._events.put(event)
        if event.get("type") == "done":
            self._finished.set()

    def events(self) -> Iterator[Dict[str, Any]]:
        """
        Yields the turn's events as they happen, ending with `done`.

        Yields:
            Dict[str, Any]: Events (see AssistantAgent.run_turn).
        """
        while True:
            event = self._events.get()
            yield event
            if event.get("type") == "done":
                return

    def next_event(self, timeout: float) -> Optional[Dict[str, Any]]:
        """
        Waits up to `timeout` seconds for the next event.

        Args:
            timeout (float): Seconds to wait.

        Returns:
            Optional[Dict[str, Any]]: The event, or None if none arrived in time.
        """
        try:
            return self._events.get(timeout=timeout)
        except queue.Empty:
            return None

    def cancel(self) -> None:
        """Asks the turn to stop generating as soon as possible."""
        self.cancel_event.set()

    @property
    def finished(self) -> bool:
        """True once the turn has ended."""
        return self._finished.is_set()


class AssistantService(ABC):
    """Service registry interface of the Assistant Plugin."""

    @abstractmethod
    def status(self) -> Dict[str, Any]:
        """Returns the model and limits the assistant uses."""

    @abstractmethod
    def list_conversations(
        self, limit: int = 50, offset: int = 0
    ) -> List[Conversation]:
        """Returns conversations, most recently active first."""

    @abstractmethod
    def count_conversations(self) -> int:
        """Returns the number of stored conversations."""

    @abstractmethod
    def create_conversation(
        self,
        project_root: str,
        title: str = "",
        check_command: str = "",
        auto_fix: bool = False,
    ) -> Conversation:
        """
        Starts a conversation about a project folder.

        Raises:
            InvalidProjectError: If the folder is not usable.
            AssistantError: If the check command cannot be parsed.
        """

    @abstractmethod
    def update_conversation(
        self,
        conversation_id: str,
        *,
        title: Optional[str] = None,
        project_root: Optional[str] = None,
        check_command: Optional[str] = None,
        auto_fix: Optional[bool] = None,
    ) -> Conversation:
        """Changes a conversation's settings."""

    @abstractmethod
    def get_conversation(self, conversation_id: str) -> Conversation:
        """
        Returns a conversation.

        Raises:
            ConversationNotFoundError: If it does not exist.
        """

    @abstractmethod
    def delete_conversation(self, conversation_id: str) -> bool:
        """Deletes a conversation with its messages and change sets."""

    @abstractmethod
    def list_messages(self, conversation_id: str) -> List[Message]:
        """Returns a conversation's messages, oldest first."""

    @abstractmethod
    def list_change_sets(self, conversation_id: str) -> List[ChangeSet]:
        """Returns a conversation's change sets, oldest first."""

    @abstractmethod
    def list_project_files(self, conversation_id: str) -> List[str]:
        """Returns the source files of a conversation's project."""

    @abstractmethod
    def start_turn(
        self,
        conversation_id: str,
        text: str,
        mode: AssistantMode,
        attached_paths: Sequence[str] = (),
    ) -> TurnHandle:
        """
        Starts handling a request on a background thread.

        Raises:
            ConversationBusyError: If the conversation already has a reply in progress.
        """

    @abstractmethod
    def stop_turn(self, conversation_id: str) -> bool:
        """Cancels a conversation's running turn; True if one was running."""

    @abstractmethod
    def apply_change_set(
        self, change_set_id: str
    ) -> Tuple[ChangeSet, Optional[Message]]:
        """
        Writes a pending change to disk, then runs the check command if one
        is configured.

        Returns:
            Tuple[ChangeSet, Optional[Message]]: The updated change set and
            the stored check message (None without a check command).
        """

    @abstractmethod
    def discard_change_set(self, change_set_id: str) -> ChangeSet:
        """Marks a pending change as discarded without writing it."""

    @abstractmethod
    def revert_change_set(self, change_set_id: str) -> ChangeSet:
        """Restores the files an applied change modified."""

    @abstractmethod
    def run_check(self, conversation_id: str) -> Message:
        """Runs the conversation's check command and stores the result."""

    @abstractmethod
    def storage(self) -> Dict[str, Any]:
        """Returns the size of the assistant database and its row counts."""


class ForgeAIAssistant(AssistantService):
    """Concrete Assistant Service."""

    def __init__(
        self,
        registry: ServiceRegistry,
        settings: Optional[AssistantSettings] = None,
        store: Optional[SQLiteAssistantStore] = None,
    ) -> None:
        """
        Args:
            registry (ServiceRegistry): Resolves the model router,
                configuration and (optionally) the event bus.
            settings (Optional[AssistantSettings]): Overrides the `assistant`
                configuration section.
            store (Optional[SQLiteAssistantStore]): Overrides the database.
        """
        config: ConfigurationService = registry.resolve(ConfigurationService)  # type: ignore[type-abstract]
        self._router: ModelRouterService = registry.resolve(ModelRouterService)  # type: ignore[type-abstract]
        try:
            self._event_bus: Optional[EventBusService] = registry.resolve(EventBusService)  # type: ignore[type-abstract]
        except ServiceNotFoundError:
            self._event_bus = None
        self._settings = settings or AssistantSettings.from_dict(
            dict(config.get_full_config().assistant or {})
        )
        self._default_model = config.get_model_settings().default_model
        self._store = store or SQLiteAssistantStore(self._settings.database_path)
        self._agent = AssistantAgent(
            self._router, self._store, self._settings, self._load_prompts()
        )
        self._active: Dict[str, TurnHandle] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _load_prompts() -> Prompts:
        return Prompts(
            ask=(_PROMPTS_DIR / "ask_system.txt").read_text(encoding="utf-8").strip(),
            edit=(_PROMPTS_DIR / "edit_system.txt").read_text(encoding="utf-8").strip(),
        )

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def initialize(self) -> None:
        """Opens the conversation database."""
        self._store.initialize()

    def shutdown(self) -> None:
        """Cancels running turns and closes the database."""
        with self._lock:
            handles = list(self._active.values())
        for handle in handles:
            handle.cancel()
        for handle in handles:
            deadline = time.monotonic() + 10
            while not handle.finished and time.monotonic() < deadline:
                time.sleep(0.05)
        self._store.close()

    # ── Conversations ──────────────────────────────────────────────────────

    def status(self) -> Dict[str, Any]:
        return {
            "model": self._settings.model or self._default_model,
            "context_tokens": self._settings.context_tokens,
            "max_edit_attempts": self._settings.max_edit_attempts,
            "max_fix_rounds": self._settings.max_fix_rounds,
            "check_timeout": self._settings.check_timeout,
            "active_conversations": sorted(self._active_ids()),
        }

    def list_conversations(
        self, limit: int = 50, offset: int = 0
    ) -> List[Conversation]:
        return self._store.list_conversations(max(1, limit), max(0, offset))

    def count_conversations(self) -> int:
        return self._store.count_conversations()

    def create_conversation(
        self,
        project_root: str,
        title: str = "",
        check_command: str = "",
        auto_fix: bool = False,
    ) -> Conversation:
        root = validate_project_root(project_root)
        command = self._validated_command(check_command)
        now = time.time()
        conversation = Conversation(
            id=uuid.uuid4().hex,
            title=title.strip()[:120],
            project_root=str(root),
            check_command=command,
            auto_fix=bool(auto_fix),
            created_at=now,
            updated_at=now,
        )
        self._store.save_conversation(conversation)
        logger.info(f"Created conversation {conversation.id} for {root}")
        return conversation

    def update_conversation(
        self,
        conversation_id: str,
        *,
        title: Optional[str] = None,
        project_root: Optional[str] = None,
        check_command: Optional[str] = None,
        auto_fix: Optional[bool] = None,
    ) -> Conversation:
        conversation = self.get_conversation(conversation_id)
        changes: Dict[str, Any] = {"updated_at": time.time()}
        if title is not None:
            changes["title"] = title.strip()[:120]
        if project_root is not None:
            self._require_idle(conversation_id)
            changes["project_root"] = str(validate_project_root(project_root))
        if check_command is not None:
            changes["check_command"] = self._validated_command(check_command)
        if auto_fix is not None:
            changes["auto_fix"] = bool(auto_fix)
        updated = replace(conversation, **changes)
        self._store.save_conversation(updated)
        return updated

    def get_conversation(self, conversation_id: str) -> Conversation:
        conversation = self._store.get_conversation(conversation_id)
        if conversation is None:
            raise ConversationNotFoundError(
                f"Conversation '{conversation_id}' not found."
            )
        return conversation

    def delete_conversation(self, conversation_id: str) -> bool:
        self._require_idle(conversation_id)
        deleted = self._store.delete_conversation(conversation_id)
        if deleted:
            logger.info(f"Deleted conversation {conversation_id}")
        return deleted

    def list_messages(self, conversation_id: str) -> List[Message]:
        self.get_conversation(conversation_id)
        return self._store.list_messages(conversation_id)

    def list_change_sets(self, conversation_id: str) -> List[ChangeSet]:
        self.get_conversation(conversation_id)
        return self._store.list_change_sets(conversation_id)

    def list_project_files(self, conversation_id: str) -> List[str]:
        conversation = self.get_conversation(conversation_id)
        workspace = self._agent.workspace(conversation)
        return self._agent.indexes.get(workspace).paths()

    # ── Turns ──────────────────────────────────────────────────────────────

    def start_turn(
        self,
        conversation_id: str,
        text: str,
        mode: AssistantMode,
        attached_paths: Sequence[str] = (),
    ) -> TurnHandle:
        if not text.strip():
            raise AssistantError("The message is empty.")
        conversation = self.get_conversation(conversation_id)
        handle = TurnHandle(conversation_id)
        with self._lock:
            if conversation_id in self._active:
                raise ConversationBusyError(
                    "ForgeAI is still replying in this conversation. Wait, or stop it first."
                )
            self._active[conversation_id] = handle

        if not conversation.title:
            first_line = text.strip().splitlines()[0]
            title = first_line[:_TITLE_CHARS] + (
                "..." if len(first_line) > _TITLE_CHARS else ""
            )
            conversation = replace(conversation, title=title, updated_at=time.time())
            self._store.save_conversation(conversation)

        def _run() -> None:
            started = time.perf_counter()
            try:
                for event in self._agent.run_turn(
                    conversation, text, mode, list(attached_paths), handle.cancel_event
                ):
                    handle.publish(event)
            except Exception as e:  # noqa: BLE001 - a worker must always end its stream
                logger.error(f"Assistant turn crashed: {e}", exc_info=True)
                handle.publish({"type": "error", "detail": f"Unexpected error: {e}"})
                handle.publish({"type": "done"})
            finally:
                with self._lock:
                    self._active.pop(conversation_id, None)
                if not handle.finished:
                    handle.publish({"type": "done"})
                self._publish(
                    "assistant.turn_finished",
                    {
                        "conversation_id": conversation_id,
                        "mode": mode.value,
                        "seconds": round(time.perf_counter() - started, 1),
                        "cancelled": handle.cancel_event.is_set(),
                    },
                )

        thread = threading.Thread(
            target=_run, name=f"forge-assistant-{conversation_id[:8]}", daemon=True
        )
        thread.start()
        return handle

    def stop_turn(self, conversation_id: str) -> bool:
        with self._lock:
            handle = self._active.get(conversation_id)
        if handle is None:
            return False
        handle.cancel()
        return True

    # ── Change sets ────────────────────────────────────────────────────────

    def apply_change_set(
        self, change_set_id: str
    ) -> Tuple[ChangeSet, Optional[Message]]:
        change_set = self._get_change_set(change_set_id)
        if change_set.status is not ChangeSetStatus.PENDING:
            raise ChangeSetStateError(
                f"This change is {change_set.status.value}; only pending changes can be applied."
            )
        conversation = self.get_conversation(change_set.conversation_id)
        self._require_idle(conversation.id)
        workspace = self._agent.workspace(conversation)
        try:
            self._agent.applier.apply(workspace, change_set)
        except OSError as e:
            raise AssistantError(f"Could not write the change: {e}") from e
        change_set = replace(
            change_set, status=ChangeSetStatus.APPLIED, updated_at=time.time()
        )
        self._store.save_change_set(change_set)
        self._publish(
            "assistant.change_applied",
            {
                "conversation_id": conversation.id,
                "change_set_id": change_set.id,
                "files": [f.path for f in change_set.files],
            },
        )

        check_message: Optional[Message] = None
        if conversation.check_command:
            result, check_message = self._agent.run_check(conversation, workspace)
            change_set = replace(change_set, check=result, updated_at=time.time())
            self._store.save_change_set(change_set)
            self._publish(
                "assistant.check_finished",
                {"conversation_id": conversation.id, "summary": check_summary(result)},
            )
        self._store.touch_conversation(conversation.id, time.time())
        return change_set, check_message

    def discard_change_set(self, change_set_id: str) -> ChangeSet:
        change_set = self._get_change_set(change_set_id)
        if change_set.status is not ChangeSetStatus.PENDING:
            raise ChangeSetStateError(
                f"This change is {change_set.status.value}; only pending changes can be discarded."
            )
        change_set = replace(
            change_set, status=ChangeSetStatus.DISCARDED, updated_at=time.time()
        )
        self._store.save_change_set(change_set)
        return change_set

    def revert_change_set(self, change_set_id: str) -> ChangeSet:
        change_set = self._get_change_set(change_set_id)
        if change_set.status is not ChangeSetStatus.APPLIED:
            raise ChangeSetStateError(
                f"This change is {change_set.status.value}; only applied changes can be undone."
            )
        conversation = self.get_conversation(change_set.conversation_id)
        self._require_idle(conversation.id)
        workspace = self._agent.workspace(conversation)
        try:
            self._agent.applier.revert(workspace, change_set)
        except OSError as e:
            raise AssistantError(f"Could not restore the files: {e}") from e
        change_set = replace(
            change_set, status=ChangeSetStatus.REVERTED, updated_at=time.time()
        )
        self._store.save_change_set(change_set)
        self._publish(
            "assistant.change_reverted",
            {"conversation_id": conversation.id, "change_set_id": change_set.id},
        )
        return change_set

    def run_check(self, conversation_id: str) -> Message:
        conversation = self.get_conversation(conversation_id)
        if not conversation.check_command:
            raise AssistantError("Set a check command for this conversation first.")
        self._require_idle(conversation_id)
        _, message = self._agent.run_check(
            conversation, self._agent.workspace(conversation)
        )
        self._store.touch_conversation(conversation_id, time.time())
        return message

    def storage(self) -> Dict[str, Any]:
        return self._store.stats()

    # ── Helpers ────────────────────────────────────────────────────────────

    def _get_change_set(self, change_set_id: str) -> ChangeSet:
        change_set = self._store.get_change_set(change_set_id)
        if change_set is None:
            raise ChangeSetNotFoundError(f"Change '{change_set_id}' not found.")
        return change_set

    def _active_ids(self) -> List[str]:
        with self._lock:
            return list(self._active)

    def _require_idle(self, conversation_id: str) -> None:
        with self._lock:
            if conversation_id in self._active:
                raise ConversationBusyError(
                    "ForgeAI is still replying in this conversation. Wait, or stop it first."
                )

    @staticmethod
    def _validated_command(command: str) -> str:
        cleaned = (command or "").strip()
        if not cleaned:
            return ""
        try:
            split_command(cleaned)
        except ValueError as e:
            raise AssistantError(f"Invalid check command: {e}") from e
        return cleaned

    def _publish(self, event_type: str, data: Dict[str, Any]) -> None:
        if self._event_bus is None:
            return
        try:
            self._event_bus.publish(Event(event_type=event_type, data=data))
        except (
            Exception
        ) as e:  # noqa: BLE001 - event delivery must never break the assistant
            logger.warning(f"Could not publish {event_type}: {e}")
