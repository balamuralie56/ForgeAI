"""
Security rule detecting dangerous subprocess invocations running with shell=True.
"""

import ast
from typing import Optional
from forge_plugins.security.models import Severity, SecurityFinding
from .base_rule import SecurityRule
from .registry import register_rule


class ShellRule(SecurityRule):
    """Detects usage of subprocess utilities executed with shell=True."""

    @property
    def rule_id(self) -> str:
        return "SEC-003-SHELL"

    @property
    def category(self) -> str:
        return "ShellInjection"

    @property
    def title(self) -> str:
        return "Subprocess Run with shell=True"

    @property
    def severity(self) -> Severity:
        return Severity.HIGH

    @property
    def confidence(self) -> str:
        return "HIGH"

    @property
    def cwe(self) -> Optional[str]:
        return "CWE-78"

    @property
    def owasp(self) -> Optional[str]:
        return "A03:2021-Injection"

    @property
    def description(self) -> str:
        return "Invoking system shells with shell=True invites command injection vulnerability if user parameters are loaded."

    @property
    def recommendation(self) -> str:
        return "Set shell=False and pass command parameters as a list of strings instead of single formatted string."

    def check_node(self, node: ast.AST, file_path: str) -> Optional[SecurityFinding]:
        if isinstance(node, ast.Call):
            # Check if subprocess is called (e.g. subprocess.run, subprocess.Popen)
            is_subprocess = False
            func = node.func
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                val_id = func.value.id
                if val_id == "subprocess" or (val_id == "os" and func.attr == "system"):
                    is_subprocess = True
            elif isinstance(func, ast.Name) and func.id in (
                "run",
                "Popen",
                "call",
                "check_output",
                "system",
            ):
                is_subprocess = True

            if is_subprocess:
                # If it's os.system, flag it directly as high
                if (
                    isinstance(func, ast.Attribute)
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "os"
                    and func.attr == "system"
                ):
                    return self.create_finding(
                        file_path,
                        node.lineno,
                        details="Use of os.system detected. Direct command execution bypasses argument escaping.",
                    )
                elif isinstance(func, ast.Name) and func.id == "system":
                    return self.create_finding(
                        file_path,
                        node.lineno,
                        details="Use of system() command execution detected.",
                    )

                # For subprocess, scan keyword arguments for shell=True
                for keyword in node.keywords:
                    if keyword.arg == "shell":
                        if (
                            isinstance(keyword.value, ast.Constant)
                            and keyword.value.value is True
                        ):
                            return self.create_finding(file_path, node.lineno)
        return None


# Auto-register rule
register_rule(ShellRule())
