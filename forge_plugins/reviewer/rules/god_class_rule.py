"""
Review rule detecting "God Classes" - a Single Responsibility Principle proxy.
"""

import ast
from typing import Optional
from forge_plugins.security.models import Severity
from forge_plugins.reviewer.models import ReviewFinding
from .base_rule import ReviewRule
from .registry import register_rule

MAX_METHODS = 15


class GodClassRule(ReviewRule):
    """Flags classes accumulating too many methods - usually a sign they own too many responsibilities."""

    @property
    def rule_id(self) -> str:
        return "REV-003-GODCLASS"

    @property
    def category(self) -> str:
        return "Design"

    @property
    def title(self) -> str:
        return "God Class (SRP Violation)"

    @property
    def severity(self) -> Severity:
        return Severity.MEDIUM

    @property
    def confidence(self) -> str:
        return "MEDIUM"

    @property
    def principle(self) -> Optional[str]:
        return "SRP"

    @property
    def description(self) -> str:
        return f"Classes with more than {MAX_METHODS} methods usually accumulate multiple unrelated responsibilities, violating the Single Responsibility Principle."

    @property
    def recommendation(self) -> str:
        return "Split the class along its distinct responsibilities into smaller, focused collaborators."

    def check_node(self, node: ast.AST, file_path: str) -> Optional[ReviewFinding]:
        if isinstance(node, ast.ClassDef):
            method_count = sum(
                1
                for item in node.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            )
            if method_count > MAX_METHODS:
                return self.create_finding(
                    file_path,
                    node.lineno,
                    details=f"Class '{node.name}' defines {method_count} methods (limit: {MAX_METHODS}).",
                )
        return None


register_rule(GodClassRule())
