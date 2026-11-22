"""
Turns Python code blocks that restate complete top-level definitions into
edits - the other common way small models ignore the edit-block format:

    ```python
    class TaskStore:
        ...every method, plus the new one...
    ```

Each function or class in the block replaces the definition of the same name
in the one shown file that has it; new definitions are appended to that
file, and imports the file lacks are added after its existing imports. A
block is rejected outright if it contains other statements, if a name
exists in several shown files, or if a restated class drops a method it had.
"""

import ast
import re
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from ..exceptions import UnsafePathError
from ..models import FileChange

_FENCE = re.compile(r"^\s*(`{3,}|~{3,})\s*([\w+#.-]*)")
_DEFINITIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
_PYTHON_FENCES = frozenset({"", "python", "py", "python3"})


def _code_blocks(reply: str) -> List[Tuple[str, str]]:
    """(language, body) of every fenced block in a reply."""
    blocks = []
    lines = reply.replace("\r\n", "\n").split("\n")
    i = 0
    while i < len(lines):
        fence = _FENCE.match(lines[i])
        if not fence:
            i += 1
            continue
        language = fence.group(2).lower()
        body: List[str] = []
        i += 1
        while i < len(lines) and not _FENCE.match(lines[i]):
            body.append(lines[i])
            i += 1
        i += 1
        blocks.append((language, "\n".join(body)))
    return blocks


def _span(node: ast.stmt) -> Tuple[int, int]:
    """1-based first and last line of a definition, including decorators."""
    decorators = getattr(node, "decorator_list", [])
    start = min([node.lineno] + [d.lineno for d in decorators])
    return start, node.end_lineno or node.lineno


def _method_names(node: ast.ClassDef) -> List[str]:
    return [
        n.name
        for n in node.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def definition_edits(
    reply: str,
    full_files: Sequence[str],
    read_file: Callable[[str], Optional[str]],
    normalize_path: Callable[[str], str],
) -> List[FileChange]:
    """
    Interprets code blocks of complete Python definitions as edits.

    Args:
        reply (str): The model's reply.
        full_files (Sequence[str]): Paths the model was shown in full.
        read_file (Callable[[str], Optional[str]]): Current file content.
        normalize_path (Callable[[str], str]): Path validation.

    Returns:
        List[FileChange]: The changes, or an empty list if any block is
        unusable (so the caller asks the model for proper edit blocks).
    """
    trees: Dict[str, ast.Module] = {}
    contents: Dict[str, str] = {}
    for path in full_files:
        if not path.endswith(".py"):
            continue
        try:
            normalized = normalize_path(path)
        except UnsafePathError:
            continue
        content = read_file(normalized)
        if content is None:
            continue
        try:
            trees[normalized] = ast.parse(content)
        except (SyntaxError, ValueError):
            continue
        contents[normalized] = content

    # path -> list of (start, end, new lines); appended definitions use start=0.
    replacements: Dict[str, List[Tuple[int, int, List[str]]]] = {}
    imports: Dict[str, List[str]] = {}
    for language, body in _code_blocks(reply):
        if language not in _PYTHON_FENCES:
            continue
        try:
            block = ast.parse(body)
        except (SyntaxError, ValueError):
            return []
        if not block.body:
            continue
        if any(
            not isinstance(n, _DEFINITIONS + (ast.Import, ast.ImportFrom))
            for n in block.body
        ):
            return []
        body_lines = body.split("\n")
        target: Optional[str] = None
        planned: List[Tuple[Optional[ast.stmt], ast.stmt]] = []
        for node in block.body:
            if not isinstance(node, _DEFINITIONS):
                continue
            owners = [
                (path, existing)
                for path, tree in trees.items()
                for existing in tree.body
                if isinstance(existing, _DEFINITIONS) and existing.name == node.name
            ]
            if len(owners) > 1:
                return []
            if owners:
                path, existing = owners[0]
                if target is not None and target != path:
                    return []
                target = path
                if isinstance(existing, ast.ClassDef):
                    if not isinstance(node, ast.ClassDef) or not set(
                        _method_names(existing)
                    ) <= set(_method_names(node)):
                        return []
                planned.append((existing, node))
            else:
                planned.append((None, node))
        if target is None:
            continue
        for previous, definition in planned:
            start, end = _span(definition)
            new_lines = body_lines[start - 1 : end]
            if previous is None:
                replacements.setdefault(target, []).append((0, 0, new_lines))
            else:
                old_start, old_end = _span(previous)
                replacements.setdefault(target, []).append(
                    (old_start, old_end, new_lines)
                )
        for node in block.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                line = ast.get_source_segment(body, node) or ""
                imports.setdefault(target, []).append(line.strip())

    changes = []
    for path, edits in replacements.items():
        original = contents[path]
        lines = original.split("\n")
        appended = [e[2] for e in edits if e[0] == 0]
        in_place = sorted((e for e in edits if e[0] != 0), key=lambda e: -e[0])
        for start, end, new_lines in in_place:
            lines[start - 1 : end] = new_lines
        for new_lines in appended:
            while lines and not lines[-1].strip():
                lines.pop()
            lines.extend(["", ""] + new_lines)
        updated = "\n".join(lines).rstrip("\n") + "\n"
        updated = _add_imports(updated, imports.get(path, []))
        if updated != original:
            changes.append(FileChange(path, original, updated))
    return changes


def _add_imports(content: str, import_lines: Sequence[str]) -> str:
    """Adds import statements the file does not already have after its imports."""
    existing = {line.strip() for line in content.split("\n")}
    missing = [
        line for line in dict.fromkeys(import_lines) if line and line not in existing
    ]
    if not missing:
        return content
    tree = ast.parse(content)
    last_import = 0
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            last_import = node.end_lineno or node.lineno
    if last_import == 0 and tree.body and isinstance(tree.body[0], ast.Expr):
        last_import = tree.body[0].end_lineno or 0
    lines = content.split("\n")
    lines[last_import:last_import] = missing
    return "\n".join(lines)
