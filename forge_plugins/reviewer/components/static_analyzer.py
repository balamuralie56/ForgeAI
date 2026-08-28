"""
Static analyzer iterating workspace files, invoking review rule checks.
Reuses the Security plugin's SecurityIgnoreEngine, which is purely a generic
path/pattern exclusion utility with no security-specific behavior.
"""

from pathlib import Path
from typing import Dict, List
from forge_plugins.reviewer.models import ReviewFinding
from forge_plugins.reviewer.rules import registry
from forge_plugins.security.components.ignore_engine import SecurityIgnoreEngine
from .analyzer_factory import ReviewAnalyzerFactory


class ReviewStaticAnalyzer:
    """Orchestrates static review scans across workspace files using language analyzers."""

    def __init__(
        self, workspace_path: str, ignore_engine: SecurityIgnoreEngine
    ) -> None:
        self.workspace = Path(workspace_path)
        self.ignore_engine = ignore_engine
        self.factory = ReviewAnalyzerFactory(workspace_path)

    def scan_files(self, rule_policy: Dict[str, bool]) -> List[ReviewFinding]:
        """Scans all non-ignored source files in the workspace."""
        findings: List[ReviewFinding] = []
        enabled_rules = registry.get_enabled_rules(rule_policy)

        if not enabled_rules:
            return findings

        file_paths: List[str] = []
        try:
            for item in self.workspace.rglob("*"):
                if item.is_file():
                    rel_path = str(item.relative_to(self.workspace))
                    file_paths.append(rel_path)
        except Exception:
            pass

        non_ignored_paths = self.ignore_engine.filter_paths(file_paths)

        for rel_path in non_ignored_paths:
            analyzer = self.factory.get_analyzer(rel_path)
            findings.extend(analyzer.analyze_file(rel_path, enabled_rules))

        return findings
