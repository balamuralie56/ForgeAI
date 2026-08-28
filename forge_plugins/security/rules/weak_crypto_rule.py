"""
Security rule detecting usage of legacy or insecure hash algorithms (MD5, SHA1).
"""

import ast
from typing import Optional
from forge_plugins.security.models import Severity, SecurityFinding
from .base_rule import SecurityRule
from .registry import register_rule


class WeakCryptoRule(SecurityRule):
    """Detects usage of weak cryptographic hash functions (MD5, SHA1)."""

    @property
    def rule_id(self) -> str:
        return "SEC-005-WEAKCRYPTO"

    @property
    def category(self) -> str:
        return "Cryptography"

    @property
    def title(self) -> str:
        return "Legacy Hash Algorithm"

    @property
    def severity(self) -> Severity:
        return Severity.MEDIUM

    @property
    def confidence(self) -> str:
        return "HIGH"

    @property
    def cwe(self) -> Optional[str]:
        return "CWE-328"

    @property
    def owasp(self) -> Optional[str]:
        return "A02:2021-Cryptographic Failures"

    @property
    def description(self) -> str:
        return "MD5 and SHA1 hash algorithms are cryptographically broken and vulnerable to collision attacks."

    @property
    def recommendation(self) -> str:
        return "Upgrade algorithms to secure alternatives like SHA256, SHA512, or bcrypt/argon2 for password storage."

    def check_node(self, node: ast.AST, file_path: str) -> Optional[SecurityFinding]:
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                if func.value.id == "hashlib" and func.attr in ("md5", "sha1", "new"):
                    if func.attr == "new":
                        # If hashlib.new('md5') or similar is used
                        if len(node.args) >= 1 and isinstance(
                            node.args[0], ast.Constant
                        ):
                            val = str(node.args[0].value).lower()
                            if val in ("md5", "sha1"):
                                return self.create_finding(file_path, node.lineno)
                    else:
                        return self.create_finding(file_path, node.lineno)
            elif isinstance(func, ast.Name) and func.id in ("md5", "sha1"):
                return self.create_finding(file_path, node.lineno)
        return None


# Auto-register rule
register_rule(WeakCryptoRule())
