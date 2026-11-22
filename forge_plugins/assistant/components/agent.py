"""
Runs one assistant turn and streams what happens as events.

The loop mirrors how an experienced engineer works, with each step checked
by code rather than trusted to the model:

1. find the relevant code (lexical search + files the user names),
2. ask the model for an answer or for edit blocks, streaming its reply,
3. apply the edits to in-memory copies - if any edit doesn't match the
   file, tell the model exactly why and let it try again,
4. statically check the result - if the change would break the code, show
   the model the errors and let it try again,
5. propose the change for approval; or, in auto-fix mode, apply it, run
   the user's check command, and feed failures back for another round.

The model's output is never executed. Only the user's own check command is.
"""

import logging
import re
import threading
import time
import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, Generator, Iterator, List, Optional, Sequence, Tuple

from forge_core.model_router.exceptions import GenerationError
from forge_core.model_router.service import ModelRouterService

from ..exceptions import AssistantError, ChangeConflictError
from ..models import (
    AssistantMode,
    AssistantSettings,
    ChangeSet,
    ChangeSetStatus,
    CheckResult,
    Conversation,
    FileChange,
    Message,
    MessageRole,
    VerificationResult,
)
from ..store import SQLiteAssistantStore
from .change_applier import ChangeApplier
from .change_verifier import ChangeVerifier
from .check_runner import CheckRunner
from .code_index import CodeIndex, IndexCache
from .context_builder import BuiltContext, ContextBuilder, estimate_tokens
from .snippet_edits import definition_edits
from .edit_blocks import (
    EditProblem,
    apply_edit_blocks,
    has_code_block,
    parse_edit_blocks,
    whole_file_edits,
)
from .workspace import ProjectWorkspace

logger = logging.getLogger("ForgeAI.Plugins.Assistant.Agent")

Event = Dict[str, Any]

_FEEDBACK_OUTPUT_CHARS = 3000


@dataclass(frozen=True)
class Prompts:
    """System prompts per mode."""

    ask: str
    edit: str


@dataclass
class _StreamOutcome:
    text: str = ""
    usage: Dict[str, int] = field(default_factory=dict)
    cancelled: bool = False
    error: str = ""
    seconds: float = 0.0


@dataclass
class _EditOutcome:
    reply: str
    change_set: Optional[ChangeSet]
    message: Message
    stopped: bool


def _now() -> float:
    return time.time()


def _new_id() -> str:
    return uuid.uuid4().hex


def summarize_plan(reply: str, files: Sequence[FileChange]) -> str:
    """One-line summary of a change: the model's plan, or the files touched."""
    plan = reply.split("<<<<<<<", 1)[0]
    for line in plan.splitlines():
        text = line.strip().strip("*#`>-").strip()
        if (
            text
            and not text.startswith("```")
            and not text.endswith((".py", ".ts", ".tsx", ".js"))
        ):
            return text if len(text) <= 160 else text[:157] + "..."
    return "Edit " + ", ".join(f.path for f in files)


def format_problems(problems: Sequence[EditProblem]) -> str:
    """Feedback for edits that failed to parse or apply."""
    lines = [
        "None of your edits were applied, because some of them could not be used:",
        "",
    ]
    for number, problem in enumerate(problems, 1):
        where = f"{problem.path}: " if problem.path else ""
        lines.append(f"{number}. {where}{problem.message}")
        if problem.hint:
            lines.append(problem.hint)
        lines.append("")
    lines.append(
        "Write all of the edit blocks again, with these problems fixed. "
        "Copy SEARCH lines exactly from the code you were shown."
    )
    return "\n".join(lines)


def format_verification(result: VerificationResult) -> str:
    """Feedback for edits that apply but would break the code."""
    lines = [
        "Your edits apply, but they would break the code. None of them were applied.",
        "",
    ]
    for issue in result.errors[:12]:
        where = f"{issue.path}:{issue.line}" if issue.line else issue.path
        lines.append(f"- {where}: {issue.message}")
    lines.append("")
    lines.append(
        "Write all of the edit blocks again so the code has none of these errors."
    )
    return "\n".join(lines)


def format_check_failure(result: CheckResult) -> str:
    """The follow-up request sent after the check command fails in auto-fix mode."""
    output = result.output or result.error
    if len(output) > _FEEDBACK_OUTPUT_CHARS:
        output = "[...]\n" + output[-_FEEDBACK_OUTPUT_CHARS:]
    status = (
        "timed out" if result.timed_out else f"failed with exit code {result.exit_code}"
    )
    return (
        f"After your change, the check command `{result.command}` {status}. "
        "Fix the code so the check passes. Here is its output:\n"
        f"```\n{output.strip()}\n```"
    )


_FAILURE_WORDS = re.compile(
    r"\b(fail\w*|error\w*|broken|break\w*|crash\w*|bugs?|traceback|exception\w*|"
    r"not working|doesn'?t work|does not work|won'?t run|wrong)\b",
    re.IGNORECASE,
)


def should_reproduce(
    conversation: Conversation, text: str, history: Sequence[Message]
) -> bool:
    """
    Whether to run the check command before answering: the user describes a
    failure, a check command is configured, and the user has not already
    pasted output or just run the check.
    """
    if not conversation.check_command or "```" in text:
        return False
    if not _FAILURE_WORDS.search(text):
        return False
    return not (history and history[-1].role is MessageRole.CHECK)


def format_check_evidence(result: CheckResult) -> str:
    """Check output appended to a request so the model works from the real error."""
    output = (result.output or result.error).strip()
    if len(output) > _FEEDBACK_OUTPUT_CHARS:
        output = "[...]\n" + output[-_FEEDBACK_OUTPUT_CHARS:]
    if result.timed_out:
        verdict = "timed out"
    elif result.passed:
        verdict = "passed"
    elif result.exit_code is None:
        verdict = "could not run"
    else:
        verdict = f"failed with exit code {result.exit_code}"
    return (
        f"(ForgeAI ran the check command `{result.command}` just now: it {verdict}. "
        "Base your answer on this real output.)\n"
        f"```\n{output}\n```"
    )


def check_summary(result: CheckResult) -> str:
    """One-line description of a check result."""
    if result.error and result.exit_code is None and not result.timed_out:
        return f"Could not run `{result.command}`: {result.error}"
    if result.timed_out:
        return f"`{result.command}` was stopped after {result.duration_seconds:.0f}s."
    verdict = "passed" if result.passed else f"failed (exit code {result.exit_code})"
    return f"`{result.command}` {verdict} in {result.duration_seconds:.1f}s."


class AssistantAgent:
    """Runs assistant turns against one model router and store."""

    def __init__(
        self,
        router: ModelRouterService,
        store: SQLiteAssistantStore,
        settings: AssistantSettings,
        prompts: Prompts,
        indexes: Optional[IndexCache] = None,
        verifier: Optional[ChangeVerifier] = None,
        checks: Optional[CheckRunner] = None,
        applier: Optional[ChangeApplier] = None,
    ) -> None:
        """
        Args:
            router (ModelRouterService): Model access.
            store (SQLiteAssistantStore): Conversation persistence.
            settings (AssistantSettings): Tuning knobs.
            prompts (Prompts): System prompts.
            indexes (Optional[IndexCache]): Shared project indexes.
            verifier (Optional[ChangeVerifier]): Static change checks.
            checks (Optional[CheckRunner]): Check command runner.
            applier (Optional[ChangeApplier]): Writes changes to disk.
        """
        self._router = router
        self._store = store
        self._settings = settings
        self._prompts = prompts
        self._indexes = indexes or IndexCache()
        self._verifier = verifier or ChangeVerifier()
        self._checks = checks or CheckRunner()
        self._applier = applier or ChangeApplier()
        self._builder = ContextBuilder(settings.context_tokens)

    @property
    def indexes(self) -> IndexCache:
        """The project index cache shared with the service."""
        return self._indexes

    @property
    def applier(self) -> ChangeApplier:
        """Writes and undoes change sets on disk."""
        return self._applier

    def workspace(self, conversation: Conversation) -> ProjectWorkspace:
        """Opens the project folder of a conversation."""
        return ProjectWorkspace(
            conversation.project_root,
            self._settings.max_indexed_files,
            self._settings.max_file_bytes,
        )

    # ── Turn ───────────────────────────────────────────────────────────────

    def run_turn(
        self,
        conversation: Conversation,
        text: str,
        mode: AssistantMode,
        attached_paths: Sequence[str],
        cancel: threading.Event,
    ) -> Iterator[Event]:
        """
        Handles one user request and yields events as it progresses.

        Events (each a dict with a "type"): `message` (a stored message),
        `context` (what code the model was shown), `token` (reply text),
        `attempt` (a retry starts, with the reason), `status` (progress
        note), `change_set` (a proposed or updated change), `error`, and a
        final `done`.

        Args:
            conversation (Conversation): The conversation.
            text (str): The user's request.
            mode (AssistantMode): Ask or edit.
            attached_paths (Sequence[str]): Files the user attached.
            cancel (threading.Event): Set to stop generating.

        Yields:
            Event: Progress events, ending with `done`.
        """
        try:
            workspace = self.workspace(conversation)
            index = self._indexes.get(workspace)
            attached = [
                p for p in (self._safe(workspace, a) for a in attached_paths) if p
            ]
            history = self._store.list_messages(conversation.id)

            user_message = Message(
                _new_id(),
                conversation.id,
                MessageRole.USER,
                mode,
                text,
                {"attached": attached} if attached else {},
                _now(),
            )
            self._store.add_message(user_message)
            yield {"type": "message", "message": user_message.to_dict()}

            request = text
            if should_reproduce(conversation, text, history):
                # Like an engineer would: look at the actual failure before
                # explaining or fixing it, instead of guessing from the code.
                yield {
                    "type": "status",
                    "text": f"Running {conversation.check_command} first to see the problem...",
                }
                result, check_message = self.run_check(conversation, workspace)
                yield {"type": "message", "message": check_message.to_dict()}
                request = text + "\n\n" + format_check_evidence(result)
                index = self._indexes.get(workspace)

            if mode is AssistantMode.ASK:
                yield from self._answer(
                    conversation, workspace, index, request, history, attached, cancel
                )
            else:
                yield from self._edit_loop(
                    conversation, workspace, index, request, history, attached, cancel
                )
        except AssistantError as e:
            logger.warning(f"Assistant turn failed: {e}")
            yield {"type": "error", "detail": str(e)}
        finally:
            self._store.touch_conversation(conversation.id, _now())
        yield {"type": "done"}

    @staticmethod
    def _safe(workspace: ProjectWorkspace, path: str) -> Optional[str]:
        try:
            normalized = workspace.normalize(path)
        except AssistantError as e:
            logger.info(f"Ignoring attached path {path!r}: {e}")
            return None
        return normalized if workspace.exists(normalized) else None

    # ── Ask ────────────────────────────────────────────────────────────────

    def _answer(
        self,
        conversation: Conversation,
        workspace: ProjectWorkspace,
        index: CodeIndex,
        text: str,
        history: Sequence[Message],
        attached: Sequence[str],
        cancel: threading.Event,
    ) -> Iterator[Event]:
        context = self._builder.build(
            mode=AssistantMode.ASK,
            system_prompt=self._prompts.ask,
            request=text,
            index=index,
            project_name=workspace.root.name,
            history=history,
            change_sets=self._change_sets(conversation.id),
            attached_paths=attached,
            output_tokens=self._settings.answer_tokens,
        )
        yield self._context_event(context)
        outcome = yield from self._stream(
            context.messages, self._settings.answer_tokens, cancel
        )
        message = Message(
            _new_id(),
            conversation.id,
            MessageRole.ASSISTANT,
            AssistantMode.ASK,
            outcome.text,
            self._reply_metadata(context, outcome),
            _now(),
        )
        self._store.add_message(message)
        if outcome.error:
            yield {"type": "error", "detail": outcome.error}
        yield {"type": "message", "message": message.to_dict()}

    # ── Edit ───────────────────────────────────────────────────────────────

    def _edit_loop(
        self,
        conversation: Conversation,
        workspace: ProjectWorkspace,
        index: CodeIndex,
        text: str,
        history: Sequence[Message],
        attached: Sequence[str],
        cancel: threading.Event,
    ) -> Iterator[Event]:
        request = text
        fix_round = 1
        while True:
            outcome = yield from self._edit_round(
                conversation, workspace, index, request, history, attached, cancel
            )
            if (
                outcome.stopped
                or outcome.change_set is None
                or not conversation.auto_fix
            ):
                return

            change_set = outcome.change_set
            if (
                change_set.verification is not None
                and not change_set.verification.passed
            ):
                yield {
                    "type": "status",
                    "text": "Not applied automatically: static checks found errors in "
                    "this change. Review it and apply or discard it yourself.",
                }
                return
            try:
                self._applier.apply(workspace, change_set)
            except ChangeConflictError as e:
                yield {"type": "error", "detail": str(e)}
                return
            except OSError as e:
                yield {"type": "error", "detail": f"Could not write the change: {e}"}
                return
            change_set = replace(
                change_set, status=ChangeSetStatus.APPLIED, updated_at=_now()
            )
            self._store.save_change_set(change_set)
            yield {"type": "change_set", "change_set": change_set.to_dict()}

            if not conversation.check_command:
                return
            yield {
                "type": "status",
                "text": f"Running `{conversation.check_command}`...",
            }
            result, check_message = self.run_check(conversation, workspace)
            change_set = replace(change_set, check=result, updated_at=_now())
            self._store.save_change_set(change_set)
            yield {"type": "change_set", "change_set": change_set.to_dict()}
            yield {"type": "message", "message": check_message.to_dict()}
            if result.passed or cancel.is_set():
                return
            if fix_round >= self._settings.max_fix_rounds:
                yield {
                    "type": "status",
                    "text": f"The check still fails after {fix_round} round(s); stopping here.",
                }
                return

            fix_round += 1
            request = format_check_failure(result)
            follow_up = Message(
                _new_id(),
                conversation.id,
                MessageRole.USER,
                AssistantMode.EDIT,
                request,
                {"auto_fix_round": fix_round},
                _now(),
            )
            self._store.add_message(follow_up)
            yield {"type": "message", "message": follow_up.to_dict()}
            index = self._indexes.get(workspace)
            # The follow-up request already carries the check output.
            skip = {check_message.id, follow_up.id}
            history = [
                m
                for m in self._store.list_messages(conversation.id)
                if m.id not in skip
            ]
            attached = [f.path for f in change_set.files]

    def _edit_round(
        self,
        conversation: Conversation,
        workspace: ProjectWorkspace,
        index: CodeIndex,
        request: str,
        history: Sequence[Message],
        attached: Sequence[str],
        cancel: threading.Event,
    ) -> Generator[Event, None, _EditOutcome]:
        change_sets = self._change_sets(conversation.id)
        feedback: List[Dict[str, str]] = []
        attempts: List[Dict[str, Any]] = []
        context: Optional[BuiltContext] = None
        outcome = _StreamOutcome()
        change_set: Optional[ChangeSet] = None
        total_seconds = 0.0
        usage_total: Dict[str, int] = {}

        for attempt in range(1, self._settings.max_edit_attempts + 1):
            reserve = sum(estimate_tokens(m["content"]) for m in feedback)
            context = self._builder.build(
                mode=AssistantMode.EDIT,
                system_prompt=self._prompts.edit,
                request=request,
                index=index,
                project_name=workspace.root.name,
                history=history,
                change_sets=change_sets,
                attached_paths=attached,
                output_tokens=self._settings.edit_tokens,
                reserve_tokens=reserve,
            )
            if attempt == 1:
                yield self._context_event(context)
            outcome = yield from self._stream(
                context.messages + feedback, self._settings.edit_tokens, cancel
            )
            total_seconds += outcome.seconds
            for key, value in outcome.usage.items():
                usage_total[key] = usage_total.get(key, 0) + value
            record: Dict[str, Any] = {"reply": outcome.text}
            attempts.append(record)
            if outcome.cancelled or outcome.error:
                break

            parsed = parse_edit_blocks(outcome.text)
            problems: List[EditProblem]
            if parsed.found_any:
                changes, apply_problems = apply_edit_blocks(
                    parsed.blocks, workspace.read_text, workspace.normalize
                )
                problems = parsed.problems + apply_problems
            else:
                full_files = [c.path for c in context.included if c.full]
                changes = whole_file_edits(
                    outcome.text, full_files, workspace.read_text, workspace.normalize
                ) or definition_edits(
                    outcome.text, full_files, workspace.read_text, workspace.normalize
                )
                if changes:
                    record["whole_file"] = True
                    problems = []
                elif not has_code_block(outcome.text):
                    if (
                        outcome.text.rstrip().endswith("?")
                        or attempt >= self._settings.max_edit_attempts
                    ):
                        break  # A clarifying question, or out of tries.
                    problems = [
                        EditProblem(
                            "",
                            "Your reply has no edit blocks, so nothing was changed. "
                            "Write the edit blocks for the change now. If you cannot, "
                            "ask one short question instead.",
                        )
                    ]
                else:
                    problems = [
                        EditProblem(
                            "",
                            "You wrote code without edit blocks, so nothing could be "
                            "applied. Write the change as SEARCH/REPLACE edit blocks, "
                            "exactly in the format from the instructions.",
                        )
                    ]
            if not problems and not changes:
                problems = [EditProblem("", "The edits do not change anything.")]
            if problems:
                record["problems"] = [
                    {"path": p.path, "message": p.message} for p in problems
                ]
                if attempt < self._settings.max_edit_attempts:
                    reason = (
                        f"{len(problems)} edit(s) could not be applied: "
                        + problems[0].message
                    )
                    yield {"type": "attempt", "number": attempt + 1, "reason": reason}
                    feedback = [
                        {"role": "assistant", "content": outcome.text},
                        {"role": "user", "content": format_problems(problems)},
                    ]
                continue

            yield {"type": "status", "text": "Checking the change..."}
            verification = self._verifier.verify(index, changes)
            if not verification.passed and attempt < self._settings.max_edit_attempts:
                record["verification"] = verification.to_dict()
                first = verification.errors[0]
                yield {
                    "type": "attempt",
                    "number": attempt + 1,
                    "reason": f"the change would introduce {len(verification.errors)} "
                    f"error(s), e.g. {first.path}: {first.message}",
                }
                feedback = [
                    {"role": "assistant", "content": outcome.text},
                    {"role": "user", "content": format_verification(verification)},
                ]
                continue

            now = _now()
            change_set = ChangeSet(
                id=_new_id(),
                conversation_id=conversation.id,
                message_id="",
                status=ChangeSetStatus.PENDING,
                summary=summarize_plan(outcome.text, changes),
                files=changes,
                verification=verification,
                check=None,
                created_at=now,
                updated_at=now,
            )
            break

        metadata = self._reply_metadata(context, outcome) if context else {}
        metadata["attempts"] = attempts
        metadata["seconds"] = round(total_seconds, 1)
        if usage_total:
            metadata["usage"] = usage_total
        if change_set is None and attempts and attempts[-1].get("problems"):
            metadata["edit_failed"] = True
        message = Message(
            _new_id(),
            conversation.id,
            MessageRole.ASSISTANT,
            AssistantMode.EDIT,
            outcome.text,
            metadata,
            _now(),
        )
        if change_set is not None:
            change_set = replace(change_set, message_id=message.id)
            message = replace(
                message, metadata={**metadata, "change_set_id": change_set.id}
            )
            self._store.save_change_set(change_set)
        self._store.add_message(message)

        if outcome.error:
            yield {"type": "error", "detail": outcome.error}
        elif metadata.get("edit_failed"):
            yield {
                "type": "error",
                "detail": "The model could not produce edits that apply cleanly after "
                f"{len(attempts)} tries. Try naming the file with @path, or a smaller request.",
            }
        yield {"type": "message", "message": message.to_dict()}
        if change_set is not None:
            yield {"type": "change_set", "change_set": change_set.to_dict()}
        return _EditOutcome(
            outcome.text,
            change_set,
            message,
            stopped=outcome.cancelled or bool(outcome.error),
        )

    # ── Checks ─────────────────────────────────────────────────────────────

    def run_check(
        self, conversation: Conversation, workspace: ProjectWorkspace
    ) -> Tuple[CheckResult, Message]:
        """
        Runs the conversation's check command and stores the result as a
        message, so the model sees it in later turns.

        Args:
            conversation (Conversation): The conversation (with a check command).
            workspace (ProjectWorkspace): Its project.

        Returns:
            Tuple[CheckResult, Message]: The result and the stored message.
        """
        result = self._checks.run(
            conversation.check_command,
            Path(workspace.root),
            self._settings.check_timeout,
        )
        message = Message(
            _new_id(),
            conversation.id,
            MessageRole.CHECK,
            AssistantMode.EDIT,
            check_summary(result),
            {"check": result.to_dict()},
            _now(),
        )
        self._store.add_message(message)
        return result, message

    # ── Helpers ────────────────────────────────────────────────────────────

    def _change_sets(self, conversation_id: str) -> Dict[str, ChangeSet]:
        return {c.id: c for c in self._store.list_change_sets(conversation_id)}

    def _stream(
        self, messages: List[Dict[str, str]], max_tokens: int, cancel: threading.Event
    ) -> Generator[Event, None, _StreamOutcome]:
        outcome = _StreamOutcome()
        parts: List[str] = []
        started = time.perf_counter()
        try:
            stream = self._router.stream_chat(
                messages,
                model=self._settings.model or None,
                temperature=self._settings.temperature,
                max_tokens=max_tokens,
                options={"num_ctx": self._settings.context_tokens},
            )
            try:
                for chunk in stream:
                    if cancel.is_set():
                        outcome.cancelled = True
                        break
                    if chunk.text:
                        parts.append(chunk.text)
                        yield {"type": "token", "text": chunk.text}
                    if chunk.done:
                        outcome.usage = dict(chunk.usage)
            finally:
                close = getattr(stream, "close", None)
                if callable(close):
                    close()
        except GenerationError as e:
            logger.error(f"Model call failed: {e}")
            outcome.error = f"The model call failed: {e}"
        outcome.text = "".join(parts)
        outcome.seconds = time.perf_counter() - started
        return outcome

    @staticmethod
    def _context_event(context: BuiltContext) -> Event:
        return {
            "type": "context",
            "included": [c.to_dict() for c in context.included],
            "prompt_tokens": context.prompt_tokens,
            "referenced": context.referenced_paths,
        }

    def _reply_metadata(
        self, context: BuiltContext, outcome: _StreamOutcome
    ) -> Dict[str, Any]:
        metadata: Dict[str, Any] = {
            "context": [c.to_dict() for c in context.included],
            "prompt_tokens": context.prompt_tokens,
            "seconds": round(outcome.seconds, 1),
        }
        if outcome.usage:
            metadata["usage"] = outcome.usage
        if outcome.cancelled:
            metadata["cancelled"] = True
        if outcome.error:
            metadata["error"] = outcome.error
        if self._settings.model:
            metadata["model"] = self._settings.model
        return metadata
