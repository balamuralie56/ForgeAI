"""
Data models for the ForgeAI Tester Plugin.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class GeneratedTestFile:
    """
    Immutable representation of an LLM-generated test suite file.
    """

    path: str
    content: str
    test_type: (
        str  # e.g., 'unit', 'integration', 'smoke', 'regression', 'mock', 'fixture'
    )

    def to_dict(self) -> Dict[str, Any]:
        """Converts to dictionary representation."""
        return {
            "path": self.path,
            "content": self.content,
            "test_type": self.test_type,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GeneratedTestFile":
        """Creates instance from dictionary."""
        return cls(
            path=data.get("path", ""),
            content=data.get("content", ""),
            test_type=data.get("test_type", ""),
        )


@dataclass
class TestReport:
    """
    Data container representing the output of the test generation process.
    """

    project_id: str
    test_files: List[GeneratedTestFile] = field(default_factory=list)
    coverage_summary: str = ""
    status: str = "PENDING"  # SUCCESS, FAILED
    summary: str = ""  # Overall testing summary markdown report

    def to_dict(self) -> Dict[str, Any]:
        """Converts to dictionary representation."""
        return {
            "project_id": self.project_id,
            "test_files": [tf.to_dict() for tf in self.test_files],
            "coverage_summary": self.coverage_summary,
            "status": self.status,
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TestReport":
        """Creates instance from dictionary."""
        return cls(
            project_id=data.get("project_id", ""),
            test_files=[
                GeneratedTestFile.from_dict(item) for item in data.get("test_files", [])
            ],
            coverage_summary=data.get("coverage_summary", ""),
            status=data.get("status", "PENDING"),
            summary=data.get("summary", ""),
        )
