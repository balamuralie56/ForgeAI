"""
Safe access to the user's project folder: listing source files (honouring
.gitignore), reading text, and writing changes atomically - never outside
the project root and never inside version-control or dependency folders.
"""

import fnmatch
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import List, Optional, Tuple

from ..exceptions import InvalidProjectError, UnsafePathError

logger = logging.getLogger("ForgeAI.Plugins.Assistant.Workspace")

# Folders that never hold the user's own source code. They are skipped when
# listing and can never be written to.
IGNORED_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".nox",
        ".eggs",
        ".idea",
        ".next",
        ".nuxt",
        ".gradle",
        ".terraform",
        "dist",
        "build",
        "htmlcov",
        "coverage",
        "target",
    }
)

# Binary or generated files that are pointless to read as source.
_SKIPPED_SUFFIXES = frozenset(
    {
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".svgz",
        ".pdf", ".zip", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar", ".tar",
        ".exe", ".dll", ".so", ".dylib", ".bin", ".o", ".a", ".lib", ".class",
        ".jar", ".pyc", ".pyo", ".pyd", ".whl", ".db", ".sqlite", ".sqlite3",
        ".woff", ".woff2", ".ttf", ".otf", ".eot", ".mp3", ".mp4", ".wav",
        ".avi", ".mov", ".mkv", ".psd", ".parquet", ".pkl", ".pt", ".onnx",
        ".gguf", ".safetensors", ".npy", ".npz", ".map", ".log",
    }
)  # fmt: skip
_SKIPPED_NAMES = frozenset(
    {
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "poetry.lock",
        "Pipfile.lock",
        "Cargo.lock",
        "composer.lock",
        "uv.lock",
    }
)


@dataclass(frozen=True)
class FileInfo:
    """
    A source file in the project.

    Attributes:
        path (str): Project-relative POSIX path.
        size (int): Size in bytes.
        mtime (float): Last modification time.
    """

    path: str
    size: int
    mtime: float


@dataclass(frozen=True)
class _IgnoreRule:
    pattern: str
    negated: bool
    dir_only: bool
    anchored: bool


class _GitIgnore:
    """
    The root .gitignore of a project. Supports comments, negation (`!`),
    directory-only (`dir/`) and anchored (`/x`, `a/b`) patterns; nested
    .gitignore files are not read.
    """

    def __init__(self, text: str) -> None:
        self._rules: List[_IgnoreRule] = []
        for raw in text.splitlines():
            line = raw.rstrip()
            if not line or line.startswith("#"):
                continue
            negated = line.startswith("!")
            if negated:
                line = line[1:]
            dir_only = line.endswith("/")
            line = line.rstrip("/")
            anchored = line.startswith("/") or "/" in line
            line = line.lstrip("/")
            if line.startswith("**/"):
                line = line[3:]
                anchored = "/" in line
            if line:
                self._rules.append(_IgnoreRule(line, negated, dir_only, anchored))

    def ignores(self, rel_path: str, is_dir: bool) -> bool:
        """Returns whether a project-relative path is ignored."""
        name = rel_path.rsplit("/", 1)[-1]
        ignored = False
        for rule in self._rules:
            if rule.dir_only and not is_dir:
                continue
            target = rel_path if rule.anchored else name
            if fnmatch.fnmatchcase(target, rule.pattern) or (
                rule.anchored and fnmatch.fnmatchcase(target, rule.pattern + "/*")
            ):
                ignored = not rule.negated
        return ignored


class ProjectWorkspace:
    """
    A validated project folder the assistant may read from and write to.
    """

    def __init__(self, root: str, max_files: int, max_file_bytes: int) -> None:
        """
        Args:
            root (str): Path of the project folder.
            max_files (int): Upper bound on files listed.
            max_file_bytes (int): Files larger than this are not read or edited.

        Raises:
            InvalidProjectError: If the folder is missing, not a folder, or too
                broad to be a project (a drive root or the home folder).
        """
        self.root = validate_project_root(root)
        self.max_files = max_files
        self.max_file_bytes = max_file_bytes
        self._gitignore = self._load_gitignore()

    def _load_gitignore(self) -> _GitIgnore:
        path = self.root / ".gitignore"
        try:
            return _GitIgnore(path.read_text(encoding="utf-8", errors="replace"))
        except FileNotFoundError:
            return _GitIgnore("")
        except OSError as e:
            logger.warning(f"Could not read {path}: {e}")
            return _GitIgnore("")

    # ── Paths ──────────────────────────────────────────────────────────────

    def normalize(self, rel_path: str) -> str:
        """
        Normalizes a project-relative path and checks that it is safe.

        Args:
            rel_path (str): A path relative to the project root.

        Returns:
            str: The normalized POSIX path.

        Raises:
            UnsafePathError: If the path is absolute, escapes the project, or
                points into a protected folder.
        """
        cleaned = rel_path.strip().strip("`'\"").replace("\\", "/")
        while cleaned.startswith("./"):
            cleaned = cleaned[2:]
        if not cleaned:
            raise UnsafePathError("Empty file path.")
        pure = PurePosixPath(cleaned)
        if pure.is_absolute() or (len(cleaned) > 1 and cleaned[1] == ":"):
            raise UnsafePathError(f"'{rel_path}' is an absolute path.")
        if any(part == ".." for part in pure.parts):
            raise UnsafePathError(f"'{rel_path}' points outside the project.")
        if any(part in IGNORED_DIRS for part in pure.parts[:-1]):
            raise UnsafePathError(f"'{rel_path}' is inside a protected folder.")
        normalized = str(pure)
        resolved = (self.root / normalized).resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise UnsafePathError(f"'{rel_path}' points outside the project.")
        return normalized

    def absolute(self, rel_path: str) -> Path:
        """Returns the absolute path of a safe project-relative path."""
        return self.root / self.normalize(rel_path)

    # ── Listing ────────────────────────────────────────────────────────────

    def list_files(self) -> List[FileInfo]:
        """
        Lists the project's source files, skipping ignored folders, binary
        types, lock files and files over the size limit.

        Returns:
            List[FileInfo]: Files sorted by path, at most `max_files`.
        """
        found: List[FileInfo] = []
        stack: List[Tuple[Path, str]] = [(self.root, "")]
        while stack and len(found) < self.max_files:
            directory, prefix = stack.pop()
            try:
                entries = sorted(os.scandir(directory), key=lambda e: e.name)
            except OSError as e:
                logger.warning(f"Cannot list {directory}: {e}")
                continue
            subdirs: List[Tuple[Path, str]] = []
            for entry in entries:
                rel = f"{prefix}{entry.name}"
                try:
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name in IGNORED_DIRS or entry.name.endswith(
                            ".egg-info"
                        ):
                            continue
                        if self._gitignore.ignores(rel, is_dir=True):
                            continue
                        subdirs.append((Path(entry.path), rel + "/"))
                    elif entry.is_file(follow_symlinks=False):
                        if not self._is_candidate(entry.name, rel):
                            continue
                        stat = entry.stat()
                        if stat.st_size > self.max_file_bytes:
                            continue
                        found.append(FileInfo(rel, stat.st_size, stat.st_mtime))
                        if len(found) >= self.max_files:
                            logger.warning(
                                f"Stopped listing {self.root} at {self.max_files} files."
                            )
                            break
                except OSError as e:
                    logger.warning(f"Cannot inspect {entry.path}: {e}")
            stack.extend(reversed(subdirs))
        return sorted(found, key=lambda f: f.path)

    def _is_candidate(self, name: str, rel: str) -> bool:
        if name in _SKIPPED_NAMES:
            return False
        suffix = PurePosixPath(name).suffix.lower()
        if suffix in _SKIPPED_SUFFIXES or name.endswith(".min.js"):
            return False
        return not self._gitignore.ignores(rel, is_dir=False)

    # ── Reading and writing ────────────────────────────────────────────────

    def read_text(self, rel_path: str) -> Optional[str]:
        """
        Reads a project file as text.

        Args:
            rel_path (str): Project-relative path.

        Returns:
            Optional[str]: The content, or None if the file does not exist,
            is binary, or is over the size limit.

        Raises:
            UnsafePathError: If the path is not safe.
        """
        path = self.absolute(rel_path)
        try:
            if not path.is_file() or path.stat().st_size > self.max_file_bytes:
                return None
            data = path.read_bytes()
        except OSError as e:
            logger.warning(f"Cannot read {path}: {e}")
            return None
        if b"\x00" in data[:8192]:
            return None
        return data.decode("utf-8", errors="replace").replace("\r\n", "\n")

    def exists(self, rel_path: str) -> bool:
        """Returns whether a project file exists."""
        return self.absolute(rel_path).is_file()

    def write_text(self, rel_path: str, content: str) -> None:
        """
        Writes a project file atomically (temp file + replace), creating
        parent folders as needed. Keeps the file's existing line endings.

        Args:
            rel_path (str): Project-relative path.
            content (str): Text with `\\n` line endings.

        Raises:
            UnsafePathError: If the path is not safe.
            OSError: If the write fails.
        """
        path = self.absolute(rel_path)
        newline = "\n"
        if path.is_file():
            try:
                with path.open("rb") as handle:
                    if b"\r\n" in handle.read(65536):
                        newline = "\r\n"
            except OSError as e:
                logger.warning(f"Cannot inspect line endings of {path}: {e}")
        path.parent.mkdir(parents=True, exist_ok=True)
        data = content.replace("\r\n", "\n")
        if newline != "\n":
            data = data.replace("\n", newline)
        fd, tmp_name = tempfile.mkstemp(prefix=".forge-", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data.encode("utf-8"))
            os.replace(tmp_name, path)
        except OSError:
            try:
                os.unlink(tmp_name)
            except OSError as cleanup_error:
                logger.warning(
                    f"Could not remove temp file {tmp_name}: {cleanup_error}"
                )
            raise

    def delete(self, rel_path: str) -> None:
        """
        Deletes a project file (used to undo a file the assistant created).

        Raises:
            UnsafePathError: If the path is not safe.
            OSError: If the delete fails.
        """
        path = self.absolute(rel_path)
        if path.is_file():
            path.unlink()


def validate_project_root(root: str) -> Path:
    """
    Resolves and validates a project folder.

    Args:
        root (str): Path of the project folder.

    Returns:
        Path: The resolved absolute path.

    Raises:
        InvalidProjectError: If the folder is missing, not a folder, or too
            broad to be a project.
    """
    if not root or not root.strip():
        raise InvalidProjectError("Choose a project folder.")
    try:
        path = Path(root.strip()).expanduser().resolve()
    except (OSError, RuntimeError) as e:
        raise InvalidProjectError(f"Invalid project folder '{root}': {e}") from e
    if not path.exists():
        raise InvalidProjectError(f"Folder '{path}' does not exist.")
    if not path.is_dir():
        raise InvalidProjectError(f"'{path}' is not a folder.")
    if path.parent == path:
        raise InvalidProjectError(
            f"'{path}' is a whole drive; choose a project folder inside it."
        )
    if path == Path.home().resolve():
        raise InvalidProjectError(
            "That is your home folder; choose a project folder inside it."
        )
    return path
