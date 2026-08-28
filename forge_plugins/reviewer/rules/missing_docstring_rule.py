"""
Review rule detecting public functions/classes missing a docstring.
"""

import ast
from typing import Optional
from forge_plugins.security.models import Severity
from forge_plugins.reviewer.models import ReviewFinding
from .base_rule import ReviewRule
from .registry import register_rule


def _has_docstring(node: ast.AST) -> bool:
    body = getattr(node, "body", None)
    if not body:
        return False
    first = body[0]
    return (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    )


class MissingDocstringRule(ReviewRule):
    """Flags public functions and classes with no docstring."""

    @property
    def rule_id(self) -> str:
        return "REV-006-NODOCSTRING"

    @property
    def category(self) -> str:
        return "Documentation"

    @property
    def title(self) -> str:
        return "Missing Docstring"

    @property
    def severity(self) -> Severity:
        return Severity.INFO

    @property
    def confidence(self) -> str:
        return "HIGH"

    @property
    def description(self) -> str:
        return "Public functions and classes without a docstring leave their contract undocumented for callers and future maintainers."

    @property
    def recommendation(self) -> str:
        return "Add a short docstring stating what the function/class does, its parameters, and what it returns or raises."

    def check_node(self, node: ast.AST, file_path: str) -> Optional[ReviewFinding]:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name.startswith("_"):
                return None
            if not _has_docstring(node):
                kind = "Class" if isinstance(node, ast.ClassDef) else "Function"
                return self.create_finding(
                    file_path,
                    node.lineno,
                    details=f"{kind} '{node.name}' has no docstring.",
                )
        return None


register_rule(MissingDocstringRule())
