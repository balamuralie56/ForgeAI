"""
Data models representing code review findings, reports, and execution manifests.
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from forge_plugins.security.models import Severity

# SOLID principles a finding may relate to. Liskov Substitution is deliberately
# absent - detecting it correctly requires cross-class contract analysis (does an
# override actually honor the base class's pre/post-conditions?), which this
# plugin's per-node AST rule interface cannot see. Rather than ship a rule that
# would misfire constantly, SOLID scoring reports "L" as not evaluated.
SOLID_PRINCIPLES = ("SRP", "OCP", "ISP", "DIP")


@dataclass(frozen=True)
class ReviewFinding:
    """
    Represents a single code quality / maintainability finding.
    """

    id: str
    rule_id: str
    category: str
    title: str
    description: str
    severity: Severity
    confidence: str  # HIGH, MEDIUM, LOW
    principle: Optional[str]  # One of SOLID_PRINCIPLES, or None for general smells
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
    def from_dict(cls, data: Dict[str, Any]) -> "ReviewFinding":
        """Deserializes a finding from its dictionary representation."""
        return cls(
            id=data["id"],
            rule_id=data["rule_id"],
            category=data["category"],
            title=data["title"],
            description=data["description"],
            severity=Severity(data["severity"]),
            confidence=data["confidence"],
            principle=data.get("principle"),
            file_path=data.get("file_path"),
            line_number=data.get("line_number"),
            recommendation=data["recommendation"],
            fingerprint=data["fingerprint"],
            references=data.get("references") or [],
        )


@dataclass(frozen=True)
class ReviewReport:
    """
    Represents the full compiled code review results.
    """

    project_id: str
    findings: List[ReviewFinding]
    quality_score: float  # 0-100, higher is better
    solid_scores: Dict[
        str, Optional[float]
    ]  # per-principle 0-100, None = not evaluated
    status: str  # PASSED, FAILED
    summary: str
    recommendations: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the report to a dictionary representation."""
        return {
            "project_id": self.project_id,
            "findings": [finding.to_dict() for finding in self.findings],
            "quality_score": self.quality_score,
            "solid_scores": self.solid_scores,
            "status": self.status,
            "summary": self.summary,
            "recommendations": self.recommendations,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReviewReport":
        """Deserializes a report from its dictionary representation."""
        return cls(
            project_id=data["project_id"],
            findings=[ReviewFinding.from_dict(f) for f in data.get("findings") or []],
            quality_score=data.get("quality_score", 100.0),
            solid_scores=data.get("solid_scores") or {},
            status=data.get("status", "PASSED"),
            summary=data.get("summary", ""),
            recommendations=data.get("recommendations") or [],
        )


@dataclass(frozen=True)
class ReviewManifest:
    """
    Represents metadata details of a review scan run for build integrations.
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
    def from_dict(cls, data: Dict[str, Any]) -> "ReviewManifest":
        """Deserializes a manifest from its dictionary representation."""
        return cls(
            files_scanned=data.get("files_scanned") or [],
            scan_duration_ms=data.get("scan_duration_ms", 0),
            rules_run=data.get("rules_run") or [],
            ignored_files=data.get("ignored_files") or [],
            tool_version=data.get("tool_version", "1.0.0"),
            timestamp=data.get("timestamp", 0.0),
        )
