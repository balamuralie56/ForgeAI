"""
Security rule detecting hardcoded passwords, tokens, or credentials in assignments.
"""

import ast
import re
from typing import Optional
from forge_plugins.security.models import Severity, SecurityFinding
from .base_rule import SecurityRule
from .registry import register_rule


class HardcodedPasswordRule(SecurityRule):
    """Detects assignments of passwords, keys, or secret variables to string constants."""

    _KEY_PATTERNS = re.compile(
        r".*(password|passwd|secret|token|api_key|apikey|private_key|auth_token|jwt_secret|passphrase).*",
        re.IGNORECASE,
    )

    @property
    def rule_id(self) -> str:
        return "SEC-006-HARDCODED"

    @property
    def category(self) -> str:
        return "Credentials"

    @property
    def title(self) -> str:
        return "Hardcoded Credential"

    @property
    def severity(self) -> Severity:
        return Severity.HIGH

    @property
    def confidence(self) -> str:
        return "MEDIUM"

    @property
    def cwe(self) -> Optional[str]:
        return "CWE-798"

    @property
    def owasp(self) -> Optional[str]:
        return "A07:2021-Identification and Authentication Failures"

    @property
    def description(self) -> str:
        return "Hardcoding passwords, keys, or credentials directly in source files risks token leakage through repository logs."

    @property
    def recommendation(self) -> str:
        return "Move passwords and keys to environment variables or local git-ignored configurations."

    def check_node(self, node: ast.AST, file_path: str) -> Optional[SecurityFinding]:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                target_name = ""
                if isinstance(target, ast.Name):
                    target_name = target.id
                elif isinstance(target, ast.Attribute):
                    target_name = target.attr

                if target_name and self._KEY_PATTERNS.match(target_name):
                    # Check if the assigned value is a non-empty string constant
                    val = node.value
                    if isinstance(val, ast.Constant):
                        val_val = val.value
                        if isinstance(val_val, str) and len(val_val) > 0:
                            val_str = val_val.lower()
                            if val_str not in (
                                "placeholder",
                                "test",
                                "dummy",
                                "admin",
                                "password",
                                "123456",
                                "",
                            ):
                                return self.create_finding(
                                    file_path,
                                    node.lineno,
                                    details=f"Variable '{target_name}' assigned to hardcoded string constant.",
                                )
        return None


# Auto-register rule
register_rule(HardcodedPasswordRule())
