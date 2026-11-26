"""
Builds the prompt for one assistant request within the model's context
window: the most relevant code (whole files when the model must edit them,
focused excerpts otherwise), a compact map of the project, and recent
conversation turns - in that order of priority.

Small local models have small windows (a few thousand tokens), and a prompt
that overflows the window is silently truncated from the start, losing the
instructions. So every section is budgeted with a conservative token
estimate, and nothing is added that does not fit.
"""

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Dict, List, Optional, Sequence, Set, Tuple

from ..models import AssistantMode, ChangeSet, Message, MessageRole
from .code_index import CodeIndex, SearchHit, fence_language
from .edit_blocks import parse_edit_blocks

_HISTORY_SHARE = 0.2
_MAP_SHARE = 0.1
_MAX_HISTORY_MESSAGES = 8
_MAX_HISTORY_MESSAGE_CHARS = 1800
_MAX_EDIT_FILES = 4
_FULL_FILE_SHARE = 0.6
_SMALL_FILE_LINES = 200
_SMALL_FILE_SHARE = 0.35
_MERGE_GAP_LINES = 3
_SAFETY_TOKENS = 200

_MENTION = re.compile(r"@([\w./\\-]+)")
_PATHLIKE = re.compile(r"(?<![\w@/])([\w.\-]+(?:/[\w.\-]+)*\.[A-Za-z0-9]{1,8})\b")


def estimate_tokens(text: str) -> int:
    """
    Conservatively estimates a text's token count (about 3 characters per
    token for code; real tokenizers average 3.5-4, so this over-counts).
    """
    return len(text) // 3 + 1


@dataclass(frozen=True)
class IncludedCode:
    """
    A piece of a file that was put in the prompt.

    Attributes:
        path (str): Project-relative path.
        start_line (int): First line shown.
        end_line (int): Last line shown.
        total_lines (int): Lines in the whole file.
    """

    path: str
    start_line: int
    end_line: int
    total_lines: int

    @property
    def full(self) -> bool:
        """True when the whole file was shown."""
        return self.start_line == 1 and self.end_line >= self.total_lines

    def to_dict(self) -> Dict[str, object]:
        """Serializes the range to a plain dictionary."""
        return {
            "path": self.path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "total_lines": self.total_lines,
            "full": self.full,
        }


@dataclass(frozen=True)
class BuiltContext:
    """
    The prompt for one request.

    Attributes:
        messages (List[Dict[str, str]]): Chat messages for the model.
        included (List[IncludedCode]): The code that made it into the prompt.
        prompt_tokens (int): Estimated prompt size.
        referenced_paths (List[str]): Files the user referred to explicitly.
    """

    messages: List[Dict[str, str]]
    included: List[IncludedCode] = field(default_factory=list)
    prompt_tokens: int = 0
    referenced_paths: List[str] = field(default_factory=list)


def find_referenced_paths(text: str, index: CodeIndex) -> List[str]:
    """
    Finds the project files a request refers to: `@path` mentions (which
    may be partial, e.g. `@service.py`) and bare file names or paths that
    resolve to exactly one file.

    Args:
        text (str): The user's request.
        index (CodeIndex): The project index.

    Returns:
        List[str]: Referenced paths in order of appearance, without duplicates.
    """
    # Tracebacks on Windows write paths with backslashes.
    text = text.replace("\\", "/")
    found: List[str] = []
    for mention in _MENTION.findall(text):
        found.extend(index.find_paths(mention)[:3])
    for candidate in _PATHLIKE.findall(text):
        matches = index.find_paths(candidate)
        if len(matches) == 1:
            found.append(matches[0])
    # Full project paths anywhere in the text, e.g. inside an absolute path
    # in a traceback ("C:/work/app/todo/store.py", line 29).
    for path in index.paths():
        if "/" not in path:
            continue
        start = text.find(path)
        while start >= 0:
            before = text[start - 1] if start > 0 else " "
            after_index = start + len(path)
            after = text[after_index] if after_index < len(text) else " "
            if not (before.isalnum() or before in "_.-") and not (
                after.isalnum() or after == "_"
            ):
                found.append(path)
                break
            start = text.find(path, start + 1)
    seen: Set[str] = set()
    ordered = []
    for path in found:
        if path not in seen:
            seen.add(path)
            ordered.append(path)
    return ordered


class ContextBuilder:
    """Assembles budgeted prompts from the project index and conversation."""

    def __init__(self, context_tokens: int) -> None:
        """
        Args:
            context_tokens (int): The model's context window, in tokens.
        """
        self._context_tokens = context_tokens

    def build(
        self,
        *,
        mode: AssistantMode,
        system_prompt: str,
        request: str,
        index: CodeIndex,
        project_name: str,
        history: Sequence[Message],
        change_sets: Dict[str, ChangeSet],
        attached_paths: Sequence[str] = (),
        output_tokens: int,
        reserve_tokens: int = 0,
    ) -> BuiltContext:
        """
        Builds the prompt messages for a request.

        Args:
            mode (AssistantMode): Ask (excerpts) or edit (whole files to edit).
            system_prompt (str): Instructions for the mode.
            request (str): The user's request.
            index (CodeIndex): Refreshed project index.
            project_name (str): Folder name shown to the model.
            history (Sequence[Message]): Earlier messages, oldest first.
            change_sets (Dict[str, ChangeSet]): Change sets by id, to describe
                past edits by outcome instead of repeating their edit blocks.
            attached_paths (Sequence[str]): Files the user attached.
            output_tokens (int): Room kept free for the reply.
            reserve_tokens (int): Extra room kept free (e.g. for a retry's
                previous reply and feedback, appended by the caller).

        Returns:
            BuiltContext: Messages and what they contain.
        """
        referenced = list(
            dict.fromkeys(list(attached_paths) + find_referenced_paths(request, index))
        )
        available = (
            self._context_tokens
            - output_tokens
            - reserve_tokens
            - estimate_tokens(system_prompt)
            - estimate_tokens(request)
            - _SAFETY_TOKENS
        )
        available = max(available, 0)

        history_messages = self._history(
            history, change_sets, int(available * _HISTORY_SHARE), request
        )
        used = sum(estimate_tokens(m["content"]) for m in history_messages)

        query = request + "\n" + " ".join(referenced)
        hits = index.search(query, limit=40, boost_paths=referenced)
        ranked_files = list(dict.fromkeys(referenced + index.rank_files(hits)))

        map_text = self._project_map(index, ranked_files, int(available * _MAP_SHARE))
        used += estimate_tokens(map_text)

        code_budget = max(available - used, 0)
        if mode is AssistantMode.EDIT:
            # When the user names the files to change, show only those: small
            # models follow the edit format far worse as the prompt grows,
            # and the project map still tells them what else exists.
            # A request that only names tests ("make @test_x.py pass") still
            # needs the code under test, so it keeps the ranked files.
            only_tests = bool(referenced) and all(_is_test_path(p) for p in referenced)
            edit_files = referenced if referenced and not only_tests else ranked_files
            sections, included = self._edit_code(index, edit_files, hits, code_budget)
        else:
            sections, included = self._ask_code(index, referenced, hits, code_budget)

        parts = [f"Project: {project_name} ({len(index.paths())} files)"]
        if map_text:
            parts.append("## Project map\n" + map_text)
        if sections:
            heading = (
                "## Code you can edit"
                if mode is AssistantMode.EDIT
                else "## Relevant code"
            )
            parts.append(heading + "\n\n" + "\n\n".join(sections))
        else:
            parts.append("## Relevant code\nNo project code matched this request.")
        parts.append("## Request\n" + request.strip())
        final_user = "\n\n".join(parts)

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history_messages)
        messages.append({"role": "user", "content": final_user})
        prompt_tokens = sum(estimate_tokens(m["content"]) for m in messages)
        return BuiltContext(messages, included, prompt_tokens, referenced)

    # ── History ────────────────────────────────────────────────────────────

    def _history(
        self,
        history: Sequence[Message],
        change_sets: Dict[str, ChangeSet],
        budget: int,
        request: str = "",
    ) -> List[Dict[str, str]]:
        rendered: List[Dict[str, str]] = []
        used = 0
        current = request.strip()
        for message in reversed(list(history)[-_MAX_HISTORY_MESSAGES:]):
            # Small models copy their earlier replies, so an earlier try at
            # this same request (and its reply) is left out entirely.
            if message.role is MessageRole.USER and message.content.strip() == current:
                continue
            entry = self._render_history_message(message, change_sets)
            if entry is None:
                continue
            if (
                rendered
                and entry["role"] == "assistant"
                and rendered[-1]["role"] == "assistant"
            ):
                continue
            cost = estimate_tokens(entry["content"])
            if used + cost > budget:
                break
            rendered.append(entry)
            used += cost
        rendered.reverse()
        # A conversation must not resume with a dangling assistant turn.
        while rendered and rendered[0]["role"] == "assistant":
            rendered.pop(0)
        return rendered

    @staticmethod
    def _render_history_message(
        message: Message, change_sets: Dict[str, ChangeSet]
    ) -> Optional[Dict[str, str]]:
        content = message.content.strip()
        if message.role is MessageRole.CHECK:
            result = message.metadata.get("check") or {}
            status = "passed" if result.get("passed") else "failed"
            output = str(result.get("output", ""))[-1500:]
            return {
                "role": "user",
                "content": f"(The check command `{result.get('command', '')}` {status}.)\n"
                + (f"```\n{output}\n```" if output else ""),
            }
        if message.role is MessageRole.ASSISTANT:
            change_set_id = message.metadata.get("change_set_id")
            if message.mode is AssistantMode.EDIT and not change_set_id:
                # A change attempt that produced nothing usable only teaches
                # the model to repeat it.
                return None
            if parse_edit_blocks(content).found_any:
                plan = content.split("<<<<<<<", 1)[0]
                plan = "\n".join(
                    line
                    for line in plan.splitlines()
                    if not line.strip().startswith("```")
                ).strip()
                change_set = change_sets.get(change_set_id) if change_set_id else None
                if change_set is not None:
                    files = ", ".join(f.path for f in change_set.files)
                    outcome = f"(I proposed changes to {files}; the user {_status_phrase(change_set.status.value)}.)"
                else:
                    outcome = "(My edits could not be applied.)"
                content = f"{plan}\n{outcome}".strip()
            content = _strip_code(content)
            if not content:
                return None
            if len(content) > _MAX_HISTORY_MESSAGE_CHARS:
                content = content[:_MAX_HISTORY_MESSAGE_CHARS] + "\n[...]"
            return {"role": "assistant", "content": content}
        if not content:
            return None
        if len(content) > _MAX_HISTORY_MESSAGE_CHARS:
            content = content[:_MAX_HISTORY_MESSAGE_CHARS] + "\n[...]"
        return {"role": "user", "content": content}

    # ── Project map ────────────────────────────────────────────────────────

    @staticmethod
    def _project_map(index: CodeIndex, ranked_files: Sequence[str], budget: int) -> str:
        if budget <= 0:
            return ""
        all_paths = index.paths()
        ordered = list(dict.fromkeys(list(ranked_files) + all_paths))
        lines: List[str] = []
        used = 0
        detailed = set(ranked_files[:15])
        for path in ordered:
            names = []
            if path in detailed:
                names = [
                    entry.strip()
                    for entry in index.outline(path)
                    if not entry.startswith("    ")
                ][:8]
            line = f"{path}: {', '.join(names)}" if names else path
            cost = estimate_tokens(line) + 1
            if used + cost > budget:
                remaining = len(ordered) - len(lines)
                if remaining > 0:
                    lines.append(f"... and {remaining} more files")
                break
            lines.append(line)
            used += cost
        return "\n".join(lines)

    # ── Code sections ──────────────────────────────────────────────────────

    def _edit_code(
        self,
        index: CodeIndex,
        ranked_files: Sequence[str],
        hits: Sequence[SearchHit],
        budget: int,
    ) -> Tuple[List[str], List[IncludedCode]]:
        sections: List[str] = []
        included: List[IncludedCode] = []
        used = 0
        for path in ranked_files[:_MAX_EDIT_FILES]:
            content = index.content(path)
            if content is None:
                continue
            total = content.count("\n") + 1
            remaining = budget - used
            full_cost = estimate_tokens(content) + 30
            # The most relevant file may use the whole budget; later ones
            # must leave room, falling back to excerpts when they can't.
            limit = (
                remaining if not sections else min(remaining, budget * _FULL_FILE_SHARE)
            )
            if full_cost <= limit:
                sections.append(_render(path, content, 1, total, total))
                included.append(IncludedCode(path, 1, total, total))
                used += full_cost
                continue
            ranges = _merge_ranges(
                [
                    (h.chunk.start_line, h.chunk.end_line)
                    for h in hits
                    if h.chunk.path == path
                ]
            )
            for start, end in ranges:
                text = _lines(content, start, end)
                cost = estimate_tokens(text) + 30
                if used + cost > budget:
                    break
                sections.append(_render(path, text, start, end, total))
                included.append(IncludedCode(path, start, end, total))
                used += cost
            if used >= budget:
                break
        return sections, included

    def _ask_code(
        self,
        index: CodeIndex,
        referenced: Sequence[str],
        hits: Sequence[SearchHit],
        budget: int,
    ) -> Tuple[List[str], List[IncludedCode]]:
        selected: Dict[str, List[Tuple[int, int]]] = {}
        order: List[str] = []
        used = 0

        def take(path: str, start: int, end: int, text: str) -> bool:
            nonlocal used
            cost = estimate_tokens(text) + 30
            if used + cost > budget:
                return False
            if path not in selected:
                selected[path] = []
                order.append(path)
            selected[path].append((start, end))
            used += cost
            return True

        for path in referenced:
            content = index.content(path)
            if content is None:
                continue
            total = content.count("\n") + 1
            if estimate_tokens(content) <= budget * _FULL_FILE_SHARE:
                take(path, 1, total, content)
        for hit in hits:
            chunk = hit.chunk
            if any(
                s <= chunk.start_line and chunk.end_line <= e
                for s, e in selected.get(chunk.path, [])
            ):
                continue
            # A small file is clearer whole than as excerpts: the model sees
            # every definition it might otherwise guess about.
            content = index.content(chunk.path) or ""
            total = content.count("\n") + 1
            if (
                chunk.path not in selected
                and total <= _SMALL_FILE_LINES
                and estimate_tokens(content) <= budget * _SMALL_FILE_SHARE
                and take(chunk.path, 1, total, content)
            ):
                continue
            take(chunk.path, chunk.start_line, chunk.end_line, chunk.text)

        sections: List[str] = []
        included: List[IncludedCode] = []
        for path in order:
            content = index.content(path) or ""
            total = content.count("\n") + 1
            for start, end in _merge_ranges(selected[path]):
                sections.append(
                    _render(path, _lines(content, start, end), start, end, total)
                )
                included.append(IncludedCode(path, start, end, total))
        return sections, included


_CONTEXT_HEADER = re.compile(
    r"^#{1,6}\s+\S+\s+\((?:whole file|lines \d+-\d+ of \d+[^)]*)\)\s*$"
)


def _strip_code(content: str) -> str:
    """
    Removes code blocks (and echoed context headers) from an earlier
    assistant reply before it goes back into a prompt. Old code is stale once
    files change, costs context, and small models copy its format instead of
    following the instructions for the current mode.
    """
    kept: List[str] = []
    in_code = False
    for line in content.split("\n"):
        if re.match(r"^\s*(```|~~~)", line):
            in_code = not in_code
            continue
        if in_code or _CONTEXT_HEADER.match(line.strip()):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def _is_test_path(path: str) -> bool:
    name = PurePosixPath(path).name
    return (
        name.startswith("test_")
        or name.endswith(("_test.py", ".test.ts", ".test.tsx", ".spec.ts", ".spec.js"))
        or "/tests/" in "/" + path
    )


def _status_phrase(status: str) -> str:
    return {
        "pending": "has not applied them yet",
        "applied": "applied them",
        "discarded": "discarded them",
        "reverted": "applied and then undid them",
    }.get(status, status)


def _merge_ranges(ranges: Sequence[Tuple[int, int]]) -> List[Tuple[int, int]]:
    merged: List[Tuple[int, int]] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1] + _MERGE_GAP_LINES:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _lines(content: str, start: int, end: int) -> str:
    return "\n".join(content.split("\n")[start - 1 : end])


def _render(path: str, text: str, start: int, end: int, total: int) -> str:
    if start == 1 and end >= total:
        header = f"### {path} (whole file)"
    else:
        header = (
            f"### {path} (lines {start}-{end} of {total}; only these lines are shown)"
        )
    language = fence_language(path) or PurePosixPath(path).suffix.lstrip(".")
    body = text.rstrip("\n")
    return f"{header}\n```{language}\n{body}\n```"
