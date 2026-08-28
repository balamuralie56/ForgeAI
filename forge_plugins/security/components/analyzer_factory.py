"""
Factory resolving language-specific static code analyzers.
"""

import ast
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List
from forge_plugins.security.models import SecurityFinding
from forge_plugins.security.rules.base_rule import SecurityRule


class BaseLanguageAnalyzer(ABC):
    """
    Abstract interface for parsing and analyzing source files of a specific language.
    """

    @abstractmethod
    def analyze_file(
        self, relative_path: str, rules: List[SecurityRule]
    ) -> List[SecurityFinding]:
        """
        Parses and audits a file, returning any detected vulnerabilities.
        """
        pass


class PythonAnalyzer(BaseLanguageAnalyzer):
    """
    AST-based Python source file analyzer.
    """

    def __init__(self, workspace_path: str) -> None:
        self.workspace = Path(workspace_path)

    def analyze_file(
        self, relative_path: str, rules: List[SecurityRule]
    ) -> List[SecurityFinding]:
        findings: List[SecurityFinding] = []
        file_path = self.workspace / relative_path

        if not file_path.exists():
            return findings

        try:
            source = file_path.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(source, filename=str(file_path))

            for node in ast.walk(tree):
                for rule in rules:
                    try:
                        finding = rule.check_node(node, relative_path)
                        if finding:
                            findings.append(finding)
                    except Exception:
                        pass
        except Exception:
            # Skip syntax errors or parse failures
            pass

        return findings


class GenericAnalyzer(BaseLanguageAnalyzer):
    """
    Fallback analyzer returning empty results for unsupported extensions.
    """

    def analyze_file(
        self, relative_path: str, rules: List[SecurityRule]
    ) -> List[SecurityFinding]:
        return []


class AnalyzerFactory:
    """
    Factory class resolving language-specific code analyzers.
    """

    def __init__(self, workspace_path: str) -> None:
        self.workspace = workspace_path
        self._python_analyzer = PythonAnalyzer(workspace_path)
        self._generic_analyzer = GenericAnalyzer()

    def get_analyzer(self, file_path: str) -> BaseLanguageAnalyzer:
        """
        Resolves the appropriate analyzer based on file extension.
        """
        ext = Path(file_path).suffix.lower()
        if ext == ".py":
            return self._python_analyzer
        return self._generic_analyzer
