"""
Review rule detecting long isinstance()/type() dispatch chains - an Open/Closed
Principle proxy: each new case requires editing this function instead of adding
a new type that plugs in through polymorphism.
"""

import ast
from typing import Optional
from forge_plugins.security.models import Severity
from forge_plugins.reviewer.models import ReviewFinding
from .base_rule import ReviewRule
from .registry import register_rule

MIN_CHAIN_LENGTH = 3


def _target_name(test: ast.expr) -> Optional[str]:
    """Extracts the variable name being type-checked from an isinstance()/type() test."""
    if (
        isinstance(test, ast.Call)
        and isinstance(test.func, ast.Name)
        and test.func.id == "isinstance"
        and test.args
        and isinstance(test.args[0], ast.Name)
    ):
        return test.args[0].id
    if (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Call)
        and isinstance(test.left.func, ast.Name)
        and test.left.func.id == "type"
        and test.left.args
        and isinstance(test.left.args[0], ast.Name)
    ):
        return test.left.args[0].id
    return None


def _chain_length(node: ast.If, subject: str) -> int:
    """Counts how many consecutive elif branches (starting at node) test the same subject."""
    if _target_name(node.test) != subject:
        return 0
    if len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If):
        return 1 + _chain_length(node.orelse[0], subject)
    return 1


class TypeCheckChainRule(ReviewRule):
    """Flags long isinstance()/type()-based elif dispatch chains on the same variable."""

    @property
    def rule_id(self) -> str:
        return "REV-008-TYPECHECKCHAIN"

    @property
    def category(self) -> str:
        return "Design"

    @property
    def title(self) -> str:
        return "Type-Check Dispatch Chain (OCP Violation)"

    @property
    def severity(self) -> Severity:
        return Severity.MEDIUM

    @property
    def confidence(self) -> str:
        return "MEDIUM"

    @property
    def principle(self) -> Optional[str]:
        return "OCP"

    @property
    def description(self) -> str:
        return f"A chain of {MIN_CHAIN_LENGTH}+ isinstance()/type() branches on one variable means adding a new case requires modifying this function, violating the Open/Closed Principle."

    @property
    def recommendation(self) -> str:
        return "Replace the dispatch chain with polymorphism (a method each type implements) or a lookup table keyed by type."

    def check_node(self, node: ast.AST, file_path: str) -> Optional[ReviewFinding]:
        if isinstance(node, ast.If):
            subject = _target_name(node.test)
            if subject:
                length = _chain_length(node, subject)
                if length >= MIN_CHAIN_LENGTH:
                    return self.create_finding(
                        file_path,
                        node.lineno,
                        details=f"{length}-branch isinstance/type chain on '{subject}'.",
                    )
        return None


register_rule(TypeCheckChainRule())
