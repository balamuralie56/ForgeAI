"""
Review rule detecting functions/methods that have grown too long to reason about easily.
"""

import ast
from typing import Optional
from forge_plugins.security.models import Severity
from forge_plugins.reviewer.models import ReviewFinding
from .base_rule import ReviewRule
from .registry import register_rule

MAX_FUNCTION_LINES = 50


class LongFunctionRule(ReviewRule):
    """Flags function/method bodies exceeding a maintainable line count."""

    @property
    def rule_id(self) -> str:
        return "REV-001-LONGFUNC"

    @property
    def category(self) -> str:
        return "Complexity"

    @property
    def title(self) -> str:
        return "Function Too Long"

    @property
    def severity(self) -> Severity:
        return Severity.MEDIUM

    @property
    def confidence(self) -> str:
        return "HIGH"

    @property
    def description(self) -> str:
        return f"Functions longer than {MAX_FUNCTION_LINES} lines are harder to test, review, and reason about in one pass."

    @property
    def recommendation(self) -> str:
        return "Extract cohesive blocks into well-named helper functions until each function fits on a single screen."

    def check_node(self, node: ast.AST, file_path: str) -> Optional[ReviewFinding]:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end_line = getattr(node, "end_lineno", None)
            if end_line is None:
                return None
            length = end_line - node.lineno
            if length > MAX_FUNCTION_LINES:
                return self.create_finding(
                    file_path,
                    node.lineno,
                    details=f"Function '{node.name}' is {length} lines long (limit: {MAX_FUNCTION_LINES}).",
                )
        return None


register_rule(LongFunctionRule())
