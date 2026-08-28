"""
Review rule detecting oversized abstract interfaces - an Interface Segregation
Principle proxy: implementers are forced to satisfy methods they may not need.
"""

import ast
from typing import Optional
from forge_plugins.security.models import Severity
from forge_plugins.reviewer.models import ReviewFinding
from .base_rule import ReviewRule
from .registry import register_rule

MAX_ABSTRACT_METHODS = 7


def _is_abstract(method: ast.stmt) -> bool:
    if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    for dec in method.decorator_list:
        name = dec.id if isinstance(dec, ast.Name) else getattr(dec, "attr", None)
        if name == "abstractmethod":
            return True
    return False


class FatInterfaceRule(ReviewRule):
    """Flags abstract base classes / Protocols that demand too many methods from implementers."""

    @property
    def rule_id(self) -> str:
        return "REV-009-FATINTERFACE"

    @property
    def category(self) -> str:
        return "Design"

    @property
    def title(self) -> str:
        return "Fat Interface (ISP Violation)"

    @property
    def severity(self) -> Severity:
        return Severity.LOW

    @property
    def confidence(self) -> str:
        return "MEDIUM"

    @property
    def principle(self) -> Optional[str]:
        return "ISP"

    @property
    def description(self) -> str:
        return f"An interface with more than {MAX_ABSTRACT_METHODS} abstract methods forces every implementer to satisfy methods it may not actually need, violating the Interface Segregation Principle."

    @property
    def recommendation(self) -> str:
        return "Split the interface into smaller, role-specific protocols that implementers can compose only the ones they need."

    def check_node(self, node: ast.AST, file_path: str) -> Optional[ReviewFinding]:
        if isinstance(node, ast.ClassDef):
            abstract_count = sum(1 for item in node.body if _is_abstract(item))
            if abstract_count > MAX_ABSTRACT_METHODS:
                return self.create_finding(
                    file_path,
                    node.lineno,
                    details=f"Interface '{node.name}' declares {abstract_count} abstract methods (limit: {MAX_ABSTRACT_METHODS}).",
                )
        return None


register_rule(FatInterfaceRule())
