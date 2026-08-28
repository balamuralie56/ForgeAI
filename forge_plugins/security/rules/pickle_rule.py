"""
Security rule detecting unsafe object deserialization via pickle module.
"""

import ast
from typing import Optional
from forge_plugins.security.models import Severity, SecurityFinding
from .base_rule import SecurityRule
from .registry import register_rule


class PickleRule(SecurityRule):
    """Detects usage of the pickle module loads/load functions."""

    @property
    def rule_id(self) -> str:
        return "SEC-004-PICKLE"

    @property
    def category(self) -> str:
        return "Deserialization"

    @property
    def title(self) -> str:
        return "Unsafe Object Deserialization (Pickle)"

    @property
    def severity(self) -> Severity:
        return Severity.HIGH

    @property
    def confidence(self) -> str:
        return "HIGH"

    @property
    def cwe(self) -> Optional[str]:
        return "CWE-502"

    @property
    def owasp(self) -> Optional[str]:
        return "A08:2021-Software and Data Integrity Failures"

    @property
    def description(self) -> str:
        return "Loading serialized streams using pickle can trigger arbitrary code execution during instantiations."

    @property
    def recommendation(self) -> str:
        return "Do not load pickle objects from untrusted sources. Use safe formats like JSON or Protocol Buffers."

    def check_node(self, node: ast.AST, file_path: str) -> Optional[SecurityFinding]:
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                if func.value.id == "pickle" and func.attr in ("load", "loads"):
                    return self.create_finding(file_path, node.lineno)
            elif isinstance(func, ast.Name) and func.id in ("load", "loads"):
                # We can also double check imports, but if it is mapped as raw load/loads we flag as medium confidence
                return self.create_finding(
                    file_path,
                    node.lineno,
                    custom_severity=Severity.MEDIUM,
                    details="Unsafe call to load/loads detected. Ensure this is not pickle module deserialization.",
                )
        return None


# Auto-register rule
register_rule(PickleRule())
