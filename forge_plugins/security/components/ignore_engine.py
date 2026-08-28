"""
Ignore utility filtering paths according to .forgeignore or default exclusion rules.
"""

import fnmatch
from pathlib import Path
from typing import List, Set


class SecurityIgnoreEngine:
    """
    Parses and matches file exclusions to skip scanning of dependencies, caches, and binary files.
    """

    DEFAULT_EXCLUSIONS = {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".coverage",
        "dist",
        "build",
        "forge_data",
        "*.png",
        "*.jpg",
        "*.jpeg",
        "*.gif",
        "*.pdf",
        "*.exe",
        "*.dll",
        "*.so",
        "*.pyc",
        "*.pyo",
        "*.db",
        "*.sqlite",
    }

    def __init__(self, workspace_path: str) -> None:
        """
        Initializes the ignore engine loading workspace ignore files.
        """
        self.workspace = Path(workspace_path)
        self.ignore_patterns: Set[str] = set(self.DEFAULT_EXCLUSIONS)
        self._load_forgeignore()

    def _load_forgeignore(self) -> None:
        """Loads .forgeignore file if present in workspace root."""
        ignore_file = self.workspace / ".forgeignore"
        if not ignore_file.exists():
            ignore_file = self.workspace / ".gitignore"

        if ignore_file.exists():
            try:
                for line in ignore_file.read_text(encoding="utf-8").splitlines():
                    cleaned = line.strip()
                    if cleaned and not cleaned.startswith("#"):
                        self.ignore_patterns.add(cleaned)
            except Exception:
                pass

    def is_ignored(self, file_path: str) -> bool:
        """
        Checks whether a file path matches ignore patterns.

        Args:
            file_path (str): Relative path within workspace.

        Returns:
            bool: True if file is ignored.
        """
        path = Path(file_path)
        parts = path.parts

        for part in parts:
            if part in self.ignore_patterns:
                return True

        # Check glob matches
        path_str = str(path).replace("\\", "/")
        for pattern in self.ignore_patterns:
            clean_pattern = pattern.rstrip("/")
            if clean_pattern in parts:
                return True
            if fnmatch.fnmatch(path_str, clean_pattern) or fnmatch.fnmatch(
                path.name, clean_pattern
            ):
                return True

        return False

    def filter_paths(self, file_paths: List[str]) -> List[str]:
        """Filters a list of relative paths returning only non-ignored files."""
        return [p for p in file_paths if not self.is_ignored(p)]
