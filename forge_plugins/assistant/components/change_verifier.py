"""
Static checks of a proposed change, run before anything is written to disk.

Reuses the Developer plugin's GeneratedCodeValidator (syntax, JSON/TOML,
import resolution, names imported from local modules, undefined names,
leftover stubs) on the whole project twice - as it is now and as it would
be after the change - and reports only the problems the change introduces.
That catches breakage the change causes in *other* files too (for example
renaming a function that another module imports), without blaming the
change for problems the project already had. Nothing is executed.
"""

import ast
import logging
from collections import Counter
from pathlib import PurePosixPath
from typing import Dict, Iterator, List, Optional, Sequence, Set, Tuple

from forge_plugins.developer.models import GeneratedFile, ValidationIssue
from forge_plugins.developer.validators.code_validator import GeneratedCodeValidator

from ..models import FileChange, VerificationIssue, VerificationResult
from .code_index import CodeIndex

logger = logging.getLogger("ForgeAI.Plugins.Assistant.ChangeVerifier")

_CHECKED_SUFFIXES = frozenset({".py", ".json", ".toml"})
# Project-wide checks; anything else (leftover stubs, placeholder comments)
# only matters inside the files the change touched.
_PROJECT_WIDE_CHECKS = frozenset({"syntax", "json", "toml", "import", "undefined-name"})
# Dependency warnings are about the project's manifest, not the change, and
# duplicates are expected in real projects (e.g. empty __init__.py files).
_IGNORED_CHECKS = frozenset({"dependency", "duplicate"})

_IssueKey = Tuple[str, str, str, str]


def _key(issue: ValidationIssue) -> _IssueKey:
    return (issue.severity.value, issue.check, issue.path, issue.message)


class ChangeVerifier:
    """Finds the problems a change set would introduce into a project."""

    def __init__(
        self,
        validator: Optional[GeneratedCodeValidator] = None,
        max_files: int = 1500,
        max_bytes: int = 12_000_000,
    ) -> None:
        """
        Args:
            validator (Optional[GeneratedCodeValidator]): Static validator to use.
            max_files (int): Above this many checkable files, only the changed
                files' folders are checked, to stay fast on large projects.
            max_bytes (int): The same bound, in total bytes.
        """
        self._validator = validator or GeneratedCodeValidator()
        self._max_files = max_files
        self._max_bytes = max_bytes

    def verify(
        self, index: CodeIndex, changes: Sequence[FileChange]
    ) -> VerificationResult:
        """
        Checks a change set against the project.

        Args:
            index (CodeIndex): The refreshed index of the project.
            changes (Sequence[FileChange]): The proposed file changes.

        Returns:
            VerificationResult: Problems the change introduces, errors first.
        """
        changed = {c.path: c for c in changes}
        if not any(
            PurePosixPath(p).suffix.lower() in _CHECKED_SUFFIXES for p in changed
        ):
            return VerificationResult(
                checked_files=0,
                skipped_reason=(
                    "No Python, JSON or TOML files changed, so there was nothing "
                    "to check statically."
                ),
            )
        checkable = [
            p
            for p in index.paths()
            if PurePosixPath(p).suffix.lower() in _CHECKED_SUFFIXES
        ]
        skipped_reason = ""
        before: Dict[str, str] = {}
        total = 0
        for path in checkable:
            content = index.content(path)
            if content is None:
                continue
            before[path] = content
            total += len(content)

        if len(before) > self._max_files or total > self._max_bytes:
            folders = {str(PurePosixPath(p).parent) for p in changed}
            before = {
                p: c
                for p, c in before.items()
                if str(PurePosixPath(p).parent) in folders
            }
            skipped_reason = (
                "Large project: only the folders of the changed files were checked."
            )

        after = dict(before)
        for path, change in changed.items():
            if PurePosixPath(path).suffix.lower() in _CHECKED_SUFFIXES:
                after[path] = change.updated
        before_result = self._validator.validate(self._as_files(before))
        after_result = self._validator.validate(self._as_files(after))

        existing = Counter(_key(i) for i in before_result.issues)
        new_issues: List[VerificationIssue] = []
        for issue in after_result.issues:
            if issue.check in _IGNORED_CHECKS:
                continue
            key = _key(issue)
            if existing[key] > 0:
                existing[key] -= 1
                continue
            if issue.check not in _PROJECT_WIDE_CHECKS and issue.path not in changed:
                continue
            new_issues.append(
                VerificationIssue(
                    severity=issue.severity.value,
                    check=issue.check,
                    path=issue.path,
                    message=issue.message,
                    line=issue.line,
                )
            )
        new_issues.extend(self._new_attribute_issues(changed))
        new_issues.sort(
            key=lambda i: (0 if i.severity == "error" else 1, i.path, i.line or 0)
        )
        logger.info(
            f"Verified change to {len(changed)} file(s): "
            f"{sum(1 for i in new_issues if i.severity == 'error')} new error(s), "
            f"{sum(1 for i in new_issues if i.severity != 'error')} new warning(s)."
        )
        return VerificationResult(
            checked_files=after_result.checked_files,
            issues=new_issues,
            skipped_reason=skipped_reason,
        )

    @staticmethod
    def _new_attribute_issues(
        changed: Dict[str, FileChange],
    ) -> List[VerificationIssue]:
        """Missing-`self`-attribute errors a change introduces in the files it touches."""
        issues: List[VerificationIssue] = []
        for path, change in changed.items():
            if PurePosixPath(path).suffix.lower() != ".py":
                continue
            before = Counter(
                message for message, _ in missing_self_attributes(change.original or "")
            )
            for message, line in missing_self_attributes(change.updated):
                if before[message] > 0:
                    before[message] -= 1
                    continue
                issues.append(
                    VerificationIssue("error", "attribute", path, message, line)
                )
        return issues

    @staticmethod
    def _as_files(contents: Dict[str, str]) -> List[GeneratedFile]:
        return [
            GeneratedFile(path=path, content=content, file_type="source")
            for path, content in sorted(contents.items())
        ]


# -- Missing self attributes --------------------------------------------------
#
# Small models often call helpers that don't exist (`self._find_task(...)`).
# The project-wide validator can't see that, because attribute access is
# dynamic in general - so this check only judges classes whose every
# attribute is visible: no base classes from elsewhere, no __getattr__, no
# setattr(), no class decorators other than dataclass.

_SAFE_DECORATORS = frozenset({"dataclass", "dataclasses.dataclass"})


def _decorator_name(node: ast.expr) -> str:
    target = node.func if isinstance(node, ast.Call) else node
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
        return f"{target.value.id}.{target.attr}"
    return ""


def _class_attributes(node: ast.ClassDef) -> Optional[Set[str]]:
    """Every attribute a class visibly defines, or None if it can't be known."""
    names: Set[str] = set()
    for statement in node.body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(statement.name)
        elif isinstance(statement, ast.Assign):
            for target in statement.targets:
                for leaf in ast.walk(target):
                    if isinstance(leaf, ast.Name):
                        names.add(leaf.id)
        elif isinstance(statement, (ast.AnnAssign, ast.AugAssign)) and isinstance(
            statement.target, ast.Name
        ):
            names.add(statement.target.id)
    if names & {"__getattr__", "__getattribute__"}:
        return None
    for sub in ast.walk(node):
        if (
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Name)
            and sub.func.id in {"setattr", "vars"}
        ):
            return None
        if isinstance(sub, ast.Attribute) and sub.attr == "__dict__":
            return None
        if (
            isinstance(sub, ast.Attribute)
            and isinstance(sub.value, ast.Name)
            and sub.value.id in {"self", "cls"}
            and isinstance(sub.ctx, (ast.Store, ast.Del))
        ):
            names.add(sub.attr)
    return names


def _self_loads(node: ast.ClassDef) -> Iterator[Tuple[str, int]]:
    """`self.<name>` reads inside a class's own methods (not nested classes)."""
    for method in node.body:
        if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        args = method.args.posonlyargs + method.args.args
        if not args or args[0].arg != "self":
            continue
        stack: List[ast.AST] = list(method.body)
        while stack:
            current = stack.pop()
            if isinstance(current, ast.ClassDef):
                continue
            if (
                isinstance(current, ast.Attribute)
                and isinstance(current.value, ast.Name)
                and current.value.id == "self"
                and isinstance(current.ctx, ast.Load)
            ):
                yield current.attr, current.lineno
            stack.extend(ast.iter_child_nodes(current))


def missing_self_attributes(source: str) -> List[Tuple[str, int]]:
    """
    Finds `self.x` reads of attributes a class never defines.

    Args:
        source (str): Python source.

    Returns:
        List[Tuple[str, int]]: (message, line) per missing attribute; empty
        if the source does not parse.
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}
    attributes: Dict[str, Optional[Set[str]]] = {}

    def resolve(name: str, seen: Set[str]) -> Optional[Set[str]]:
        if name in attributes:
            return attributes[name]
        node = classes[name]
        if name in seen or node.keywords:
            return None
        if any(_decorator_name(d) not in _SAFE_DECORATORS for d in node.decorator_list):
            attributes[name] = None
            return None
        own = _class_attributes(node)
        if own is None:
            attributes[name] = None
            return None
        for base in node.bases:
            if isinstance(base, ast.Name) and base.id == "object":
                continue
            if isinstance(base, ast.Name) and base.id in classes:
                inherited = resolve(base.id, seen | {name})
                if inherited is None:
                    attributes[name] = None
                    return None
                own = own | inherited
                continue
            attributes[name] = None
            return None
        attributes[name] = own
        return own

    found: List[Tuple[str, int]] = []
    for name, node in classes.items():
        known = resolve(name, set())
        if known is None:
            continue
        reported: Set[str] = set()
        for attr, line in sorted(_self_loads(node), key=lambda item: item[1]):
            if (
                attr in known
                or attr in reported
                or (attr.startswith("__") and attr.endswith("__"))
            ):
                continue
            reported.add(attr)
            found.append(
                (
                    f"`self.{attr}` is used, but class {name} never defines {attr}.",
                    line,
                )
            )
    return found
