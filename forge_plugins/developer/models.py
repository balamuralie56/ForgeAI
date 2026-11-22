"""
Developer implementation models for ForgeAI.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Dict, List, Optional


class ImplementationStatus(StrEnum):
    """Outcome of an implementation run, derived from code validation."""

    SUCCESS = "SUCCESS"
    SUCCESS_WITH_WARNINGS = "SUCCESS_WITH_WARNINGS"
    VALIDATION_FAILED = "VALIDATION_FAILED"


class IssueSeverity(StrEnum):
    """How serious a validation finding is."""

    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class ValidationIssue:
    """
    A single problem found in a generated file.

    Attributes:
        severity (IssueSeverity): ERROR means the code will fail when run or
            imported; WARNING means it is suspicious but may still work.
        check (str): The check that raised it (e.g. "syntax", "import").
        path (str): Workspace-relative path of the offending file.
        message (str): Human-readable description.
        line (Optional[int]): 1-based line number, when known.
    """

    severity: IssueSeverity
    check: str
    path: str
    message: str
    line: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Converts to dictionary representation."""
        return {
            "severity": self.severity.value,
            "check": self.check,
            "path": self.path,
            "message": self.message,
            "line": self.line,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ValidationIssue":
        """Creates instance from dictionary."""
        return cls(
            severity=IssueSeverity(data.get("severity", IssueSeverity.WARNING)),
            check=data.get("check", ""),
            path=data.get("path", ""),
            message=data.get("message", ""),
            line=data.get("line"),
        )


@dataclass(frozen=True)
class CodeValidationResult:
    """
    Outcome of statically validating a set of generated files.

    Attributes:
        checked_files (int): Number of files a check applied to.
        issues (List[ValidationIssue]): Every finding, errors first.
    """

    checked_files: int
    issues: List[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> List[ValidationIssue]:
        """Findings that will make the code fail."""
        return [i for i in self.issues if i.severity is IssueSeverity.ERROR]

    @property
    def warnings(self) -> List[ValidationIssue]:
        """Findings that are suspicious but not necessarily fatal."""
        return [i for i in self.issues if i.severity is IssueSeverity.WARNING]

    @property
    def passed(self) -> bool:
        """True when no errors were found."""
        return not self.errors

    @property
    def status(self) -> ImplementationStatus:
        """The implementation status this result implies."""
        if self.errors:
            return ImplementationStatus.VALIDATION_FAILED
        if self.warnings:
            return ImplementationStatus.SUCCESS_WITH_WARNINGS
        return ImplementationStatus.SUCCESS

    def to_dict(self) -> Dict[str, Any]:
        """Converts to dictionary representation."""
        return {
            "passed": self.passed,
            "checked_files": self.checked_files,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "issues": [i.to_dict() for i in self.issues],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CodeValidationResult":
        """Creates instance from dictionary."""
        return cls(
            checked_files=int(data.get("checked_files", 0)),
            issues=[ValidationIssue.from_dict(i) for i in data.get("issues") or []],
        )


@dataclass
class GeneratedFile:
    """Represents a generated file asset."""

    path: str
    content: str
    file_type: str

    def to_dict(self) -> Dict[str, Any]:
        """Converts to dictionary representation."""
        return {
            "path": self.path,
            "content": self.content,
            "file_type": self.file_type,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GeneratedFile":
        """Creates instance from dictionary."""
        return cls(
            path=data.get("path", ""),
            content=data.get("content", ""),
            file_type=data.get("file_type", ""),
        )


@dataclass
class ImplementationReport:
    """
    Holds the final result of the implementation execution pipeline.

    `status` is one of the ImplementationStatus values. `validation` is None
    for reports produced before code validation existed.
    """

    project_id: str
    files: List[GeneratedFile] = field(default_factory=list)
    summary: str = ""
    status: str = ImplementationStatus.SUCCESS.value
    validation: Optional[CodeValidationResult] = None

    def to_dict(self) -> Dict[str, Any]:
        """Converts to dictionary representation."""
        return {
            "project_id": self.project_id,
            "files": [f.to_dict() for f in self.files],
            "summary": self.summary,
            "status": self.status,
            "validation": self.validation.to_dict() if self.validation else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ImplementationReport":
        """Creates instance from dictionary."""
        files_data = data.get("files") or []
        validation_data = data.get("validation")
        return cls(
            project_id=data.get("project_id", ""),
            files=[GeneratedFile.from_dict(f) for f in files_data],
            summary=data.get("summary", ""),
            status=data.get("status", ImplementationStatus.SUCCESS.value),
            validation=(
                CodeValidationResult.from_dict(validation_data)
                if isinstance(validation_data, dict)
                else None
            ),
        )
