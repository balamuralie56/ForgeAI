"""
Security rule detecting insecure tempfile creations using tempfile.mktemp().
"""

import ast
from typing import Optional
from forge_plugins.security.models import Severity, SecurityFinding
from .base_rule import SecurityRule
from .registry import register_rule


class TempFileRule(SecurityRule):
    """Detects usage of the insecure tempfile.mktemp() call."""

    @property
    def rule_id(self) -> str:
        return "SEC-008-TEMPFILE"

    @property
    def category(self) -> str:
        return "InsecureTemporaryFile"

    @property
    def title(self) -> str:
        return "Insecure mktemp() Call"

    @property
    def severity(self) -> Severity:
        return Severity.MEDIUM

    @property
    def confidence(self) -> str:
        return "HIGH"

    @property
    def cwe(self) -> Optional[str]:
        return "CWE-377"

    @property
    def owasp(self) -> Optional[str]:
        return "A01:2021-Broken Access Control"

    @property
    def description(self) -> str:
        return "Use of tempfile.mktemp() is deprecated and introduces file creation race condition vulnerabilities."

    @property
    def recommendation(self) -> str:
        return "Use tempfile.TemporaryFile() or tempfile.NamedTemporaryFile() which securely open files during creation."

    def check_node(self, node: ast.AST, file_path: str) -> Optional[SecurityFinding]:
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                if func.value.id == "tempfile" and func.attr == "mktemp":
                    return self.create_finding(file_path, node.lineno)
            elif isinstance(func, ast.Name) and func.id == "mktemp":
                return self.create_finding(file_path, node.lineno)
        return None


# Auto-register rule
register_rule(TempFileRule())
