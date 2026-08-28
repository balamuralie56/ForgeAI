"""
Review rule detecting unexplained numeric literals used directly in comparisons.
"""

import ast
from typing import Optional
from forge_plugins.security.models import Severity
from forge_plugins.reviewer.models import ReviewFinding
from .base_rule import ReviewRule
from .registry import register_rule

# Values excluded as self-explanatory (indices, booleans-as-int, percentages, common bases).
_ALLOWED_NUMBERS = {0, 1, -1, 2, 10, 100, 1000}


def _is_magic_constant(value: ast.expr) -> bool:
    return (
        isinstance(value, ast.Constant)
        and isinstance(value.value, (int, float))
        and not isinstance(value.value, bool)
        and value.value not in _ALLOWED_NUMBERS
    )


class MagicNumberRule(ReviewRule):
    """Flags bare numeric literals used in comparisons instead of a named constant."""

    @property
    def rule_id(self) -> str:
        return "REV-005-MAGICNUMBER"

    @property
    def category(self) -> str:
        return "Readability"

    @property
    def title(self) -> str:
        return "Magic Number in Comparison"

    @property
    def severity(self) -> Severity:
        return Severity.LOW

    @property
    def confidence(self) -> str:
        return "LOW"

    @property
    def description(self) -> str:
        return "An unexplained numeric literal in a comparison obscures why that specific threshold matters."

    @property
    def recommendation(self) -> str:
        return "Extract the value into a named constant (e.g. MAX_RETRIES = 3) so the intent is documented at its definition."

    def check_node(self, node: ast.AST, file_path: str) -> Optional[ReviewFinding]:
        if isinstance(node, ast.Compare):
            values = [node.left, *node.comparators]
            for value in values:
                if isinstance(value, ast.Constant) and _is_magic_constant(value):
                    return self.create_finding(
                        file_path,
                        node.lineno,
                        details=f"Comparison uses unexplained literal '{value.value!r}' instead of a named constant.",
                    )
        return None


register_rule(MagicNumberRule())
