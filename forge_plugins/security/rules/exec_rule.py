"""
Security rule detecting unsafe dynamic code execution via exec().
"""

import ast
from typing import Optional
from forge_plugins.security.models import Severity, SecurityFinding
from .base_rule import SecurityRule
from .registry import register_rule


class ExecRule(SecurityRule):
    """Detects usage of the unsafe exec() built-in function."""

    @property
    def rule_id(self) -> str:
        return "SEC-002-EXEC"

    @property
    def category(self) -> str:
        return "Injection"

    @property
    def title(self) -> str:
        return "Unsafe exec() Call"

    @property
    def severity(self) -> Severity:
        return Severity.CRITICAL

    @property
    def confidence(self) -> str:
        return "HIGH"

    @property
    def cwe(self) -> Optional[str]:
        return "CWE-95"

    @property
    def owasp(self) -> Optional[str]:
        return "A03:2021-Injection"

    @property
    def description(self) -> str:
        return "Use of exec() detected. Dynamic code execution of untrusted input can result in severe system compromises."

    @property
    def recommendation(self) -> str:
        return "Refactor design to avoid exec(). Do not execute raw string blocks as executable python statements."

    def check_node(self, node: ast.AST, file_path: str) -> Optional[SecurityFinding]:
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "exec":
                return self.create_finding(file_path, node.lineno)
        return None


# Auto-register rule
register_rule(ExecRule())
