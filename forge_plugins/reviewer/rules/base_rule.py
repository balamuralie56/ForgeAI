"""
Base abstract definition for static analysis code review rules.
"""

import ast
from abc import ABC, abstractmethod
from typing import Optional
from forge_plugins.reviewer.models import ReviewFinding
from forge_plugins.security.models import Severity


class ReviewRule(ABC):
    """
    Abstract interface for AST static code quality / SOLID review rules.
    """

    @property
    @abstractmethod
    def rule_id(self) -> str:
        """The identifier of the rule (e.g., REV-001)."""
        pass

    @property
    @abstractmethod
    def category(self) -> str:
        """The category of the rule (e.g., Complexity, Design, Documentation)."""
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
    def principle(self) -> Optional[str]:
        """SOLID principle this rule acts as a proxy for, if any. Default: None."""
        return None

    @property
    @abstractmethod
    def description(self) -> str:
        """Elaborate description of the code quality issue."""
        pass

    @property
    @abstractmethod
    def recommendation(self) -> str:
        """Remediation guidance."""
        pass

    @abstractmethod
    def check_node(self, node: ast.AST, file_path: str) -> Optional[ReviewFinding]:
        """
        Analyzes an AST node to verify compliance with this review check.

        Args:
            node (ast.AST): The AST node to check.
            file_path (str): Relative or absolute file path being scanned.

        Returns:
            Optional[ReviewFinding]: The violation finding, or None.
        """
        pass

    def create_finding(
        self,
        file_path: str,
        line_number: int,
        details: Optional[str] = None,
        custom_severity: Optional[Severity] = None,
    ) -> ReviewFinding:
        """
        Helper method to instantiate a ReviewFinding from a rule violation.
        """
        import uuid
        import hashlib

        desc = details if details else self.description
        sev = custom_severity if custom_severity else self.severity

        fingerprint_content = f"{self.rule_id}:{file_path}:{line_number}:{desc}"
        fingerprint = hashlib.sha256(fingerprint_content.encode("utf-8")).hexdigest()

        return ReviewFinding(
            id=str(uuid.uuid4()),
            rule_id=self.rule_id,
            category=self.category,
            title=self.title,
            description=desc,
            severity=sev,
            confidence=self.confidence,
            principle=self.principle,
            file_path=file_path,
            line_number=line_number,
            recommendation=self.recommendation,
            fingerprint=fingerprint,
        )
