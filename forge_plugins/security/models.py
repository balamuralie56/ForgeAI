"""
Data models representing security findings, reports, and execution manifests.
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional


class Severity(Enum):
    """Vulnerability severity categories."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


@dataclass(frozen=True)
class SecurityFinding:
    """
    Represents a specific security vulnerability or compliance check finding.
    """

    id: str
    rule_id: str
    category: str
    title: str
    description: str
    severity: Severity
    confidence: str  # HIGH, MEDIUM, LOW
    cwe: Optional[str]
    owasp: Optional[str]
    file_path: Optional[str]
    line_number: Optional[int]
    recommendation: str
    fingerprint: str
    references: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the finding to a dictionary representation."""
        data = asdict(self)
        data["severity"] = self.severity.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SecurityFinding":
        """Deserializes a finding from its dictionary representation."""
        return cls(
            id=data["id"],
            rule_id=data["rule_id"],
            category=data["category"],
            title=data["title"],
            description=data["description"],
            severity=Severity(data["severity"]),
            confidence=data["confidence"],
            cwe=data.get("cwe"),
            owasp=data.get("owasp"),
            file_path=data.get("file_path"),
            line_number=data.get("line_number"),
            recommendation=data["recommendation"],
            fingerprint=data["fingerprint"],
            references=data.get("references") or [],
        )


@dataclass(frozen=True)
class SecurityReport:
    """
    Represents the full compiled security audit results.
    """

    project_id: str
    findings: List[SecurityFinding]
    risk_score: float
    security_score: float
    status: str  # PASSED, FAILED
    summary: str
    recommendations: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the report to a dictionary representation."""
        return {
            "project_id": self.project_id,
            "findings": [finding.to_dict() for finding in self.findings],
            "risk_score": self.risk_score,
            "security_score": self.security_score,
            "status": self.status,
            "summary": self.summary,
            "recommendations": self.recommendations,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SecurityReport":
        """Deserializes a report from its dictionary representation."""
        return cls(
            project_id=data["project_id"],
            findings=[SecurityFinding.from_dict(f) for f in data.get("findings") or []],
            risk_score=data.get("risk_score", 0.0),
            security_score=data.get("security_score", 100.0),
            status=data.get("status", "PASSED"),
            summary=data.get("summary", ""),
            recommendations=data.get("recommendations") or [],
        )


@dataclass(frozen=True)
class SecurityManifest:
    """
    Represents metadata details of a security scan run for build integrations.
    """

    files_scanned: List[str]
    scan_duration_ms: int
    rules_run: List[str]
    ignored_files: List[str]
    tool_version: str
    timestamp: float

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the manifest metadata to a dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SecurityManifest":
        """Deserializes a manifest from its dictionary representation."""
        return cls(
            files_scanned=data.get("files_scanned") or [],
            scan_duration_ms=data.get("scan_duration_ms", 0),
            rules_run=data.get("rules_run") or [],
            ignored_files=data.get("ignored_files") or [],
            tool_version=data.get("tool_version", "1.0.0"),
            timestamp=data.get("timestamp", 0.0),
        )
