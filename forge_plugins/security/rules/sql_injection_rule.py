"""
Security rule detecting potential SQL injection vulnerabilities in string formatted execution calls.
"""

import ast
from typing import Optional
from forge_plugins.security.models import Severity, SecurityFinding
from .base_rule import SecurityRule
from .registry import register_rule


class SqlInjectionRule(SecurityRule):
    """Detects usage of SQL execution calls using dynamic string formatting instead of query arguments."""

    @property
    def rule_id(self) -> str:
        return "SEC-007-SQL"

    @property
    def category(self) -> str:
        return "Injection"

    @property
    def title(self) -> str:
        return "Potential SQL Injection"

    @property
    def severity(self) -> Severity:
        return Severity.HIGH

    @property
    def confidence(self) -> str:
        return "MEDIUM"

    @property
    def cwe(self) -> Optional[str]:
        return "CWE-89"

    @property
    def owasp(self) -> Optional[str]:
        return "A03:2021-Injection"

    @property
    def description(self) -> str:
        return "Building SQL queries dynamically using string concatenation, f-strings, or % format formatting is vulnerable to SQL injection."

    @property
    def recommendation(self) -> str:
        return "Use parameterized queries with placeholders (e.g. 'SELECT * FROM users WHERE id = ?', (user_id,)) instead of formatted query strings."

    def check_node(self, node: ast.AST, file_path: str) -> Optional[SecurityFinding]:
        if isinstance(node, ast.Call):
            func = node.func
            is_execute = False
            if isinstance(func, ast.Attribute):
                if func.attr in ("execute", "executemany"):
                    is_execute = True
            elif isinstance(func, ast.Name):
                if func.id in ("execute", "executemany"):
                    is_execute = True

            if is_execute and len(node.args) >= 1:
                query_arg = node.args[0]
                # Check if query arg is constructed using f-string, format, or percentage strings
                is_dynamic = False
                if isinstance(query_arg, ast.JoinedStr):  # f-string
                    is_dynamic = True
                elif isinstance(query_arg, ast.BinOp) and isinstance(
                    query_arg.op, ast.Mod
                ):  # query % args
                    is_dynamic = True
                elif isinstance(query_arg, ast.Call):
                    # check if calling query.format(...) or similar
                    sub_func = query_arg.func
                    if (
                        isinstance(sub_func, ast.Attribute)
                        and sub_func.attr == "format"
                    ):
                        is_dynamic = True

                if is_dynamic:
                    return self.create_finding(
                        file_path,
                        node.lineno,
                        details="SQL query execution built dynamically via string formatting. Use query parameter mapping instead.",
                    )
        return None


# Auto-register rule
register_rule(SqlInjectionRule())
