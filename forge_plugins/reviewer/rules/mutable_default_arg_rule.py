"""
Review rule detecting mutable default arguments - a classic Python correctness pitfall.
"""

import ast
from typing import Optional
from forge_plugins.security.models import Severity
from forge_plugins.reviewer.models import ReviewFinding
from .base_rule import ReviewRule
from .registry import register_rule


class MutableDefaultArgRule(ReviewRule):
    """Flags function parameters whose default value is a mutable literal (list/dict/set)."""

    @property
    def rule_id(self) -> str:
        return "REV-007-MUTABLEDEFAULT"

    @property
    def category(self) -> str:
        return "Correctness"

    @property
    def title(self) -> str:
        return "Mutable Default Argument"

    @property
    def severity(self) -> Severity:
        return Severity.HIGH

    @property
    def confidence(self) -> str:
        return "HIGH"

    @property
    def description(self) -> str:
        return "Default argument values are evaluated once at function definition time, so a mutable default is shared and accumulates state across every call that doesn't pass its own value."

    @property
    def recommendation(self) -> str:
        return "Use `None` as the default and create the list/dict/set inside the function body instead."

    def check_node(self, node: ast.AST, file_path: str) -> Optional[ReviewFinding]:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defaults = list(node.args.defaults) + list(node.args.kw_defaults)
            for default in defaults:
                if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                    return self.create_finding(
                        file_path,
                        node.lineno,
                        details=f"Function '{node.name}' uses a mutable literal as a default argument value.",
                    )
        return None


register_rule(MutableDefaultArgRule())
