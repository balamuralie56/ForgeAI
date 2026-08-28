"""
Static analyzer iterating files, invoking language-specific rule checks.
"""

from pathlib import Path
from typing import Dict, List
from forge_plugins.security.models import SecurityFinding
from forge_plugins.security.rules import registry
from .ignore_engine import SecurityIgnoreEngine
from .analyzer_factory import AnalyzerFactory


class StaticAnalyzer:
    """
    Orchestrates static analysis scans across workspace files using language analyzers.
    """

    def __init__(
        self, workspace_path: str, ignore_engine: SecurityIgnoreEngine
    ) -> None:
        self.workspace = Path(workspace_path)
        self.ignore_engine = ignore_engine
        self.factory = AnalyzerFactory(workspace_path)

    def scan_files(self, rule_policy: Dict[str, bool]) -> List[SecurityFinding]:
        """
        Scans all non-ignored source files in the workspace.
        """
        findings: List[SecurityFinding] = []
        enabled_rules = registry.get_enabled_rules(rule_policy)

        if not enabled_rules:
            return findings

        # Recursively search for files in workspace
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
