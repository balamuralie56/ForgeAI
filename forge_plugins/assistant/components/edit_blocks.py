"""
Parses and applies the SEARCH/REPLACE edit blocks the assistant writes:

    path/to/file.py
    <<<<<<< SEARCH
    lines copied from the current file
    =======
    the new lines
    >>>>>>> REPLACE

Small local models get this format slightly wrong in predictable ways
(code fences around blocks, decorated file names, different indentation or
trailing whitespace, missing blank lines), so parsing and matching tolerate
those - but never guess: an edit that matches more than one place, or none,
is reported back with enough detail for the model to correct it.
"""

import ast
import difflib
import re
from dataclasses import dataclass
from typing import Callable, Collection, Dict, List, Optional, Sequence, Tuple

from ..exceptions import UnsafePathError
from ..models import FileChange

_HEAD = re.compile(r"^\s*<{5,9}\s*SEARCH\s*$")
_DIVIDER = re.compile(r"^\s*={5,9}\s*$")
_TAIL = re.compile(r"^\s*>{5,9}\s*REPLACE\s*$")
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")
_PATH_TOKEN = re.compile(r"[\w.\-/\\]*[\w\-]\.[A-Za-z0-9]{1,10}\b|[\w.\-]+/[\w.\-/]+")
_DECORATION = re.compile(
    r"^(?:#+\s*|\*+\s*|-\s+|>\s*|`+)?(?:(?:file(?:name)?|path)\s*:\s*)?", re.I
)
# Lines a model writes to skip code it didn't want to repeat. In REPLACE
# they would delete that code, so they are rejected.
_ELISION = re.compile(
    r"^\s*(?:#|//|/\*|<!--|\*)?\s*\.{3}\s*(?:\(?\s*(?:rest|existing|remaining|other|same|unchanged|previous)\b.*)?$"
    r"|^\s*(?:#|//)\s*(?:rest of|existing|remaining|unchanged|other)\b.*(?:code|unchanged|here|same|methods|functions)\b.*$",
    re.I,
)


@dataclass(frozen=True)
class EditBlock:
    """
    One parsed edit.

    Attributes:
        path (str): File path as the model wrote it.
        search (str): Lines to find (empty to create a file).
        replace (str): Lines to put in their place.
    """

    path: str
    search: str
    replace: str


@dataclass(frozen=True)
class EditProblem:
    """
    Why an edit could not be parsed or applied.

    Attributes:
        path (str): The file concerned ("" if unknown).
        message (str): What went wrong, phrased for the model to act on.
        hint (str): Extra context, e.g. the closest matching lines.
    """

    path: str
    message: str
    hint: str = ""


@dataclass(frozen=True)
class ParsedEdits:
    """Edit blocks found in a reply, and problems with malformed ones."""

    blocks: List[EditBlock]
    problems: List[EditProblem]

    @property
    def found_any(self) -> bool:
        """True when the reply tried to edit something."""
        return bool(self.blocks or self.problems)


def parse_edit_blocks(text: str) -> ParsedEdits:
    """
    Finds every SEARCH/REPLACE block in a model reply.

    Args:
        text (str): The model's reply.

    Returns:
        ParsedEdits: Well-formed blocks, plus a problem for each malformed one.
    """
    lines = text.replace("\r\n", "\n").split("\n")
    blocks: List[EditBlock] = []
    problems: List[EditProblem] = []
    current_path: Optional[str] = None
    i = 0
    while i < len(lines):
        if not _HEAD.match(lines[i]):
            i += 1
            continue
        path = _find_path(lines, i) or current_path
        i += 1
        search: List[str] = []
        while i < len(lines) and not (
            _DIVIDER.match(lines[i]) or _HEAD.match(lines[i]) or _TAIL.match(lines[i])
        ):
            search.append(lines[i])
            i += 1
        if i >= len(lines) or not _DIVIDER.match(lines[i]):
            problems.append(
                EditProblem(
                    path or "",
                    "An edit block is missing its ======= line between SEARCH and REPLACE.",
                )
            )
            continue
        i += 1
        replace: List[str] = []
        while i < len(lines) and not (_TAIL.match(lines[i]) or _HEAD.match(lines[i])):
            replace.append(lines[i])
            i += 1
        if i >= len(lines) or not _TAIL.match(lines[i]):
            problems.append(
                EditProblem(
                    path or "",
                    "An edit block is missing its >>>>>>> REPLACE line"
                    + (
                        " (the reply probably hit the length limit; make smaller edits)."
                        if i >= len(lines)
                        else "."
                    ),
                )
            )
            continue
        i += 1
        if path is None:
            problems.append(
                EditProblem(
                    "",
                    "An edit block has no file path. Write the file path on the line "
                    "just before <<<<<<< SEARCH.",
                )
            )
            continue
        blocks.append(EditBlock(path, "\n".join(search), "\n".join(replace)))
        current_path = path
    return ParsedEdits(blocks, problems)


def _find_path(lines: Sequence[str], head_index: int) -> Optional[str]:
    """Finds the file path written just above a SEARCH marker."""
    checked = 0
    j = head_index - 1
    while j >= 0 and checked < 3:
        line = lines[j].strip()
        j -= 1
        if not line:
            continue
        fence = _FENCE.match(line)
        if fence:
            info = fence.group(2).strip()
            candidate = _path_from(info) if info else None
            if candidate:
                return candidate
            continue
        checked += 1
        candidate = _path_from(line)
        if candidate:
            return candidate
        if _TAIL.match(line):
            return None
    return None


def _path_from(line: str) -> Optional[str]:
    cleaned = _DECORATION.sub("", line.strip()).strip().strip("`*:").strip()
    if not cleaned:
        return None
    if " " not in cleaned and ("." in cleaned or "/" in cleaned):
        return cleaned
    matches = _PATH_TOKEN.findall(cleaned)
    return matches[-1].strip("`*:") if matches else None


# ── Applying ───────────────────────────────────────────────────────────────


def apply_edit_blocks(
    blocks: Sequence[EditBlock],
    read_file: Callable[[str], Optional[str]],
    normalize_path: Callable[[str], str],
) -> Tuple[List[FileChange], List[EditProblem]]:
    """
    Applies edit blocks in order to in-memory copies of the files. Nothing
    is written to disk.

    Args:
        blocks (Sequence[EditBlock]): Parsed edits.
        read_file (Callable[[str], Optional[str]]): Returns a file's current
            content by normalized path, or None if it does not exist.
        normalize_path (Callable[[str], str]): Validates and normalizes a
            path; raises UnsafePathError for paths outside the project.

    Returns:
        Tuple[List[FileChange], List[EditProblem]]: The resulting file
        changes (in first-edited order, unchanged files dropped) and a
        problem for every edit that could not be applied.
    """
    originals: Dict[str, Optional[str]] = {}
    current: Dict[str, Optional[str]] = {}
    order: List[str] = []
    problems: List[EditProblem] = []

    for block in blocks:
        try:
            path = normalize_path(block.path)
        except UnsafePathError as e:
            problems.append(EditProblem(block.path, str(e)))
            continue
        if path not in current:
            content = read_file(path)
            originals[path] = content
            current[path] = content
            order.append(path)

        elision = _elision_line(block.search, block.replace)
        if elision is not None:
            problems.append(
                EditProblem(
                    path,
                    f"REPLACE contains '{elision.strip()}' instead of real code. "
                    "Write out every line that should be in the file; anything "
                    "left out would be deleted.",
                )
            )
            continue

        existing = current[path]
        if not block.search.strip():
            if existing is not None and existing.strip():
                problems.append(
                    EditProblem(
                        path,
                        f"{path} already exists, so SEARCH cannot be empty. Copy the "
                        "exact lines you want to change into SEARCH.",
                    )
                )
                continue
            new_content = block.replace
            current[path] = (
                new_content if new_content.endswith("\n") else new_content + "\n"
            )
            continue

        if _trim_blank_edges(block.search.split("\n")) == _trim_blank_edges(
            block.replace.split("\n")
        ):
            # Small models often restate unchanged files as no-op blocks;
            # they change nothing, so they are skipped rather than failed.
            continue
        if existing is None:
            problems.append(
                EditProblem(
                    path,
                    f"{path} does not exist. To create a new file, leave SEARCH empty.",
                )
            )
            continue
        updated, problem = replace_once(existing, block.search, block.replace)
        if problem is not None:
            problems.append(EditProblem(path, problem[0], problem[1]))
            continue
        current[path] = updated

    changes = []
    for path in order:
        updated_content = current[path]
        if updated_content is None or updated_content == originals[path]:
            continue
        changes.append(FileChange(path, originals[path], updated_content))
    return changes, problems


def _elision_line(search: str, replace: str) -> Optional[str]:
    search_lines = {line.strip() for line in search.split("\n")}
    for line in replace.split("\n"):
        if _ELISION.match(line) and line.strip() not in search_lines:
            return line
    return None


def _trim_blank_edges(lines: List[str]) -> List[str]:
    start, end = 0, len(lines)
    while start < end and not lines[start].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1
    return lines[start:end]


def _indent(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def replace_once(
    content: str, search: str, replace: str
) -> Tuple[str, Optional[Tuple[str, str]]]:
    """
    Replaces the single place in `content` that matches `search`.

    Matching is tried exactly, then ignoring trailing whitespace, then
    ignoring a consistent indentation difference (re-indenting REPLACE to
    match), then ignoring blank lines. The first strategy that finds exactly
    one match wins.

    Args:
        content (str): Current file content.
        search (str): Lines to find.
        replace (str): Lines to substitute.

    Returns:
        Tuple[str, Optional[Tuple[str, str]]]: The new content and None, or
        the unchanged content and a (message, hint) problem.
    """
    file_lines = content.split("\n")
    search_lines = _trim_blank_edges(search.split("\n"))
    replace_lines = _trim_blank_edges(replace.split("\n"))
    if not search_lines:
        return content, ("SEARCH is empty.", "")
    if search_lines == replace_lines:
        return content, (
            "SEARCH and REPLACE are identical, so the edit changes nothing.",
            "",
        )

    count = len(search_lines)
    strategies: List[Callable[[], List[Tuple[int, int, List[str]]]]] = [
        lambda: [
            (i, i + count, replace_lines)
            for i in range(len(file_lines) - count + 1)
            if file_lines[i : i + count] == search_lines
        ],
        lambda: [
            (i, i + count, replace_lines)
            for i in range(len(file_lines) - count + 1)
            if [x.rstrip() for x in file_lines[i : i + count]]
            == [x.rstrip() for x in search_lines]
        ],
        lambda: _indent_matches(file_lines, search_lines, replace_lines),
        lambda: _blank_insensitive_matches(file_lines, search_lines, replace_lines),
    ]
    for strategy in strategies:
        matches = strategy()
        if len(matches) == 1:
            start, end, new_lines = matches[0]
            return "\n".join(file_lines[:start] + new_lines + file_lines[end:]), None
        if len(matches) > 1:
            return content, (
                f"SEARCH matches {len(matches)} places. Include a few more of the "
                "surrounding lines so it matches exactly one.",
                "",
            )
    return content, (
        "SEARCH does not match the file. It must copy the current lines exactly.",
        _closest_lines(file_lines, search_lines),
    )


def _indent_shift(file_line: str, search_line: str) -> Optional[Tuple[str, int]]:
    """
    The indentation change that turns `search_line` into `file_line`:
    ("", 0) for none, (prefix, 1) to add a prefix, (prefix, -1) to remove one,
    or None when the two indents are unrelated (e.g. tabs vs spaces).
    """
    f_indent, s_indent = _indent(file_line), _indent(search_line)
    if f_indent == s_indent:
        return ("", 0)
    if f_indent.endswith(s_indent):
        return (f_indent[: len(f_indent) - len(s_indent)], 1)
    if s_indent.endswith(f_indent):
        return (s_indent[: len(s_indent) - len(f_indent)], -1)
    return None


def _indent_matches(
    file_lines: List[str], search_lines: List[str], replace_lines: List[str]
) -> List[Tuple[int, int, List[str]]]:
    count = len(search_lines)
    stripped = [s.strip() for s in search_lines]
    matches = []
    for i in range(len(file_lines) - count + 1):
        window = file_lines[i : i + count]
        if [w.strip() for w in window] != stripped:
            continue
        shifts = {
            _indent_shift(file_line, search_line)
            for file_line, search_line in zip(window, search_lines)
            if search_line.strip()
        }
        if len(shifts) != 1 or None in shifts:
            continue
        matches.append((i, i + count, _reindent(replace_lines, shifts.pop())))
    return matches


def _reindent(lines: List[str], shift: Optional[Tuple[str, int]]) -> List[str]:
    if shift is None or not shift[0]:
        return list(lines)
    prefix, direction = shift
    if direction > 0:
        return [prefix + line if line.strip() else line for line in lines]
    return [
        line[len(prefix) :] if line.startswith(prefix) else line.lstrip()
        for line in lines
    ]


def _blank_insensitive_matches(
    file_lines: List[str], search_lines: List[str], replace_lines: List[str]
) -> List[Tuple[int, int, List[str]]]:
    wanted = [s.strip() for s in search_lines if s.strip()]
    if not wanted:
        return []
    first_search = next(s for s in search_lines if s.strip())
    non_blank = [(i, line.strip()) for i, line in enumerate(file_lines) if line.strip()]
    matches = []
    for k in range(len(non_blank) - len(wanted) + 1):
        if [text for _, text in non_blank[k : k + len(wanted)]] != wanted:
            continue
        start = non_blank[k][0]
        end = non_blank[k + len(wanted) - 1][0] + 1
        shift = _indent_shift(file_lines[start], first_search)
        matches.append((start, end, _reindent(replace_lines, shift)))
    return matches


def _closest_lines(file_lines: List[str], search_lines: List[str]) -> str:
    """Shows the region of the file most similar to a failed SEARCH."""
    count = len(search_lines)
    if not file_lines or count == 0:
        return ""
    target = "\n".join(s.strip() for s in search_lines)
    best_ratio, best_start = 0.0, 0
    step = 1 if len(file_lines) < 3000 else 3
    for i in range(0, max(1, len(file_lines) - count + 1), step):
        window = "\n".join(s.strip() for s in file_lines[i : i + count])
        ratio = difflib.SequenceMatcher(
            None, target, window, autojunk=False
        ).quick_ratio()
        if ratio <= best_ratio:
            continue
        ratio = difflib.SequenceMatcher(None, target, window, autojunk=False).ratio()
        if ratio > best_ratio:
            best_ratio, best_start = ratio, i
    if best_ratio < 0.4:
        return ""
    end = min(len(file_lines), best_start + max(count, 3) + 2)
    start = max(0, best_start - 1)
    shown = "\n".join(file_lines[start:end])
    return f"The closest lines in the file are (lines {start + 1}-{end}):\n{shown}"


# -- Whole-file replies -------------------------------------------------------
#
# Small models sometimes ignore the edit-block format and answer with the
# complete new file in a code block instead. That is a usable edit when the
# file was shown whole and nothing that existed is dropped; anything less
# certain is rejected so the model is asked again for proper edit blocks.

_HEADER_PATH = re.compile(r"^#{1,6}\s+(\S+)")


def has_code_block(text: str) -> bool:
    """True when a reply contains a fenced code block."""
    return any(_FENCE.match(line) for line in text.split("\n"))


def _top_level_keys(path: str, content: str) -> Optional[set]:
    """
    What a Python file defines at module level - its docstring, imports,
    assigned names, functions and classes. None for other files or bad syntax.
    """
    if not path.endswith(".py"):
        return None
    try:
        tree = ast.parse(content)
    except (SyntaxError, ValueError):
        return None
    keys = set()
    for index, node in enumerate(tree.body):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            keys.add(("def", node.name))
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            keys.update(("import", alias.asname or alias.name) for alias in node.names)
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                keys.update(
                    ("name", leaf.id)
                    for leaf in ast.walk(target)
                    if isinstance(leaf, ast.Name)
                )
        elif (
            index == 0
            and isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            keys.add(("docstring", ""))
    return keys


def _keeps_existing_code(path: str, original: str, updated: str) -> bool:
    keys = _top_level_keys(path, original)
    if keys is not None:
        new_keys = _top_level_keys(path, updated)
        return new_keys is not None and keys <= new_keys
    original_lines = {line.strip() for line in original.split("\n") if line.strip()}
    if not original_lines:
        return True
    updated_lines = {line.strip() for line in updated.split("\n")}
    return len(original_lines & updated_lines) >= 0.8 * len(original_lines)


def _best_matching_file(
    body: Sequence[str],
    candidates: Collection[str],
    read_file: Callable[[str], Optional[str]],
) -> Optional[str]:
    """
    For a code block that names no file: the one shown file whose lines it
    mostly restates (at least 60%), or None if no file - or more than one -
    fits.
    """
    block_lines = {line.strip() for line in body if line.strip()}
    if not block_lines:
        return None
    scored = []
    for path in candidates:
        content = read_file(path)
        if not content:
            continue
        original = {line.strip() for line in content.split("\n") if line.strip()}
        if original:
            scored.append((len(original & block_lines) / len(original), path))
    scored.sort(reverse=True)
    if not scored or scored[0][0] < 0.6:
        return None
    if len(scored) > 1 and scored[1][0] >= 0.6:
        return None
    return scored[0][1]


def whole_file_edits(
    reply: str,
    full_files: Sequence[str],
    read_file: Callable[[str], Optional[str]],
    normalize_path: Callable[[str], str],
) -> List[FileChange]:
    """
    Interprets code blocks that restate a whole file as edits to that file.

    A code block counts only if the line just before it (or its fence info)
    names a file that was shown to the model in full, and the new content
    keeps every top-level function and class the file already had (or, for
    non-Python files, at least 80% of its lines).

    Args:
        reply (str): The model's reply.
        full_files (Sequence[str]): Paths the model was shown in full.
        read_file (Callable[[str], Optional[str]]): Current file content.
        normalize_path (Callable[[str], str]): Path validation.

    Returns:
        List[FileChange]: The changes, or an empty list if any block is unsafe.
    """
    allowed = set(full_files)
    lines = reply.replace("\r\n", "\n").split("\n")
    changes: Dict[str, FileChange] = {}
    i = 0
    while i < len(lines):
        fence = _FENCE.match(lines[i])
        if not fence:
            i += 1
            continue
        marker = fence.group(1)
        path = _path_from(fence.group(2)) if fence.group(2).strip() else None
        j = i - 1
        while path is None and j >= 0 and i - j <= 3:
            candidate = lines[j].strip()
            j -= 1
            if not candidate:
                continue
            header = _HEADER_PATH.match(candidate)
            path = _path_from(header.group(1) if header else candidate)
            break
        body: List[str] = []
        i += 1
        while i < len(lines) and not lines[i].strip().startswith(marker[:3]):
            body.append(lines[i])
            i += 1
        i += 1
        if path is None:
            path = _best_matching_file(body, allowed, read_file)
        if path is None:
            continue
        try:
            normalized = normalize_path(path)
        except UnsafePathError:
            return []
        if normalized not in allowed:
            continue
        original = read_file(normalized)
        if original is None:
            continue
        updated = "\n".join(body).rstrip("\n") + "\n"
        if updated == original or not _keeps_existing_code(
            normalized, original, updated
        ):
            return []
        changes[normalized] = FileChange(normalized, original, updated)
    return list(changes.values())
