"""
Static validation of the source files the Developer Plugin generates.

Nothing generated is ever executed: every check works on file text (the Python
AST, the JSON and TOML parsers), so validating untrusted model output is safe.
The checks target the failures local models actually produce - syntax errors,
relative imports from top-level scripts, imports of modules or names that were
never generated, names used without being defined or imported, undeclared
third-party dependencies, and leftover stubs.
"""

import ast
import builtins
import io
import json
import logging
import re
import sys
import tokenize
import tomllib
from pathlib import PurePosixPath
from typing import Dict, Iterator, List, Optional, Sequence, Set, Tuple

from forge_plugins.developer.models import (
    CodeValidationResult,
    GeneratedFile,
    IssueSeverity,
    ValidationIssue,
)

logger = logging.getLogger("ForgeAI.Plugins.Developer.CodeValidator")

# Import names whose PyPI distribution is published under a different name.
_IMPORT_TO_DISTRIBUTIONS: Dict[str, Tuple[str, ...]] = {
    "attr": ("attrs",),
    "bs4": ("beautifulsoup4",),
    "Crypto": ("pycryptodome", "pycryptodomex"),
    "cv2": ("opencv-python", "opencv-python-headless", "opencv-contrib-python"),
    "dateutil": ("python-dateutil",),
    "dotenv": ("python-dotenv",),
    "jose": ("python-jose",),
    "jwt": ("pyjwt",),
    "multipart": ("python-multipart",),
    "MySQLdb": ("mysqlclient",),
    "OpenSSL": ("pyopenssl",),
    "PIL": ("pillow",),
    "pkg_resources": ("setuptools",),
    "psycopg2": ("psycopg2", "psycopg2-binary"),
    "serial": ("pyserial",),
    "sklearn": ("scikit-learn",),
    "usb": ("pyusb",),
    "win32api": ("pywin32",),
    "yaml": ("pyyaml",),
}

_MODULE_DUNDERS = {
    "__file__",
    "__name__",
    "__doc__",
    "__path__",
    "__builtins__",
    "__spec__",
    "__loader__",
    "__package__",
    "__annotations__",
    "__dict__",
    "__module__",
    "__qualname__",
    "__class__",
}
_KNOWN_GLOBALS = frozenset(dir(builtins)) | _MODULE_DUNDERS

_PLACEHOLDER_COMMENT = re.compile(
    r"\b(TODO|FIXME)\b|\b(dummy|placeholder|stub)\b", re.I
)
_REQUIREMENT_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
_STUB_DECORATORS = {"abstractmethod", "abstractproperty", "overload"}
_IMPORT_ERRORS = {"ImportError", "ModuleNotFoundError"}
_NESTED_SCOPES = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.Lambda,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
)


def _normalize_path(path: str) -> str:
    cleaned = path.replace("\\", "/").strip()
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return PurePosixPath(cleaned.lstrip("/")).as_posix()


def _normalize_distribution(name: str) -> str:
    """PEP 503 normalization, so 'Pydantic_Settings' matches 'pydantic-settings'."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _issue(
    severity: IssueSeverity, check: str, path: str, message: str, line: Optional[int]
) -> ValidationIssue:
    return ValidationIssue(
        severity=severity, check=check, path=path, message=message, line=line
    )


class _ProjectIndex:
    """Answers "does this module exist among the generated files?"."""

    def __init__(self, paths: Sequence[str]) -> None:
        self.py_files: Set[str] = {p for p in paths if p.endswith(".py")}
        self.py_dirs: Set[str] = set()
        for p in self.py_files:
            parent = PurePosixPath(p).parent
            while parent.as_posix() not in ("", "."):
                self.py_dirs.add(parent.as_posix())
                parent = parent.parent

    @staticmethod
    def _roots_for(file_path: str) -> List[str]:
        # Where an absolute import can resolve from, depending on how the project
        # is launched: the importing script's own directory (python dir/script.py),
        # the project root (python -m), and a src/ layout.
        parent = PurePosixPath(file_path).parent.as_posix()
        roots = ["" if parent == "." else parent, "", "src"]
        return list(dict.fromkeys(roots))

    def resolve_path(self, rel: str) -> Optional[Tuple[str, str]]:
        """
        Resolves a slash-separated module path to ("module" | "package" |
        "namespace", path), or None if nothing was generated there.
        """
        rel = rel.strip("/")
        if not rel:
            return None
        if f"{rel}.py" in self.py_files:
            return "module", f"{rel}.py"
        if f"{rel}/__init__.py" in self.py_files:
            return "package", f"{rel}/__init__.py"
        if rel in self.py_dirs:
            return "namespace", rel
        return None

    def resolve_all(self, dotted: str, file_path: str) -> List[Tuple[str, str]]:
        """
        Every generated module an absolute dotted import could resolve to from
        `file_path`. Which one Python picks depends on how the project is
        launched, so callers treat an import as broken only if all fail.
        """
        tail = dotted.replace(".", "/")
        found: List[Tuple[str, str]] = []
        for root in self._roots_for(file_path):
            target = self.resolve_path(f"{root}/{tail}" if root else tail)
            if target is not None and target not in found:
                found.append(target)
        return found


def _scope_store_names(node: ast.AST) -> Set[str]:
    """Names bound by `node` without descending into nested scopes."""
    names: Set[str] = set()
    stack: List[ast.AST] = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, ast.Name) and isinstance(current.ctx, ast.Store):
            names.add(current.id)
        for child in ast.iter_child_nodes(current):
            if not isinstance(child, _NESTED_SCOPES):
                stack.append(child)
    return names


def _module_scope_statements(body: Sequence[ast.stmt]) -> Iterator[ast.stmt]:
    """Statements that execute at module scope, including inside if/try/with blocks."""
    for stmt in body:
        yield stmt
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for attr in ("body", "orelse", "finalbody"):
            inner = getattr(stmt, attr, None)
            if isinstance(inner, list):
                yield from _module_scope_statements(inner)
        for handler in getattr(stmt, "handlers", []) or []:
            yield from _module_scope_statements(handler.body)
        if isinstance(stmt, ast.Match):
            for case in stmt.cases:
                yield from _module_scope_statements(case.body)


def _module_bindings(tree: ast.Module) -> Optional[Set[str]]:
    """
    Names importable from a module. None when that cannot be known statically
    (a star import, or a module-level __getattr__).
    """
    names: Set[str] = set()
    for stmt in _module_scope_statements(tree.body):
        if isinstance(stmt, ast.ImportFrom) and any(a.name == "*" for a in stmt.names):
            return None
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if stmt.name == "__getattr__":
                return None
            names.add(stmt.name)
        elif isinstance(stmt, ast.Import):
            names.update(a.asname or a.name.split(".")[0] for a in stmt.names)
        elif isinstance(stmt, ast.ImportFrom):
            names.update(a.asname or a.name for a in stmt.names)
        else:
            names.update(_scope_store_names(stmt))
    return names


def _guarded_import_lines(tree: ast.Module) -> Set[int]:
    """Line numbers of imports wrapped in `try: ... except ImportError:` (optional imports)."""
    lines: Set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        catches_import_error = False
        for handler in node.handlers:
            caught = handler.type
            types = caught.elts if isinstance(caught, ast.Tuple) else [caught]
            if caught is None or any(
                isinstance(t, ast.Name) and t.id in _IMPORT_ERRORS for t in types
            ):
                catches_import_error = True
        if catches_import_error:
            for stmt in node.body:
                for inner in ast.walk(stmt):
                    if isinstance(inner, (ast.Import, ast.ImportFrom)):
                        lines.add(inner.lineno)
    return lines


def _expr_name(node: ast.expr) -> str:
    """The trailing identifier of a decorator or base-class expression."""
    target = node.func if isinstance(node, ast.Call) else node
    if isinstance(target, ast.Subscript):
        target = target.value
    if isinstance(target, ast.Attribute):
        return target.attr
    if isinstance(target, ast.Name):
        return target.id
    return ""


def _is_stub_body(body: Sequence[ast.stmt]) -> bool:
    statements = list(body)
    if (
        statements
        and isinstance(statements[0], ast.Expr)
        and isinstance(statements[0].value, ast.Constant)
        and isinstance(statements[0].value.value, str)
    ):
        statements = statements[1:]
    if not statements:
        return True
    for stmt in statements:
        if isinstance(stmt, ast.Pass):
            continue
        if (
            isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Constant)
            and stmt.value.value is Ellipsis
        ):
            continue
        if isinstance(stmt, ast.Raise) and stmt.exc is not None:
            exc = stmt.exc.func if isinstance(stmt.exc, ast.Call) else stmt.exc
            if isinstance(exc, ast.Name) and exc.id == "NotImplementedError":
                continue
        return False
    return True


class GeneratedCodeValidator:
    """Statically validates a set of generated files and reports every problem found."""

    def validate(self, files: Sequence[GeneratedFile]) -> CodeValidationResult:
        """
        Validates generated files. Never executes any of them.

        Args:
            files (Sequence[GeneratedFile]): Files in generation order. When a
                path appears more than once, the last version is the one that
                gets written, so it is the one validated.

        Returns:
            CodeValidationResult: Findings, errors first.
        """
        issues: List[ValidationIssue] = []
        latest: Dict[str, GeneratedFile] = {}
        for gen_file in files:
            path = _normalize_path(gen_file.path)
            if path in latest:
                issues.append(
                    _issue(
                        IssueSeverity.WARNING,
                        "duplicate",
                        path,
                        "This file was generated more than once; only the last version is kept.",
                        None,
                    )
                )
            latest[path] = gen_file

        checked = 0
        modules: Dict[str, ast.Module] = {}
        for path, gen_file in latest.items():
            suffix = PurePosixPath(path).suffix.lower()
            if suffix == ".py":
                checked += 1
                tree = self._parse_python(path, gen_file.content, issues)
                if tree is not None:
                    modules[path] = tree
            elif suffix == ".json":
                checked += 1
                self._check_json(path, gen_file.content, issues)
            elif suffix == ".toml":
                checked += 1
                self._check_toml(path, gen_file.content, issues)

        index = _ProjectIndex(list(latest))
        declared = self._declared_dependencies(latest)
        third_party: Dict[str, Tuple[str, int]] = {}
        for path, tree in modules.items():
            self._check_imports(path, tree, index, modules, issues, third_party)
            self._check_undefined_names(path, tree, issues)
            self._check_placeholders(path, latest[path].content, tree, issues)
        self._check_dependencies(third_party, declared, issues)
        self._check_duplicate_content(latest, issues)

        issues.sort(
            key=lambda i: (
                0 if i.severity is IssueSeverity.ERROR else 1,
                i.path,
                i.line or 0,
            )
        )
        return CodeValidationResult(checked_files=checked, issues=issues)

    # ── Parsing ────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_python(
        path: str, content: str, issues: List[ValidationIssue]
    ) -> Optional[ast.Module]:
        try:
            return ast.parse(content, filename=path)
        except SyntaxError as e:
            issues.append(
                _issue(
                    IssueSeverity.ERROR,
                    "syntax",
                    path,
                    f"Python syntax error: {e.msg}",
                    e.lineno,
                )
            )
        except ValueError as e:
            issues.append(
                _issue(
                    IssueSeverity.ERROR,
                    "syntax",
                    path,
                    f"Unparseable source: {e}",
                    None,
                )
            )
        return None

    @staticmethod
    def _check_json(path: str, content: str, issues: List[ValidationIssue]) -> None:
        try:
            json.loads(content)
        except json.JSONDecodeError as e:
            issues.append(
                _issue(
                    IssueSeverity.ERROR,
                    "json",
                    path,
                    f"Invalid JSON: {e.msg}",
                    e.lineno,
                )
            )

    @staticmethod
    def _check_toml(path: str, content: str, issues: List[ValidationIssue]) -> None:
        try:
            tomllib.loads(content)
        except tomllib.TOMLDecodeError as e:
            issues.append(
                _issue(IssueSeverity.ERROR, "toml", path, f"Invalid TOML: {e}", None)
            )

    # ── Imports ────────────────────────────────────────────────────────────

    def _check_imports(
        self,
        path: str,
        tree: ast.Module,
        index: _ProjectIndex,
        modules: Dict[str, ast.Module],
        issues: List[ValidationIssue],
        third_party: Dict[str, Tuple[str, int]],
    ) -> None:
        guarded = _guarded_import_lines(tree)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            if node.lineno in guarded:
                continue
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self._check_absolute(
                        path,
                        node.lineno,
                        alias.name,
                        [],
                        index,
                        modules,
                        issues,
                        third_party,
                    )
            elif node.level > 0:
                self._check_relative(path, node, index, modules, issues)
            elif node.module:
                names = [a.name for a in node.names if a.name != "*"]
                self._check_absolute(
                    path,
                    node.lineno,
                    node.module,
                    names,
                    index,
                    modules,
                    issues,
                    third_party,
                )

    def _check_absolute(
        self,
        path: str,
        line: int,
        module: str,
        names: List[str],
        index: _ProjectIndex,
        modules: Dict[str, ast.Module],
        issues: List[ValidationIssue],
        third_party: Dict[str, Tuple[str, int]],
    ) -> None:
        top = module.split(".")[0]
        targets = index.resolve_all(module, path)
        if targets:
            self._check_imported_names(
                path, line, module, names, targets, index, modules, issues
            )
            return
        if index.resolve_all(top, path):
            issues.append(
                _issue(
                    IssueSeverity.ERROR,
                    "import",
                    path,
                    f"Module '{module}' does not exist in the generated project.",
                    line,
                )
            )
            return
        if top in sys.stdlib_module_names or top == "__future__":
            return
        third_party.setdefault(top, (path, line))

    def _check_relative(
        self,
        path: str,
        node: ast.ImportFrom,
        index: _ProjectIndex,
        modules: Dict[str, ast.Module],
        issues: List[ValidationIssue],
    ) -> None:
        dots = "." * node.level
        shown = f"from {dots}{node.module or ''} import ..."
        parent = PurePosixPath(path).parent.as_posix()
        package_parts = [] if parent == "." else parent.split("/")
        if not package_parts:
            issues.append(
                _issue(
                    IssueSeverity.ERROR,
                    "import",
                    path,
                    f"'{shown}' is a relative import in a top-level module; it fails at "
                    "runtime with 'attempted relative import with no known parent package'.",
                    node.lineno,
                )
            )
            return
        climb = node.level - 1
        if climb >= len(package_parts):
            issues.append(
                _issue(
                    IssueSeverity.ERROR,
                    "import",
                    path,
                    f"'{shown}' climbs above the top-level package.",
                    node.lineno,
                )
            )
            return
        base = "/".join(package_parts[: len(package_parts) - climb])
        names = [a.name for a in node.names if a.name != "*"]
        if node.module:
            rel = f"{base}/{node.module.replace('.', '/')}"
            target = index.resolve_path(rel)
            if target is None:
                issues.append(
                    _issue(
                        IssueSeverity.ERROR,
                        "import",
                        path,
                        f"'{shown}' refers to a module that does not exist in the generated project.",
                        node.lineno,
                    )
                )
                return
            self._check_imported_names(
                path,
                node.lineno,
                f"{dots}{node.module}",
                names,
                [target],
                index,
                modules,
                issues,
            )
            return
        package = index.resolve_path(base)
        if package is not None:
            self._check_imported_names(
                path, node.lineno, dots, names, [package], index, modules, issues
            )

    @staticmethod
    def _check_imported_names(
        path: str,
        line: int,
        module: str,
        names: List[str],
        targets: List[Tuple[str, str]],
        index: _ProjectIndex,
        modules: Dict[str, ast.Module],
        issues: List[ValidationIssue],
    ) -> None:
        """Reports names that no candidate target module provides."""

        def provides(target: Tuple[str, str], name: str) -> bool:
            kind, target_path = target
            if kind in ("module", "package"):
                tree = modules.get(target_path)
                # An unparseable target is already reported as a syntax error,
                # and a dynamic one cannot be checked; neither is flagged here.
                bindings = _module_bindings(tree) if tree is not None else None
                if bindings is None or name in bindings:
                    return True
                if kind == "module":
                    return False
            package_dir = (
                target_path
                if kind == "namespace"
                else PurePosixPath(target_path).parent.as_posix()
            )
            return index.resolve_path(f"{package_dir}/{name}") is not None

        for name in names:
            if any(provides(target, name) for target in targets):
                continue
            where = ", ".join(t[1] for t in targets)
            issues.append(
                _issue(
                    IssueSeverity.ERROR,
                    "import",
                    path,
                    f"Cannot import name '{name}' from '{module}' ({where}); "
                    "it is not defined there.",
                    line,
                )
            )

    # ── Dependencies ───────────────────────────────────────────────────────

    @staticmethod
    def _declared_dependencies(latest: Dict[str, GeneratedFile]) -> Optional[Set[str]]:
        """Normalized distribution names from requirements*.txt / pyproject.toml, or None if neither exists."""
        declared: Set[str] = set()
        found_manifest = False
        for path, gen_file in latest.items():
            name = PurePosixPath(path).name.lower()
            if name.startswith("requirements") and name.endswith(".txt"):
                found_manifest = True
                for raw in gen_file.content.splitlines():
                    entry = raw.split("#", 1)[0].strip()
                    if not entry or entry.startswith("-"):
                        continue
                    match = _REQUIREMENT_NAME.match(entry)
                    if match:
                        declared.add(_normalize_distribution(match.group(1)))
            elif name == "pyproject.toml":
                found_manifest = True
                try:
                    data = tomllib.loads(gen_file.content)
                except tomllib.TOMLDecodeError:
                    continue
                entries: List[str] = list(
                    data.get("project", {}).get("dependencies", [])
                )
                poetry = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
                entries.extend(poetry.keys() if isinstance(poetry, dict) else [])
                for entry in entries:
                    match = _REQUIREMENT_NAME.match(str(entry))
                    if match:
                        declared.add(_normalize_distribution(match.group(1)))
        return declared if found_manifest else None

    @staticmethod
    def _check_dependencies(
        third_party: Dict[str, Tuple[str, int]],
        declared: Optional[Set[str]],
        issues: List[ValidationIssue],
    ) -> None:
        for top, (path, line) in sorted(third_party.items()):
            if top.lower() == "python":
                continue
            candidates = _IMPORT_TO_DISTRIBUTIONS.get(top, ()) + (top,)
            if declared is not None and any(
                _normalize_distribution(c) in declared for c in candidates
            ):
                continue
            where = (
                "no requirements.txt or pyproject.toml was generated"
                if declared is None
                else "it is not declared in requirements.txt / pyproject.toml"
            )
            issues.append(
                _issue(
                    IssueSeverity.WARNING,
                    "dependency",
                    path,
                    f"Third-party package '{top}' is imported but {where}; "
                    "declare every direct dependency.",
                    line,
                )
            )

    # ── Names ──────────────────────────────────────────────────────────────

    @staticmethod
    def _check_undefined_names(
        path: str, tree: ast.Module, issues: List[ValidationIssue]
    ) -> None:
        """
        Flags names that are read but bound nowhere in the module. Deliberately
        scope-insensitive: a name bound anywhere counts as defined, so anything
        reported is undefined everywhere and is a guaranteed NameError if reached.
        """
        bound: Set[str] = set(_KNOWN_GLOBALS)
        used: Dict[str, int] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and any(
                a.name == "*" for a in node.names
            ):
                return
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                bound.add(node.name)
            elif isinstance(node, ast.Import):
                bound.update(a.asname or a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                bound.update(a.asname or a.name for a in node.names)
            elif isinstance(node, ast.arg):
                bound.add(node.arg)
            elif isinstance(node, ast.Name):
                if isinstance(node.ctx, ast.Load):
                    used[node.id] = min(used.get(node.id, node.lineno), node.lineno)
                else:
                    bound.add(node.id)
            elif isinstance(node, ast.ExceptHandler) and node.name:
                bound.add(node.name)
            elif isinstance(node, (ast.Global, ast.Nonlocal)):
                bound.update(node.names)
            elif isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name:
                bound.add(node.name)
            elif isinstance(node, ast.MatchMapping) and node.rest:
                bound.add(node.rest)
            elif isinstance(node, (ast.TypeVar, ast.ParamSpec, ast.TypeVarTuple)):
                bound.add(node.name)

        for name, line in sorted(used.items(), key=lambda item: item[1]):
            if name not in bound:
                issues.append(
                    _issue(
                        IssueSeverity.ERROR,
                        "undefined-name",
                        path,
                        f"Name '{name}' is used but never defined or imported.",
                        line,
                    )
                )

    # ── Leftovers ──────────────────────────────────────────────────────────

    @staticmethod
    def _check_placeholders(
        path: str, content: str, tree: ast.Module, issues: List[ValidationIssue]
    ) -> None:
        try:
            for token in tokenize.generate_tokens(io.StringIO(content).readline):
                if token.type == tokenize.COMMENT and _PLACEHOLDER_COMMENT.search(
                    token.string
                ):
                    issues.append(
                        _issue(
                            IssueSeverity.WARNING,
                            "placeholder",
                            path,
                            f"Placeholder comment left in generated code: {token.string.strip()[:80]}",
                            token.start[0],
                        )
                    )
        except tokenize.TokenError as e:
            # The AST parse already succeeded; a tokenizer edge case only means
            # comments go unscanned, not that the code is invalid.
            logger.debug(f"Skipped comment scan for {path}: {e}")

        protocol_methods: Set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and any(
                _expr_name(base).endswith("Protocol") for base in node.bases
            ):
                protocol_methods.update(id(item) for item in node.body)

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if id(node) in protocol_methods:
                continue
            if any(_expr_name(d) in _STUB_DECORATORS for d in node.decorator_list):
                continue
            if _is_stub_body(node.body):
                issues.append(
                    _issue(
                        IssueSeverity.WARNING,
                        "placeholder",
                        path,
                        f"Function '{node.name}' has no implementation "
                        "(only pass, ..., or NotImplementedError).",
                        node.lineno,
                    )
                )

    @staticmethod
    def _check_duplicate_content(
        latest: Dict[str, GeneratedFile], issues: List[ValidationIssue]
    ) -> None:
        first_seen: Dict[str, str] = {}
        for path, gen_file in latest.items():
            if not path.endswith(".py") or PurePosixPath(path).name == "__init__.py":
                continue
            normalized = "\n".join(
                line.rstrip() for line in gen_file.content.strip().splitlines()
            )
            if not normalized:
                continue
            if normalized in first_seen:
                issues.append(
                    _issue(
                        IssueSeverity.WARNING,
                        "duplicate",
                        path,
                        f"Identical to {first_seen[normalized]}.",
                        None,
                    )
                )
            else:
                first_seen[normalized] = path
