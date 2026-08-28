"""
Base abstract definition for static analysis security rules.
"""

import ast
from abc import ABC, abstractmethod
from typing import Optional
from forge_plugins.security.models import SecurityFinding, Severity


class SecurityRule(ABC):
    """
    Abstract interface for AST static code analysis rules.
    """

    @property
    @abstractmethod
    def rule_id(self) -> str:
        """The identifier of the rule (e.g., SEC-001)."""
        pass

    @property
    @abstractmethod
    def category(self) -> str:
        """The category of the rule (e.g., Injection, Cryptography)."""
        pass

    @property
    @abstractmethod
    def title(self) -> str:
        """A short descriptive title."""
        pass

    @property
    @abstractmethod
    def severity(self) -> Severity:
        """Default severity for rule violations."""
        pass

    @property
    @abstractmethod
    def confidence(self) -> str:
        """Scan confidence (HIGH, MEDIUM, LOW)."""
        pass

    @property
    @abstractmethod
    def cwe(self) -> Optional[str]:
        """CWE code if applicable."""
        pass

    @property
    @abstractmethod
    def owasp(self) -> Optional[str]:
        """OWASP category code if applicable."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Elaborate description of the security issue."""
        pass

    @property
    @abstractmethod
    def recommendation(self) -> str:
        """Remediation instructions."""
        pass

    @abstractmethod
    def check_node(self, node: ast.AST, file_path: str) -> Optional[SecurityFinding]:
        """
        Analyzes an AST node to verify compliance with this security check.

        Args:
            node (ast.AST): The AST node to check.
            file_path (str): Relative or absolute file path being scanned.

        Returns:
            Optional[SecurityFinding]: The violation finding, or None.
        """
        pass

    def create_finding(
        self,
        file_path: str,
        line_number: int,
        details: Optional[str] = None,
        custom_severity: Optional[Severity] = None,
    ) -> SecurityFinding:
        """
        Helper method to instantiate a SecurityFinding from a rule violation.
        """
        import uuid
        import hashlib

        desc = details if details else self.description
        sev = custom_severity if custom_severity else self.severity

        # Generate a stable fingerprint using SHA256 of stable attributes
        fingerprint_content = f"{self.rule_id}:{file_path}:{line_number}:{desc}"
        fingerprint = hashlib.sha256(fingerprint_content.encode("utf-8")).hexdigest()

        return SecurityFinding(
            id=str(uuid.uuid4()),
            rule_id=self.rule_id,
            category=self.category,
            title=self.title,
            description=desc,
            severity=sev,
            confidence=self.confidence,
            cwe=self.cwe,
            owasp=self.owasp,
            file_path=file_path,
            line_number=line_number,
            recommendation=self.recommendation,
            fingerprint=fingerprint,
        )
