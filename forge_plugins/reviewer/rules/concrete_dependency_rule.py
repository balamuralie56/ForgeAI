"""
Review rule detecting constructors that build their own collaborators instead of
receiving them - a Dependency Inversion Principle proxy.
"""

import ast
from typing import Optional
from forge_plugins.security.models import Severity
from forge_plugins.reviewer.models import ReviewFinding
from .base_rule import ReviewRule
from .registry import register_rule

# Naming convention (also used throughout this codebase) for classes that
# represent injectable collaborators rather than plain data/value objects.
_INJECTABLE_SUFFIXES = (
    "Service",
    "Manager",
    "Client",
    "Engine",
    "Repository",
    "Provider",
    "Handler",
)


def _callee_name(call: ast.Call) -> Optional[str]:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


class ConcreteDependencyRule(ReviewRule):
    """Flags __init__ methods that instantiate their own collaborators internally."""

    @property
    def rule_id(self) -> str:
        return "REV-010-CONCRETEDEP"

    @property
    def category(self) -> str:
        return "Design"

    @property
    def title(self) -> str:
        return "Concrete Dependency Construction (DIP Violation)"

    @property
    def severity(self) -> Severity:
        return Severity.LOW

    @property
    def confidence(self) -> str:
        return "LOW"

    @property
    def principle(self) -> Optional[str]:
        return "DIP"

    @property
    def description(self) -> str:
        return "A constructor that builds its own Service/Manager/Client/Engine/Repository collaborator hardcodes that dependency, making the class harder to test or swap - violating the Dependency Inversion Principle."

    @property
    def recommendation(self) -> str:
        return "Accept the collaborator as a constructor parameter (dependency injection) instead of instantiating it directly."

    def check_node(self, node: ast.AST, file_path: str) -> Optional[ReviewFinding]:
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "__init__"
        ):
            param_names = {a.arg for a in node.args.args} | {
                a.arg for a in node.args.kwonlyargs
            }
            for stmt in node.body:
                if not isinstance(stmt, ast.Assign):
                    continue
                if not isinstance(stmt.value, ast.Call):
                    continue
                callee = _callee_name(stmt.value)
                if not callee or not callee.endswith(_INJECTABLE_SUFFIXES):
                    continue
                # Constructing it from a parameter that was passed in (e.g. a
                # factory call using an injected registry) is not the smell.
                arg_names = {a.id for a in stmt.value.args if isinstance(a, ast.Name)}
                if callee in param_names or arg_names & param_names:
                    continue
                return self.create_finding(
                    file_path,
                    stmt.lineno,
                    details=f"__init__ directly constructs '{callee}' instead of receiving it as a dependency.",
                )
        return None


register_rule(ConcreteDependencyRule())
