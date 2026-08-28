"""
Review rule detecting deeply nested control flow within a single function.
"""

import ast
from typing import Optional
from forge_plugins.security.models import Severity
from forge_plugins.reviewer.models import ReviewFinding
from .base_rule import ReviewRule
from .registry import register_rule

MAX_NESTING_DEPTH = 4
_NESTING_NODE_TYPES = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.With,
    ast.AsyncWith,
    ast.Try,
)


def _max_depth(body: list, current: int = 0) -> int:
    """Recursively computes the deepest level of nested control-flow blocks in a statement list."""
    deepest = current
    for stmt in body:
        if isinstance(stmt, _NESTING_NODE_TYPES):
            child_bodies = [getattr(stmt, "body", [])]
            if isinstance(stmt, ast.If):
                child_bodies.append(stmt.orelse)
            if isinstance(stmt, ast.Try):
                for handler in stmt.handlers:
                    child_bodies.append(handler.body)
                child_bodies.append(stmt.orelse)
                child_bodies.append(stmt.finalbody)
            for child in child_bodies:
                deepest = max(deepest, _max_depth(child, current + 1))
        else:
            for attr in ("body", "orelse"):
                nested = getattr(stmt, attr, None)
                if isinstance(nested, list):
                    deepest = max(deepest, _max_depth(nested, current))
    return deepest


class DeepNestingRule(ReviewRule):
    """Flags functions whose control flow nests beyond a readable depth."""

    @property
    def rule_id(self) -> str:
        return "REV-004-DEEPNESTING"

    @property
    def category(self) -> str:
        return "Complexity"

    @property
    def title(self) -> str:
        return "Excessive Nesting Depth"

    @property
    def severity(self) -> Severity:
        return Severity.LOW

    @property
    def confidence(self) -> str:
        return "MEDIUM"

    @property
    def description(self) -> str:
        return f"Control flow nested more than {MAX_NESTING_DEPTH} levels deep is difficult to follow and test exhaustively."

    @property
    def recommendation(self) -> str:
        return "Use guard clauses / early returns, or extract inner blocks into their own functions to flatten the structure."

    def check_node(self, node: ast.AST, file_path: str) -> Optional[ReviewFinding]:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            depth = _max_depth(node.body)
            if depth > MAX_NESTING_DEPTH:
                return self.create_finding(
                    file_path,
                    node.lineno,
                    details=f"Function '{node.name}' nests control flow {depth} levels deep (limit: {MAX_NESTING_DEPTH}).",
                )
        return None


register_rule(DeepNestingRule())
