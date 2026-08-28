"""
Security rule detecting unsafe dynamic code execution via eval().
"""

import ast
from typing import Optional
from forge_plugins.security.models import Severity, SecurityFinding
from .base_rule import SecurityRule
from .registry import register_rule


class EvalRule(SecurityRule):
    """Detects usage of the unsafe eval() built-in function."""

    @property
    def rule_id(self) -> str:
        return "SEC-001-EVAL"

    @property
    def category(self) -> str:
        return "Injection"

    @property
    def title(self) -> str:
        return "Unsafe eval() Call"

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
        return "Use of eval() detected. Passing untrusted parameters to eval() can lead to arbitrary code execution."

    @property
    def recommendation(self) -> str:
        return "Avoid using eval(). If dynamic value expression parsing is required, use ast.literal_eval() instead."

    def check_node(self, node: ast.AST, file_path: str) -> Optional[SecurityFinding]:
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "eval":
                return self.create_finding(file_path, node.lineno)
        return None


# Auto-register rule
register_rule(EvalRule())
