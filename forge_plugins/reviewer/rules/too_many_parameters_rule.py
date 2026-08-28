"""
Review rule detecting functions with too many parameters.
"""

import ast
from typing import Optional
from forge_plugins.security.models import Severity
from forge_plugins.reviewer.models import ReviewFinding
from .base_rule import ReviewRule
from .registry import register_rule

MAX_PARAMETERS = 5


class TooManyParametersRule(ReviewRule):
    """Flags functions/methods whose signature takes too many parameters."""

    @property
    def rule_id(self) -> str:
        return "REV-002-TOOMANYPARAMS"

    @property
    def category(self) -> str:
        return "Complexity"

    @property
    def title(self) -> str:
        return "Too Many Parameters"

    @property
    def severity(self) -> Severity:
        return Severity.LOW

    @property
    def confidence(self) -> str:
        return "HIGH"

    @property
    def description(self) -> str:
        return f"Functions with more than {MAX_PARAMETERS} parameters are hard to call correctly and usually signal missing abstraction."

    @property
    def recommendation(self) -> str:
        return "Group related parameters into a dataclass/config object, or split the function's responsibilities."

    def check_node(self, node: ast.AST, file_path: str) -> Optional[ReviewFinding]:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            count = len(args.posonlyargs) + len(args.args) + len(args.kwonlyargs)
            # 'self'/'cls' is not a design smell contributor
            if args.args and args.args[0].arg in ("self", "cls"):
                count -= 1
            if count > MAX_PARAMETERS:
                return self.create_finding(
                    file_path,
                    node.lineno,
                    details=f"Function '{node.name}' takes {count} parameters (limit: {MAX_PARAMETERS}).",
                )
        return None


register_rule(TooManyParametersRule())
